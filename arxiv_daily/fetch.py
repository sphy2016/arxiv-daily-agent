"""Find step: pull today's arXiv announcements and keyword-prefilter them."""
import os
import re
import shutil
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

UA = {"User-Agent": "arxiv-daily/0.1 (personal paper watcher)"}
NS = {"arxiv": "http://arxiv.org/schemas/atom", "dc": "http://purl.org/dc/elements/1.1/"}


@dataclass
class Paper:
    id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    announce_type: str
    kw_score: float = 0.0
    kw_hits: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://arxiv.org/abs/{self.id}"


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def fetch_announcements(categories: list[str]) -> tuple[date | None, list[Paper]]:
    """New submissions and cross-lists from the latest announcement (replacements skipped)."""
    xml = http_get("https://rss.arxiv.org/rss/" + "+".join(categories))
    channel = ET.fromstring(xml).find("channel")
    pub = channel.findtext("pubDate")
    announced = parsedate_to_datetime(pub).date() if pub else None

    papers: dict[str, Paper] = {}
    for item in channel.findall("item"):
        kind = item.findtext("arxiv:announce_type", "", NS).strip()
        if kind not in ("new", "cross"):
            continue
        pid = item.findtext("link", "").rstrip("/").split("/")[-1]
        desc = item.findtext("description", "")
        abstract = desc.split("Abstract:", 1)[-1].strip()
        authors = [a.strip() for a in item.findtext("dc:creator", "", NS).split(",") if a.strip()]
        papers[pid] = Paper(
            id=pid,
            title=" ".join(item.findtext("title", "").split()),
            authors=authors,
            abstract=" ".join(abstract.split()),
            categories=[c.text for c in item.findall("category") if c.text],
            announce_type=kind,
        )
    return announced, list(papers.values())


def prefilter(papers: list[Paper], profile: dict, min_score: float, limit: int) -> list[Paper]:
    """Cheap regex scoring against the memory profile; title hits count double."""
    kws = [(re.compile(p, re.I), w, p) for p, w in profile.get("keywords", {}).items()]
    negs = [(re.compile(p, re.I), w) for p, w in profile.get("negative", {}).items()]
    authors = [a.lower() for a in profile.get("authors", [])]

    for p in papers:
        score, hits = 0.0, []
        for rx, w, pat in kws:
            if rx.search(p.title):
                score += 2 * w
                hits.append(pat)
            elif rx.search(p.abstract):
                score += w
                hits.append(pat)
        for rx, w in negs:
            if rx.search(p.title) or rx.search(p.abstract):
                score -= w
        if any(a in au.lower() for a in authors for au in p.authors):
            score += 10
            hits.append("author")
        p.kw_score, p.kw_hits = score, hits

    kept = sorted((p for p in papers if p.kw_score >= min_score), key=lambda p: -p.kw_score)
    return kept[:limit]


class _ArxivHTMLText(HTMLParser):
    """Flatten an arXiv (LaTeXML) HTML paper to text, keeping TeX for math, dropping refs."""
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "button", "svg"}
    SKIP_CLASSES = {"ltx_bibliography", "ltx_page_footer", "ltx_authors", "ltx_dates"}
    VOID = {"img", "br", "hr", "meta", "link", "input", "source", "col", "wbr"}
    BLOCK = {"p", "div", "section", "li", "tr", "figcaption", "table", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        skipping = tag in self.SKIP_TAGS or tag == "math" or bool(classes & self.SKIP_CLASSES)
        if tag == "math" and not self.skip:
            self.out.append(f" ${a.get('alttext', '')}$ ")
        if not self.skip and tag in self.BLOCK:
            self.out.append("\n\n## " if tag in ("h1", "h2", "h3") else "\n")
        self.stack.append((tag, skipping))
        self.skip += skipping

    def handle_endtag(self, tag):
        if not any(t == tag for t, _ in self.stack):
            return
        while self.stack:
            t, skipping = self.stack.pop()
            self.skip -= skipping
            if t == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)

    def text(self) -> str:
        s = "".join(self.out)
        s = re.sub(r"[ \t]+", " ", s)
        return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def fetch_fulltext(pid: str, max_chars: int = 180_000) -> str | None:
    """Full text from arXiv's HTML rendering; None when there is no usable HTML version."""
    try:
        html = http_get(f"https://arxiv.org/html/{pid}").decode("utf-8", "replace")
    except Exception:
        return None
    parser = _ArxivHTMLText()
    parser.feed(html)
    text = parser.text()
    return text[:max_chars] if len(text) > 5000 else None


def fetch_pdf_text(pid: str, workdir, max_chars: int = 180_000) -> str | None:
    """Fallback when there is no HTML rendering: PDF -> text via poppler's pdftotext."""
    exe = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    if not os.path.exists(exe):
        return None
    pdf = workdir / "paper.pdf"
    pdf.write_bytes(http_get(f"https://arxiv.org/pdf/{pid}", timeout=120))
    r = subprocess.run([exe, "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=120)
    text = r.stdout.split("\nReferences\n")[0] if r.returncode == 0 else ""
    return text[:max_chars] if len(text) > 5000 else None
