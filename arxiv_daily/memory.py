"""Memory: interests.md (explicit, editable) + feedback.jsonl (your reactions) + consolidation."""
import json
import re
import tomllib
from datetime import date

from . import MEMORY, PAPERS, ROOT, STATE, llm

INTERESTS = MEMORY / "interests.md"
FEEDBACK = MEMORY / "feedback.jsonl"
CHANGELOG = MEMORY / "changelog.md"
MEMSTATE = STATE / "memory_state.json"

_PROFILE_RX = re.compile(r"```toml\n(.*?)```", re.S)
_FB_LINE = re.compile(r"^feedback: *(.*)$", re.M)


EXAMPLE = ROOT / "examples" / "interests.md"


def interests_text() -> str:
    if not INTERESTS.exists():  # first run: start from the template; edit memory/interests.md to make it yours
        INTERESTS.write_text(EXAMPLE.read_text())
    return INTERESTS.read_text()


def parse_profile(text: str) -> dict:
    m = _PROFILE_RX.search(text)
    if not m:
        raise ValueError("interests.md has no ```toml matching-profile block")
    profile = tomllib.loads(m.group(1))
    if not profile.get("categories"):
        raise ValueError("matching profile must list at least one arXiv category")
    for pat in [*profile.get("keywords", {}), *profile.get("negative", {})]:
        re.compile(pat)
    return profile


def load_profile() -> dict:
    return parse_profile(interests_text())


def load_feedback() -> list[dict]:
    if not FEEDBACK.exists():
        return []
    return [json.loads(l) for l in FEEDBACK.read_text().splitlines() if l.strip()]


def _note_path(pid: str):
    hits = list(PAPERS.glob(f"*/*/{pid}.md"))
    return hits[0] if hits else None


def _note_meta(text: str) -> dict:
    meta = {}
    for key in ("title", "matched", "tags"):
        m = re.search(rf"^{key}: *(.*)$", text, re.M)
        if m:
            try:
                meta[key] = json.loads(m.group(1))
            except json.JSONDecodeError:
                meta[key] = m.group(1)
    return meta


def normalize_rating(r: str) -> str:
    r = r.strip().lower()
    if r in ("+", "++", "up", "good", "yes", "👍", "1"):
        return "+"
    if r in ("-", "--", "down", "bad", "no", "👎", "0"):
        return "-"
    return r


def add_feedback(pid: str, rating: str, note: str = "", title: str = "", source: str = "cli") -> dict:
    rating = normalize_rating(rating)
    path = _note_path(pid)
    meta = {}
    if path:
        text = path.read_text()
        meta = _note_meta(text)
        value = rating + (f" {note}" if note else "")
        path.write_text(_FB_LINE.sub(f"feedback: {json.dumps(value)}", text, count=1))
    entry = {"date": date.today().isoformat(), "id": pid, "rating": rating, "note": note,
             "title": meta.get("title", title), "matched": meta.get("matched", []),
             "tags": meta.get("tags", []), "source": source}
    with open(FEEDBACK, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def sync_note_feedback() -> int:
    """Pick up feedback typed directly into a note's `feedback:` field."""
    logged = {(e["id"], e["rating"], e.get("note", "")) for e in load_feedback()}
    added = 0
    for path in PAPERS.glob("*/*/*.md"):
        m = _FB_LINE.search(path.read_text())
        if not m:
            continue
        raw = m.group(1).strip()
        try:
            raw = json.loads(raw) if raw else ""
        except json.JSONDecodeError:
            pass
        if not raw:
            continue
        rating, _, note = str(raw).partition(" ")
        rating = normalize_rating(rating)
        if (path.stem, rating, note) not in logged:
            add_feedback(path.stem, rating, note, source="note")
            added += 1
    return added


def _memstate() -> dict:
    return json.loads(MEMSTATE.read_text()) if MEMSTATE.exists() else {"consolidated_upto": 0}


UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "interests_md": {"type": "string", "description": "complete new contents of interests.md"},
        "changelog": {"type": "string", "description": "1-4 bullet lines describing what changed and why"},
        "changed": {"type": "boolean"},
    },
    "required": ["interests_md", "changelog", "changed"],
}

UPDATE_PROMPT = """You maintain a researcher's arXiv interest memory file (interests.md, below).
Update it according to the INPUT, then return the complete new file.

Rules:
- Keep the same overall structure and keep a valid ```toml matching-profile block (it is parsed by Python
  tomllib; keyword keys are case-insensitive Python regexes in single-quoted TOML literal strings, values are weights 1-5).
- Never remove or weaken anything under "## Pinned" unless the INPUT is an explicit instruction from the user to do so.
- Put emerging themes under "## Current focus" and repeatedly disliked themes under "## Less interested / avoid".
  Let stale focus items fade (remove them) if recent feedback no longer supports them.
- Adjust keyword weights / add keywords / add negative keywords / add authors only when the evidence supports it.
- Make the smallest edit that captures the change. If nothing should change, return the file unchanged with changed=false.

=== CURRENT interests.md ===
{interests}

=== INPUT ({kind}) ===
{payload}
"""


def update_interests(kind: str, payload: str, model: str) -> tuple[bool, str]:
    """Ask the LLM to revise interests.md; validate before writing. Returns (changed, changelog)."""
    out = llm.ask(UPDATE_PROMPT.format(interests=interests_text(), kind=kind, payload=payload),
                  UPDATE_SCHEMA, model)
    new = out["interests_md"].rstrip() + "\n"
    if not out["changed"] or new == interests_text():
        return False, out["changelog"]
    parse_profile(new)  # raises on a broken profile, leaving the old file untouched
    INTERESTS.write_text(new)
    with open(CHANGELOG, "a") as f:
        f.write(f"\n## {date.today().isoformat()} ({kind})\n{out['changelog'].strip()}\n")
    return True, out["changelog"]


def consolidation_due(cfg: dict) -> bool:
    pending = len(load_feedback()) - _memstate()["consolidated_upto"]
    if pending <= 0:
        return False
    return pending >= cfg["consolidate_after"] or date.today().weekday() == cfg["consolidate_weekday"]


def consolidate(model: str) -> tuple[bool, str]:
    fb = load_feedback()
    start = _memstate()["consolidated_upto"]
    if start >= len(fb):
        return False, "no new feedback"
    lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in fb[start:])
    changed, log = update_interests("feedback since last consolidation, '+' liked, '-' disliked", lines, model)
    MEMSTATE.write_text(json.dumps({"consolidated_upto": len(fb), "last": date.today().isoformat()}))
    return changed, log


def recent_feedback_block(n: int) -> str:
    fb = load_feedback()[-n:]
    if not fb:
        return "(no feedback yet)"
    return "\n".join(f"[{e['rating']}] {e.get('title') or e['id']}" + (f" — {e['note']}" if e.get("note") else "")
                     for e in fb)
