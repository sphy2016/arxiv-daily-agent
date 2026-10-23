"""LLM access: one `ask(prompt, schema, model)` returning schema-checked JSON.

Providers (config `[llm] provider`):
  - "openai-compatible" (default): any OpenAI-style /chat/completions endpoint, e.g. DeepSeek, or a gateway
    hosting DeepSeek models. Key from $<api_key_env> or the file api_key_file; never stored in the repo.
  - "claude-code": headless `claude -p`; `[models]` then take Claude names (sonnet / opus).
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import load_config


class LLMError(RuntimeError):
    pass


USAGE = {"calls": 0, "prompt": 0, "cache_hit": 0, "completion": 0}
_usage_lock = threading.Lock()


def usage_summary() -> str:
    u = USAGE
    return (f"{u['calls']} LLM calls, {u['prompt']:,} prompt tokens ({u['cache_hit']:,} cache hits), "
            f"{u['completion']:,} completion tokens")


# --- schema checking: models without a strict JSON-schema mode get the schema in the prompt, we verify the reply

_TYPES = {"string": str, "boolean": bool, "array": list, "object": dict}


def _coerce(schema: dict, v, path: str = "$"):
    """Validate v against the small JSON-schema subset we use; lightly coerce numbers. Raises ValueError."""
    t = schema.get("type")
    if t in ("integer", "number"):
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                pass
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{path}: expected {t}, got {type(v).__name__}")
        if t == "integer":
            if v != int(v):
                raise ValueError(f"{path}: expected integer, got {v}")
            v = int(v)
        if "minimum" in schema and v < schema["minimum"] or "maximum" in schema and v > schema["maximum"]:
            raise ValueError(f"{path}: {v} outside [{schema.get('minimum')}, {schema.get('maximum')}]")
        return v
    if t in _TYPES and not isinstance(v, _TYPES[t]):
        raise ValueError(f"{path}: expected {t}, got {type(v).__name__}")
    if t == "object":
        for k in schema.get("required", []):
            if k not in v:
                raise ValueError(f"{path}: missing required key '{k}'")
        return {k: _coerce(schema["properties"][k], x, f"{path}.{k}") if k in schema.get("properties", {}) else x
                for k, x in v.items()}
    if t == "array" and "items" in schema:
        return [_coerce(schema["items"], x, f"{path}[{i}]") for i, x in enumerate(v)]
    return v


def _parse_json(text: str):
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)  # some models fence the JSON anyway
    return json.loads(m.group(1) if m else text)


# --- openai-compatible provider

def _api_key(cfg: dict) -> str:
    key = os.environ.get(cfg["api_key_env"], "").strip()
    if not key:
        f = Path(cfg["api_key_file"]).expanduser()
        key = f.read_text().strip() if f.exists() else ""
    if not key:
        raise LLMError(f"no API key: set ${cfg['api_key_env']} or put the key in {cfg['api_key_file']} "
                       f"(chmod 600). Scheduled jobs don't see your shell env, so use the file for those.")
    return key


def key_source(cfg: dict) -> str:
    if os.environ.get(cfg["api_key_env"], "").strip():
        return f"${cfg['api_key_env']}"
    f = Path(cfg["api_key_file"]).expanduser()
    return str(f) if f.exists() and f.read_text().strip() else "none found"


def _post(cfg: dict, body: dict) -> dict:
    """POST /chat/completions with backoff on rate limits, 5xx and network errors."""
    req = urllib.request.Request(cfg["base_url"].rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {_api_key(cfg)}"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=cfg["timeout"]) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * 3 ** attempt)
                continue
            hint = {401: " (check the API key)", 402: " (insufficient balance)"}.get(e.code, "")
            raise LLMError(f"HTTP {e.code}{hint}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < 3:
                time.sleep(5 * 3 ** attempt)
                continue
            raise LLMError(f"cannot reach {cfg['base_url']}: {getattr(e, 'reason', e)}") from e


def _ask_openai(prompt: str, schema: dict, model: str, cfg: dict) -> dict:
    messages = [
        {"role": "system", "content": "You are a careful research assistant. Reply with a single JSON object only: "
                                      "no prose, no markdown fences."},
        {"role": "user", "content": f"{prompt}\n\nRespond with one JSON object that conforms to this JSON Schema:\n"
                                    f"{json.dumps(schema, ensure_ascii=False)}"},
    ]
    body = {"model": model, "messages": messages, "max_tokens": cfg["max_tokens"],
            "temperature": cfg["temperature"], "stream": False}
    if cfg["json_mode"] == "json_object":
        body["response_format"] = {"type": "json_object"}

    error = "empty reply"
    for attempt in range(3):
        out = _post(cfg, body)
        u = out.get("usage") or {}
        with _usage_lock:
            USAGE["calls"] += 1
            USAGE["prompt"] += u.get("prompt_tokens", 0)
            USAGE["cache_hit"] += u.get("prompt_cache_hit_tokens", 0)
            USAGE["completion"] += u.get("completion_tokens", 0)
        choice = (out.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        if choice.get("finish_reason") == "length":
            raise LLMError(f"reply cut off at max_tokens={cfg['max_tokens']}; raise [llm] max_tokens")
        try:
            if not content.strip():
                raise ValueError("empty reply")  # JSON mode occasionally returns nothing
            return _coerce(schema, _parse_json(content))
        except (ValueError, json.JSONDecodeError) as e:
            error = str(e)
            body["messages"] = messages + [{"role": "assistant", "content": content or "(empty)"},
                                           {"role": "user", "content": f"That reply was invalid ({error}). "
                                            "Reply again with only the corrected JSON object."}]
    raise LLMError(f"model never returned valid JSON ({error})")


# --- claude-code provider (headless CLI)

def _ask_claude_code(prompt: str, schema: dict, model: str, timeout: int = 900) -> dict:
    exe = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    if not os.path.exists(exe):
        raise LLMError("claude CLI not found on PATH")
    cmd = [exe, "-p", "--model", model, "--output-format", "json", "--json-schema", json.dumps(schema),
           "--no-session-persistence", "--tools", ""]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
        out = json.loads(proc.stdout)
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"claude timed out after {timeout}s") from e
    except json.JSONDecodeError:
        raise LLMError(f"claude exit {proc.returncode}: {(proc.stderr or proc.stdout)[-800:]}")
    if out.get("is_error") or "structured_output" not in out:
        raise LLMError(f"claude failed ({out.get('subtype')}): {str(out.get('result'))[-800:]}")
    return out["structured_output"]


def ask(prompt: str, schema: dict, model: str) -> dict:
    cfg = load_config()["llm"]
    if cfg["provider"] == "claude-code":
        return _ask_claude_code(prompt, schema, model)
    return _ask_openai(prompt, schema, model, cfg)


def list_models(cfg: dict) -> list[str]:
    req = urllib.request.Request(cfg["base_url"].rstrip("/") + "/models",
                                 headers={"Authorization": f"Bearer {_api_key(cfg)}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return [m["id"] for m in json.load(r).get("data", [])]
