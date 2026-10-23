"""Save papers into the local Zotero desktop app via its connector server (same API the browser extension uses)."""
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import DIGESTS, STATE, obsidian
from .fetch import http_get
from .html import blocks, detex, inline

CONNECTOR = "http://127.0.0.1:23119/connector"
SAVED = STATE / "zotero.json"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


class ZoteroError(RuntimeError):
    pass


def _call(endpoint: str, data: dict | None = None, timeout: int = 30) -> tuple[int, str]:
    req = urllib.request.Request(f"{CONNECTOR}/{endpoint}", data=json.dumps(data or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Zotero-Connector-API-Version": "3"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except OSError as e:
        raise ZoteroError("Zotero isn't running. Open the Zotero app and try again.") from e


def _upload_pdf(session: str, pid: str) -> bool:
    """Zotero 7+ expects the connector to fetch the file and upload the bytes itself."""
    pdf = http_get(f"https://arxiv.org/pdf/{pid}", timeout=120)
    if not pdf.startswith(b"%PDF"):
        return False
    meta = {"sessionID": session, "parentItemID": pid, "title": "arXiv Fulltext PDF",
            "url": f"https://arxiv.org/pdf/{pid}"}
    req = urllib.request.Request(f"{CONNECTOR}/saveAttachment", data=pdf, method="POST",
                                 headers={"Content-Type": "application/pdf", "X-Metadata": json.dumps(meta),
                                          "X-Zotero-Connector-API-Version": "3"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status in (200, 201)
    except urllib.error.HTTPError:
        return False


def saved() -> dict:
    return json.loads(SAVED.read_text()) if SAVED.exists() else {}


def arxiv_meta(pid: str) -> dict:
    feed = ET.fromstring(http_get(f"https://export.arxiv.org/api/query?id_list={pid}"))
    e = feed.find(ATOM + "entry")
    if e is None or e.findtext(ATOM + "title") in (None, "Error"):
        raise ZoteroError(f"arXiv has no record for {pid}")
    clean = lambda s: " ".join((s or "").split())
    return {"title": clean(e.findtext(ATOM + "title")),
            "authors": [detex(clean(a.findtext(ATOM + "name"))) for a in e.findall(ATOM + "author")],
            "abstract": clean(e.findtext(ATOM + "summary")),
            "date": (e.findtext(ATOM + "published") or "")[:10],
            "doi": e.findtext(ARXIV + "doi"),
            "journal_ref": clean(e.findtext(ARXIV + "journal_ref")),
            "primary": (e.find(ARXIV + "primary_category") or {}).get("term", "")}


def _digest_meta(pid: str) -> dict | None:
    """Metadata already captured in a digest sidecar; spares the rate-limited arXiv API."""
    for path in sorted(DIGESTS.glob("*.json"), reverse=True):
        d = json.loads(path.read_text())
        for r in d["read"] + d["flagged"] + d["rest"]:
            p = r["paper"]
            if p["id"] == pid and p.get("abstract") and p.get("authors"):
                cats = p.get("categories") or []
                return {"title": p["title"], "authors": [detex(a) for a in p["authors"]], "abstract": p["abstract"],
                        "date": d["date"], "doi": None, "journal_ref": "", "primary": cats[0] if cats else ""}
    return None


def _note_html(pid: str, obsidian_uri: str | None = None) -> str | None:
    """Our reading note (from the digest sidecars) as a Zotero child note."""
    for path in sorted(DIGESTS.glob("*.json"), reverse=True):
        for r in json.loads(path.read_text())["read"]:
            if r["paper"]["id"] != pid:
                continue
            n, s = r["note"], r["score"]
            results = "".join(f"<li>{inline(x)}</li>" for x in n["key_results"])
            link = f'<p><a href="{obsidian_uri}">Open in Obsidian</a></p>' if obsidian_uri else ""
            return (f"<h1>arxiv-daily note · {s['score']}/10</h1>{link}"
                    f"<p><strong>TL;DR</strong> {inline(n['tldr'])}</p>"
                    f"<h2>Why it matters to you</h2>{blocks(n['relevance'])}"
                    f"<h2>Key results</h2><ol>{results}</ol>"
                    f"<h2>Problem</h2>{blocks(n['problem'])}"
                    f"<h2>Data &amp; methods</h2>{blocks(n['data_methods'])}"
                    f"<h2>Limitations</h2>{blocks(n['limitations'])}")
    return None


def _creator(name: str) -> dict:
    first, _, last = name.rpartition(" ")
    return {"firstName": first, "lastName": last, "creatorType": "author"} if first else \
           {"name": name, "creatorType": "author"}


def save(pid: str, cfg: dict, force: bool = False, obsidian_cfg: dict | None = None) -> dict:
    """Returns {"status": "saved"|"exists", "collection": name, "obsidian": vault-relative path?}."""
    already = saved()
    if pid in already and not force:
        return {"status": "exists", **already[pid]}
    status, _ = _call("ping")
    if status != 200:
        raise ZoteroError("Zotero isn't responding. Is the app open?")

    m = _digest_meta(pid) or arxiv_meta(pid)
    tags = [{"tag": t} for t in cfg.get("tags", [])]
    item = {
        "id": pid, "itemType": "preprint", "title": m["title"], "creators": [_creator(a) for a in m["authors"]],
        "abstractNote": m["abstract"], "date": m["date"], "repository": "arXiv", "archiveID": f"arXiv:{pid}",
        "url": f"https://arxiv.org/abs/{pid}", "DOI": m["doi"] or f"10.48550/arXiv.{pid}",
        "libraryCatalog": "arXiv.org", "accessDate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "extra": "\n".join(x for x in [f"arXiv: {m['primary']}" if m["primary"] else "",
                                       f"Journal reference: {m['journal_ref']}" if m["journal_ref"] else ""] if x),
        "tags": tags, "notes": [], "attachments": [],
    }
    use_obsidian = bool(obsidian_cfg and obsidian_cfg.get("enabled"))
    ob_uri = obsidian.plan(pid, m, obsidian_cfg)[1] if use_obsidian else None
    if note := _note_html(pid, ob_uri):
        item["notes"].append({"note": note})

    session = str(uuid.uuid4())
    status, body = _call("saveItems", {"sessionID": session, "uri": item["url"], "items": [item]}, timeout=120)
    if status not in (200, 201):
        raise ZoteroError(f"Zotero refused the item (HTTP {status}): {body[:200]}")
    pdf = cfg.get("attach_pdf", True) and _upload_pdf(session, pid)

    collection = "selected collection"
    if want := cfg.get("collection"):
        _, body = _call("getSelectedCollection")
        targets = json.loads(body).get("targets", [])
        target = next((t for t in targets if t["name"].lower() == want.lower()), None)
        if target:
            _call("updateSession", {"sessionID": session, "target": target["id"]})
            collection = target["name"]

    already[pid] = {"date": datetime.now().date().isoformat(), "collection": collection, "pdf": bool(pdf)}
    SAVED.write_text(json.dumps(already, indent=1, ensure_ascii=False))
    result = {"status": "saved", **already[pid]}
    if use_obsidian:
        try:
            path = obsidian.write(pid, m, obsidian_cfg, collection)
            result["obsidian"] = path.relative_to(Path(obsidian_cfg["vault"]).expanduser()).as_posix()
        except Exception as e:  # the Zotero save already succeeded; report, don't fail
            result["obsidian_error"] = f"{type(e).__name__}: {e}"
    return result
