"""Local helper: serves the digest pages on 127.0.0.1 and backs their buttons (Zotero, feedback)."""
import json
import logging
import mimetypes
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import DATA, DIGESTS, gitops, memory, obsidian, zotero

log = logging.getLogger("arxiv_daily")
_write_lock = threading.Lock()
SERVED_DIRS = ("digests", "papers")
cfg_global: dict = {}


def base_url(cfg: dict) -> str:
    return f"http://127.0.0.1:{cfg['server']['port']}"


def page_url(cfg: dict, page: Path) -> str:
    """http:// URL for a digest page if the helper is up, else a file:// URI."""
    try:
        urllib.request.urlopen(base_url(cfg) + "/api/state", timeout=1).close()
        return f"{base_url(cfg)}/{page.relative_to(DATA).as_posix()}"
    except Exception:
        return page.resolve().as_uri()


def _state() -> dict:
    fb = {}
    for e in memory.load_feedback():
        fb[e["id"]] = e["rating"]
    uris = {}
    if cfg_global.get("obsidian", {}).get("enabled"):
        vault = Path(cfg_global["obsidian"]["vault"]).expanduser()
        for pid, rel in obsidian.written().items():
            if (vault / rel).exists():
                uris[pid] = obsidian.plan(pid, {"authors": [], "title": ""}, cfg_global["obsidian"])[1]
    return {"zotero": sorted(zotero.saved()), "feedback": fb, "obsidian": uris}


def make_handler(cfg: dict):
    cfg_global.update(cfg)
    origin = base_url(cfg)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.debug("server: " + fmt, *args)

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path == "/":
                latest = max(DIGESTS.glob("*.html"), default=None)
                target = f"/digests/{latest.name}" if latest else "/api/state"
                return self._send(302, b"", "text/plain", {"Location": target})
            if path == "/api/state":
                return self._json(200, _state())
            file = (DATA / path.lstrip("/")).resolve()
            if not any(file.is_relative_to(DATA / d) for d in SERVED_DIRS) or not file.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = "text/plain; charset=utf-8" if file.suffix == ".md" else \
                (mimetypes.guess_type(file.name)[0] or "application/octet-stream") + "; charset=utf-8"
            self._send(200, file.read_bytes(), ctype)

        def do_POST(self):
            # Only our own pages may write: same origin + a custom header (blocks cross-site form posts).
            if self.headers.get("X-Arxiv-Daily") != "1" or self.headers.get("Origin") not in (None, origin):
                return self._json(403, {"error": "forbidden"})
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                pid = str(data.get("id", "")).strip()
                if not pid:
                    return self._json(400, {"error": "missing id"})
                path = urlparse(self.path).path
                with _write_lock:
                    if path == "/api/zotero":
                        result = zotero.save(pid, cfg["zotero"], force=bool(data.get("force")), obsidian_cfg=cfg.get("obsidian"))
                        if result["status"] == "saved":
                            gitops.commit(f"zotero: saved {pid}")
                        return self._json(200, result)
                    if path == "/api/feedback":
                        e = memory.add_feedback(pid, str(data.get("rating", "")), str(data.get("note", "")).strip(),
                                                source="page")
                        gitops.commit(f"feedback {e['rating']} {pid}")
                        return self._json(200, {"status": "recorded", "rating": e["rating"]})
                return self._json(404, {"error": "unknown endpoint"})
            except zotero.ZoteroError as e:
                return self._json(502, {"error": str(e)})
            except Exception as e:
                log.exception("server POST failed")
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

    return Handler


def _pull_loop(minutes: int = 15):
    """Pick up digests the GitHub Action pushed to the data repo."""
    while True:
        gitops.sync()
        threading.Event().wait(minutes * 60)


def serve(cfg: dict):
    port = cfg["server"]["port"]
    if gitops.has_remote():
        threading.Thread(target=_pull_loop, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg))
    log.info("serving digests at %s", base_url(cfg))
    httpd.serve_forever()
