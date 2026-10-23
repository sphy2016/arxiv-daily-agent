"""Thin wrapper over headless Claude Code (`claude -p`) returning schema-validated JSON."""
import json
import os
import shutil
import subprocess
from pathlib import Path


class ClaudeError(RuntimeError):
    pass


def _claude_bin() -> str:
    found = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    if not os.path.exists(found):
        raise ClaudeError("claude CLI not found on PATH")
    return found


def ask(prompt: str, schema: dict, model: str, tools: str = "", cwd: Path | None = None,
        timeout: int = 900) -> dict:
    """Run one headless turn. `tools` is a comma list of built-in tools ("" = none)."""
    cmd = [_claude_bin(), "-p", "--model", model, "--output-format", "json",
           "--json-schema", json.dumps(schema), "--no-session-persistence", "--tools", tools]
    if tools:
        cmd += ["--allowedTools", tools, "--permission-mode", "dontAsk"]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude timed out after {timeout}s") from e
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeError(f"claude exit {proc.returncode}: {(proc.stderr or proc.stdout)[-800:]}")
    if out.get("is_error") or "structured_output" not in out:
        raise ClaudeError(f"claude failed ({out.get('subtype')}): {str(out.get('result'))[-800:]}")
    return out["structured_output"]
