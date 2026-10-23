"""Write a paper note into the Obsidian vault, cross-linked with its Zotero item."""
import json
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from . import DIGESTS, STATE

WRITTEN = STATE / "obsidian.json"
LOCAL_API = "http://127.0.0.1:23119/api/users/0"


def written() -> dict:
    return json.loads(WRITTEN.read_text()) if WRITTEN.exists() else {}


def digest_entry(pid: str) -> dict | None:
    """The newest digest record for a paper: {'paper', 'score', 'note'?}."""
    for path in sorted(DIGESTS.glob("*.json"), reverse=True):
        d = json.loads(path.read_text())
        for r in d["read"] + d["flagged"] + d["rest"]:
            if r["paper"]["id"] == pid:
                return r
    return None


def _topic(cfg: dict, title: str, entry: dict | None) -> str:
    hay = " ".join([title, *(entry or {}).get("note", {}).get("tags", []), *(entry or {}).get("score", {}).get("matched", [])])
    for folder, pattern in cfg.get("topics", {}).items():
        if re.search(pattern, hay, re.I):
            return folder
    return cfg.get("default_topic", "arXiv")


def plan(pid: str, meta: dict, cfg: dict) -> tuple[Path, str]:
    """Where the note goes (absolute path) and its obsidian:// URI. Deterministic, so the
    Zotero note can link to it before the file exists."""
    vault = Path(cfg["vault"]).expanduser()
    if pid in written():
        rel = Path(written()[pid])
    else:
        first = (meta["authors"][0].split()[-1] if meta["authors"] else "Anon")
        etal = " et al." if len(meta["authors"]) > 2 else (f" & {meta['authors'][1].split()[-1]}" if len(meta["authors"]) == 2 else "")
        name = f"Notes of {first}{etal} 20{pid[:2]}"
        rel = Path(cfg["folder"]) / _topic(cfg, meta["title"], digest_entry(pid)) / f"{name}.md"
        if (vault / rel).exists() and f'arxiv: "{pid}"' not in (vault / rel).read_text():
            rel = rel.with_name(f"{name} ({pid}).md")  # same author-year, different paper
    uri = "obsidian://open?" + urllib.parse.urlencode(
        {"vault": vault.name, "file": rel.with_suffix("").as_posix()}, quote_via=urllib.parse.quote)
    return vault / rel, uri


def zotero_keys(pid: str, title: str) -> tuple[str | None, str | None]:
    """(item key, PDF attachment key) via Zotero's read-only local API; (None, None) if unavailable."""
    try:
        q = urllib.parse.quote(title[:80])
        items = json.load(urllib.request.urlopen(f"{LOCAL_API}/items?q={q}&format=json&include=data", timeout=5))
        item = next((i for i in items if i["data"].get("archiveID") == f"arXiv:{pid}"
                     or pid in (i["data"].get("DOI") or "")), None)
        if not item:
            return None, None
        kids = json.load(urllib.request.urlopen(f"{LOCAL_API}/items/{item['key']}/children?format=json", timeout=5))
        pdf = next((k["key"] for k in kids if k["data"].get("contentType") == "application/pdf"), None)
        return item["key"], pdf
    except Exception:
        return None, None


def _y(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _tag(t: str) -> str:
    return re.sub(r"[^\w/-]+", "-", t.strip().lower()).strip("-")


def write(pid: str, meta: dict, cfg: dict, zotero_collection: str = "") -> Path:
    """Create the note unless it already exists (never overwrites your edits). Returns its path."""
    path, _ = plan(pid, meta, cfg)
    vault = Path(cfg["vault"]).expanduser()
    rel = path.relative_to(vault).as_posix()
    if path.exists():
        _record(pid, rel)
        return path

    entry = digest_entry(pid) or {}
    n, s = entry.get("note"), entry.get("score", {})
    item_key, pdf_key = zotero_keys(pid, meta["title"])
    links = [f"[Open in Zotero](zotero://select/library/items/{item_key})" if item_key else "",
             f"[PDF in Zotero](zotero://open-pdf/library/items/{pdf_key})" if pdf_key else "",
             f"[arXiv](https://arxiv.org/abs/{pid})", f"[PDF](https://arxiv.org/pdf/{pid})"]
    tags = ["arxiv-daily", *[_tag(t) for t in (n or {}).get("tags", [])]]

    fm = [f"title: {_y(meta['title'])}", f"authors: {_y(meta['authors'][:15])}", f"year: 20{pid[:2]}",
          f"arxiv: {_y(pid)}", f"doi: {_y(meta.get('doi') or f'10.48550/arXiv.{pid}')}",
          f"url: {_y(f'https://arxiv.org/abs/{pid}')}"]
    if item_key:
        fm.append(f"zotero: {_y(f'zotero://select/library/items/{item_key}')}")
    if zotero_collection:
        fm.append(f"zotero-collection: {_y(zotero_collection)}")
    if s.get("score") is not None:
        fm.append(f"score: {s['score']}")
    if n:
        fm += [f"redshift: {_y(n['redshift_range'])}", f"facilities: {_y(n['facilities'])}"]
    fm += [f"tags: {_y(tags)}", f"created: {date.today().isoformat()}"]

    authors = ", ".join(meta["authors"][:6]) + (" et al." if len(meta["authors"]) > 6 else "")
    body = [f"# {meta['title']}", "", f"{authors}", "", " · ".join(l for l in links if l), ""]
    if n:
        results = "\n".join(f"{i}. {r}" for i, r in enumerate(n["key_results"], 1))
        body += ["> [!abstract] TL;DR", f"> {n['tldr']}", "",
                 "## Why it matters to me", n["relevance"], "",
                 "## Key results", results, "",
                 "## Problem", n["problem"], "",
                 "## Data & methods", n["data_methods"], "",
                 "## Limitations & open questions", n["limitations"], ""]
    elif s.get("reason"):
        body += ["> [!info] Why it was flagged", f"> {s['reason']}", ""]
    body += ["## My notes", "", "", "> [!quote]- Abstract", f"> {meta['abstract']}", ""]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + "\n".join(fm) + "\n---\n\n" + "\n".join(body))
    _record(pid, rel)
    return path


def _record(pid: str, rel: str):
    w = written()
    w[pid] = rel
    WRITTEN.write_text(json.dumps(w, indent=1, ensure_ascii=False))
