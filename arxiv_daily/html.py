"""Render digests/YYYY-MM-DD.json into a self-contained, offline HTML page per day."""
import json
import re
import unicodedata
from datetime import date
from html import escape
from pathlib import Path

from . import DIGESTS, ROOT

FB = str(ROOT / "fb").replace(str(Path.home()), "~")

_TEX = [(r"\\sim", "∼"), (r"\\gtrsim", "≳"), (r"\\lesssim", "≲"), (r"\\approx", "≈"), (r"\\simeq", "≃"),
        (r"\\ell", "ℓ"), (r"\\alpha", "α"), (r"\\beta", "β"), (r"\\gamma", "γ"), (r"\\Lambda", "Λ"),
        (r"\\odot", "⊙"), (r"\\times", "×"), (r"\\pm", "±"), (r"\\leq?", "≤"), (r"\\geq?", "≥"),
        (r"\\AA|\\r\{A\}", "Å"), (r"\\(mathrm|rm|textrm|text|mathit)\s*", ""), (r"\\[,;! ]", " ")]


def _math(m: re.Match) -> str:
    s = m.group(1)
    for pat, rep in _TEX:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\^\{([^}]*)\}|\^(\S)", lambda g: f"<sup>{g.group(1) or g.group(2)}</sup>", s)
    s = re.sub(r"_\{([^}]*)\}|_(\S)", lambda g: f"<sub>{g.group(1) or g.group(2)}</sub>", s)
    return s.replace("{", "").replace("}", "").replace("\\", "")


_ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303", "c": "\u0327",
            "v": "\u030c", "u": "\u0306", "=": "\u0304", ".": "\u0307", "H": "\u030b"}


def detex(s: str) -> str:
    """LaTeX accents in names: Luki\\'{c} -> Lukić."""
    return re.sub(r"\\(['`^\"~cvu=.H])\s*\{?([A-Za-z])\}?",
                  lambda m: unicodedata.normalize("NFC", m.group(2) + _ACCENTS[m.group(1)]), s).replace("{", "").replace("}", "")


def _scripts(s: str) -> str:
    """Bare x^y / x_y written outside $...$ (e.g. 10^7, f_esc^LyC) -> sup/sub."""
    s = re.sub(r"(?<=[\w)⊙★⋆])\^\{([^}]*)\}|(?<=[\w)⊙★⋆])\^([-+−]?[\w.]+)", lambda g: f"<sup>{g.group(1) or g.group(2)}</sup>", s)
    return re.sub(r"(?<=[A-Za-zα-ωΑ-Ω])_\{([^}]*)\}|(?<=[A-Za-zα-ωΑ-Ω])_([A-Za-z0-9]+)", lambda g: f"<sub>{g.group(1) or g.group(2)}</sub>", s)


def short(s: str, n: int = 38) -> str:
    """Chip text: drop parentheticals / trailing clauses, then cap length."""
    s = re.split(r"\s*[;(]", s)[0].strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def inline(s: str) -> str:
    """Escape, then render $tex$, bare ^/_, **bold** and `code` lightly."""
    s = escape(s, quote=False)
    parts = re.split(r"(\$[^$]+\$)", s)
    s = "".join(_math(re.match(r"\$(.+)\$", p, re.S)) if p.startswith("$") and p.endswith("$") and len(p) > 1
                else _scripts(p) for p in parts)
    s = re.sub(r"\\r\{A\}", "Å", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def blocks(s: str) -> str:
    """Paragraphs and '- ' bullet lists, as models tend to write them."""
    out, items = [], []
    for line in s.splitlines() + [""]:
        t = line.strip()
        if t.startswith(("- ", "• ")):
            items.append(f"<li>{inline(t[2:])}</li>")
            continue
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
            items = []
        if t:
            out.append(f"<p>{inline(t)}</p>")
    return "".join(out)


def _authors(a: list[str], n: int = 4) -> str:
    return escape(detex(", ".join(a[:n])) + (" et al." if len(a) > n else ""))


def _tier(score: int) -> str:
    return "hi" if score >= 9 else "mid" if score >= 7 else "lo" if score >= 5 else "min"


def _fb(pid: str, small: bool = False) -> str:
    cls = "fb small" if small else "fb"
    up, down = ("👍", "👎") if small else ("👍 More like this", "👎 Less like this")
    return (f'<button class="{cls}" data-id="{pid}" data-rating="+" data-cmd="{FB} {pid} + &quot;&quot;" title="More like this">{up}</button>'
            f'<button class="{cls}" data-id="{pid}" data-rating="-" data-cmd="{FB} {pid} - &quot;&quot;" title="Less like this">{down}</button>')


def _zt(pid: str, small: bool = False) -> str:
    label = "Zotero" if small else "Save to Zotero"
    return (f'<button class="zt{" small" if small else ""}" data-id="{pid}" title="Save to Zotero (metadata, PDF, note)">'
            f'<span class="zt-ico" aria-hidden="true">＋</span><span class="zt-label">{label}</span></button>')


def _chips(n: dict, tags: int, facilities: int) -> str:
    chips = []
    if n.get("data_release"):
        chips.append('<span class="chip release">Data release</span>')
    if n.get("redshift_range") and n["redshift_range"].lower() != "n/a":
        chips.append(f'<span class="chip z" title="{escape(n["redshift_range"])}">{inline(short(n["redshift_range"]))}</span>')
    chips += [f'<span class="chip fac" title="{escape(f)}">{escape(short(f, 28))}</span>' for f in n.get("facilities", [])[:facilities]]
    chips += [f'<span class="chip">{escape(t)}</span>' for t in n.get("tags", [])[:tags]]
    return "".join(chips)


def _links(pid: str) -> str:
    return (f'<a href="https://arxiv.org/abs/{pid}">Abstract</a><a href="https://arxiv.org/pdf/{pid}">PDF</a>'
            f'<a href="https://arxiv.org/html/{pid}">HTML</a>')


def _card(r: dict) -> str:
    """Compact list card; the full note lives in a <template> shown in the side panel."""
    p, s, n = r["paper"], r["score"], r["note"]
    pid = escape(p["id"])
    return f"""
<article class="card" data-note="{pid}" tabindex="0">
  <div class="card-head">
    <div class="score {_tier(s['score'])}" title="relevance score">{s['score']}</div>
    <div>
      <h3>{inline(p['title'])}</h3>
      <p class="byline">{_authors(p['authors'])} <span class="id">arXiv:{pid}</span></p>
    </div>
  </div>
  <p class="tldr">{inline(n['tldr'])}</p>
  <div class="chips">{_chips(n, tags=3, facilities=2)}</div>
  <footer class="actions">
    <nav><button class="open-note" data-note="{pid}">Read note <span aria-hidden="true">→</span></button>{_links(pid)}<a class="ob" data-ob="{pid}" hidden>Obsidian</a></nav>
    <div class="fbs">{_zt(pid, small=True)}{_fb(pid, small=True)}</div>
  </footer>
</article>
{_note(r)}"""


def _note(r: dict) -> str:
    p, s, n = r["paper"], r["score"], r["note"]
    pid = escape(p["id"])
    results = "".join(f"<li>{inline(x)}</li>" for x in n["key_results"])
    abstract = (f'<details class="abs"><summary>Abstract</summary>{blocks(p["abstract"])}</details>'
                if p.get("abstract") else "")
    return f"""<template id="note-{pid}">
  <header class="p-head">
    <div class="p-meta"><span class="score sm {_tier(s['score'])}">{s['score']}</span><span class="id">arXiv:{pid}</span></div>
    <h2>{inline(p['title'])}</h2>
    <p class="byline">{_authors(p['authors'], 12)}</p>
    <div class="chips">{_chips(n, tags=8, facilities=6)}</div>
  </header>
  <p class="p-tldr">{inline(n['tldr'])}</p>
  <section class="why"><div class="label">Why it matters to you</div>{blocks(n['relevance'])}</section>
  <section><h4>Key results</h4><ol class="results">{results}</ol></section>
  <section><h4>Problem</h4>{blocks(n['problem'])}</section>
  <section><h4>Data &amp; methods</h4>{blocks(n['data_methods'])}</section>
  <section><h4>Limitations &amp; open questions</h4>{blocks(n['limitations'])}</section>
  {abstract}
  <footer class="p-foot">
    <div class="fbs">{_zt(pid)}{_fb(pid)}</div>
    <nav>{_links(pid)}<a class="ob" data-ob="{pid}" hidden>Obsidian</a><a href="{escape('../' + r['note_path'])}" title="Raw Markdown note">.md</a></nav>
  </footer>
</template>"""


def _row(r: dict, with_reason: bool = True) -> str:
    p, s = r["paper"], r["score"]
    pid = escape(p["id"])
    reason = f'<p class="reason">{inline(s["reason"])}</p>' if with_reason else ""
    return f"""
<li class="row">
  <span class="pill {_tier(s['score'])}">{s['score']}</span>
  <div class="row-body">
    <a class="row-title" href="https://arxiv.org/abs/{pid}">{inline(p['title'])}</a>
    <p class="byline">{_authors(p['authors'], 2)} <span class="id">{pid}</span></p>
    {reason}
  </div>
  <div class="fbs">{_zt(pid, small=True)}{_fb(pid, small=True)}</div>
</li>"""


CSS = """
:root{--bg:#f6f4ef;--paper:#fffdf9;--ink:#1d1b26;--muted:#6b6878;--line:#e6e1d8;--accent:#5a3fd6;
--accent-soft:#ece8fb;--hi:#5a3fd6;--mid:#2f7d6d;--lo:#a07a2c;--min:#9a97a3;--chip:#f1eee7;--shadow:0 1px 2px rgba(30,20,60,.05),0 8px 24px -12px rgba(30,20,60,.12);color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#121119;--paper:#1b1a24;--ink:#ebe9f3;--muted:#9c99ab;--line:#2c2a38;
--accent:#a594ff;--accent-soft:#2a2547;--hi:#a594ff;--mid:#5cc4ad;--lo:#d6aa55;--min:#77748a;--chip:#252331;--shadow:none;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.6 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:780px;margin:0 auto;padding:48px 20px 80px}
a{color:inherit}
sup,sub{line-height:0;font-size:.72em}
.serif,h1,h2,h3{font-family:"Iowan Old Style","Charter","Palatino",Georgia,serif;font-weight:600;letter-spacing:-.01em}
.mast{border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:34px}
.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600;display:flex;justify-content:space-between;align-items:center}
.kicker nav a{color:var(--muted);text-decoration:none;margin-left:14px;letter-spacing:.06em}
.kicker nav a:hover{color:var(--accent)}
h1{font-size:40px;line-height:1.1;margin:10px 0 14px}
.stats{display:flex;flex-wrap:wrap;gap:6px 22px;color:var(--muted);font-size:14px}
.stats b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
h2{font-size:22px;margin:42px 0 16px;display:flex;align-items:baseline;gap:10px}
h2 .count{font:500 13px -apple-system,sans-serif;color:var(--muted)}
.card{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:24px 26px 18px;margin-bottom:20px;box-shadow:var(--shadow)}
.card-head{display:flex;gap:16px;align-items:flex-start}
.score{flex:none;width:44px;height:44px;border-radius:12px;display:grid;place-items:center;font:700 19px -apple-system,sans-serif;color:#fff;font-variant-numeric:tabular-nums}
.score.hi{background:var(--hi)}.score.mid{background:var(--mid)}.score.lo{background:var(--lo)}.score.min{background:var(--min)}
@media (prefers-color-scheme:dark){.score{color:#121119}}
h3{font-size:20px;line-height:1.3;margin:0 0 4px}
h3 a{text-decoration:none}h3 a:hover{color:var(--accent)}
.byline{margin:0;color:var(--muted);font-size:13.5px}
.id{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);margin-left:6px;opacity:.85}
.tldr{font-family:"Iowan Old Style","Charter",Georgia,serif;font-size:17px;line-height:1.55;margin:18px 0 14px}
.why{background:var(--accent-soft);border-radius:10px;padding:12px 16px;margin:0 0 14px;font-size:14.5px}
.why p{margin:4px 0}.why ul{margin:4px 0;padding-left:20px}.why li{margin:3px 0}
.label{font-size:11px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;color:var(--accent)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.chip{background:var(--chip);border-radius:999px;padding:2px 10px;font-size:12.5px;color:var(--muted)}
.chip.z{color:var(--accent);font-weight:600}.chip.fac{color:var(--ink)}
.chip.release{background:var(--mid);color:#fff;font-weight:600}
details{border-top:1px solid var(--line);margin-top:6px}
summary{cursor:pointer;padding:10px 0;font-size:13.5px;font-weight:600;color:var(--muted);list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸";display:inline-block;margin-right:8px;transition:transform .15s}
details[open]>summary::before{transform:rotate(90deg)}
summary:hover{color:var(--accent)}
.detail{font-size:14.5px;padding-bottom:6px}
.detail h4{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:14px 0 4px}
.detail p{margin:4px 0}.detail ul{margin:4px 0;padding-left:20px}.detail li{margin:4px 0}
.actions{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;border-top:1px solid var(--line);padding-top:14px;margin-top:4px}
.actions nav a{font-size:13.5px;font-weight:600;color:var(--accent);text-decoration:none;margin-right:16px}
.actions nav a:hover{text-decoration:underline}
.fbs{display:flex;gap:6px;flex:none}
.fb{border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:8px;padding:5px 11px;font:13px -apple-system,sans-serif;cursor:pointer}
.fb:hover{border-color:var(--accent);color:var(--accent)}
.fb.small{padding:3px 7px;font-size:13px}
.zt{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:8px;padding:5px 11px;font:13px -apple-system,sans-serif;cursor:pointer;white-space:nowrap}
.zt.small{padding:3px 8px;font-size:12.5px}
.zt:hover{border-color:#cc2936;color:#cc2936}
.zt-ico{font-weight:700;font-size:13px;line-height:1}
.zt.busy{opacity:.6;cursor:progress}
.zt.done{border-color:transparent;background:rgba(204,41,54,.1);color:#cc2936;cursor:default}
@media (prefers-color-scheme:dark){.zt:hover,.zt.done{color:#ff6b75;border-color:#ff6b75}.zt.done{background:rgba(255,107,117,.12);border-color:transparent}}
.fb.done{background:var(--accent);border-color:var(--accent);color:#fff}
.list{list-style:none;margin:0;padding:0;background:var(--paper);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}
.row{display:flex;gap:14px;padding:14px 18px;border-bottom:1px solid var(--line);align-items:flex-start}
.row:last-child{border-bottom:0}
.pill{flex:none;min-width:30px;text-align:center;border-radius:8px;padding:2px 0;font:700 13px -apple-system,sans-serif;color:#fff;margin-top:2px;font-variant-numeric:tabular-nums}
.pill.hi{background:var(--hi)}.pill.mid{background:var(--mid)}.pill.lo{background:var(--lo)}.pill.min{background:var(--min)}
@media (prefers-color-scheme:dark){.pill{color:#121119}}
.row-body{flex:1;min-width:0}
.row-title{font-weight:600;text-decoration:none;line-height:1.35}.row-title:hover{color:var(--accent)}
.reason{margin:4px 0 0;font-size:14px;color:var(--muted)}
.lower{border:0;margin-top:30px}.lower>summary{font-size:15px}
.lower .list .row{padding:10px 18px}
.empty{color:var(--muted);font-style:italic}
.foot{margin-top:48px;color:var(--muted);font-size:13px;text-align:center}
.foot code{font-size:12px;background:var(--chip);padding:1px 6px;border-radius:5px}
.toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(20px);background:var(--ink);color:var(--bg);padding:10px 16px;border-radius:10px;font-size:13.5px;opacity:0;transition:all .2s;pointer-events:none;max-width:90vw}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.card{cursor:pointer;transition:border-color .15s,transform .15s}
.card:hover,.card:focus-visible{border-color:var(--accent);outline:none}
.card.active{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.card h3{transition:color .15s}.card:hover h3{color:var(--accent)}
.card .tldr{font-size:16px;margin:14px 0 12px}
.actions nav{display:flex;align-items:center;flex-wrap:wrap;gap:4px 16px}
.actions nav a{margin-right:0}
.ob{color:#7c3aed!important}
.open-note{border:0;background:var(--accent);color:#fff;border-radius:8px;padding:6px 13px;font:600 13.5px -apple-system,sans-serif;cursor:pointer}
.open-note:hover{filter:brightness(1.08)}
@media (prefers-color-scheme:dark){.open-note{color:#121119}}
.scrim{position:fixed;inset:0;background:rgba(18,14,30,.28);opacity:0;pointer-events:none;transition:opacity .25s;backdrop-filter:blur(1.5px)}
.panel{position:fixed;top:0;right:0;height:100vh;width:min(680px,94vw);background:var(--paper);border-left:1px solid var(--line);
transform:translateX(102%);visibility:hidden;transition:transform .28s cubic-bezier(.2,.8,.2,1),visibility 0s .28s;display:flex;flex-direction:column;z-index:10}
html.reading .panel{transform:none;visibility:visible;transition:transform .28s cubic-bezier(.2,.8,.2,1);box-shadow:-24px 0 60px -20px rgba(20,10,50,.35)}html.reading .scrim{opacity:1;pointer-events:auto}html.reading body{overflow:hidden}
.p-bar{display:flex;align-items:center;gap:6px;padding:12px 18px;border-bottom:1px solid var(--line);flex:none}
.p-bar button{border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:8px;width:34px;height:30px;cursor:pointer;font-size:14px}
.p-bar button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
.p-bar button:disabled{opacity:.35;cursor:default}
.p-pos{font:12.5px -apple-system,sans-serif;color:var(--muted);min-width:44px;text-align:center;font-variant-numeric:tabular-nums}
.p-close{margin-left:auto}
.p-body{overflow-y:auto;padding:26px 34px 0;flex:1;overscroll-behavior:contain}
.p-meta{display:flex;align-items:center;gap:10px}
.score.sm{width:30px;height:30px;border-radius:8px;font-size:14px}
.p-head h2{font-size:25px;line-height:1.25;margin:12px 0 6px;display:block}
.p-head .byline{margin-bottom:14px}
.p-tldr{font-family:"Iowan Old Style","Charter",Georgia,serif;font-size:18px;line-height:1.55;margin:22px 0 18px;padding-top:20px;border-top:1px solid var(--line)}
.p-body section{margin:0 0 20px;font-size:15px}
.p-body section.why{padding:14px 18px;font-size:15px}
.p-body h4{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.p-body p{margin:6px 0}.p-body ul{padding-left:20px;margin:6px 0}.p-body li{margin:5px 0}
.results{counter-reset:r;list-style:none;padding:0;margin:0}
.results li{counter-increment:r;position:relative;padding:8px 0 8px 34px;border-bottom:1px dashed var(--line);margin:0}
.results li:last-child{border-bottom:0}
.results li::before{content:counter(r);position:absolute;left:0;top:9px;width:22px;height:22px;border-radius:50%;background:var(--accent-soft);color:var(--accent);font:700 12px/22px -apple-system,sans-serif;text-align:center}
.abs{border-top:1px solid var(--line);margin:0 0 8px;font-size:14px;color:var(--muted)}
.p-foot{position:sticky;bottom:0;background:var(--paper);border-top:1px solid var(--line);margin:20px -34px 0;padding:14px 34px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.p-foot nav a{font-size:13.5px;font-weight:600;color:var(--accent);text-decoration:none;margin-left:16px}
.p-foot nav a:hover{text-decoration:underline}
@media (max-width:560px){.p-body{padding:20px 20px 0}.p-foot{margin:20px -20px 0;padding:12px 20px}.p-head h2{font-size:21px}}
@media (max-width:560px){.wrap{padding-top:28px}h1{font-size:30px}.card{padding:18px}.row{flex-wrap:wrap}.row .fbs{margin-left:44px}}
"""

JS = """
const toast=document.querySelector('.toast'),panel=document.querySelector('.panel'),body=panel.querySelector('.p-body');
const ids=[...document.querySelectorAll('.card[data-note]')].map(c=>c.dataset.note);let cur=-1;
function copy(t){if(navigator.clipboard&&window.isSecureContext)return navigator.clipboard.writeText(t);
const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();return Promise.resolve()}
function say(t){toast.textContent=t;toast.classList.add('show');clearTimeout(window._t);window._t=setTimeout(()=>toast.classList.remove('show'),3200)}
function open(id,push){const i=ids.indexOf(id),tpl=document.getElementById('note-'+id);if(i<0||!tpl)return;cur=i;
body.replaceChildren(tpl.content.cloneNode(true));body.scrollTop=0;refresh();
document.querySelectorAll('.card.active').forEach(c=>c.classList.remove('active'));
const card=document.querySelector('.card[data-note="'+id+'"]');card.classList.add('active');
panel.querySelector('.p-pos').textContent=(i+1)+' / '+ids.length;
panel.querySelector('[data-dir="-1"]').disabled=i===0;panel.querySelector('[data-dir="1"]').disabled=i===ids.length-1;
document.documentElement.classList.add('reading');panel.setAttribute('aria-hidden','false');
if(push!==false)history.replaceState(null,'','#'+id);panel.querySelector('.p-close').focus({preventScroll:true})}
function close(){if(cur<0)return;document.documentElement.classList.remove('reading');panel.setAttribute('aria-hidden','true');
const card=document.querySelector('.card[data-note="'+ids[cur]+'"]');cur=-1;history.replaceState(null,'',location.pathname);
if(card){card.focus({preventScroll:true});card.scrollIntoView({block:'nearest',behavior:'smooth'})}}
function step(d){if(cur<0)return;const j=cur+d;if(j>=0&&j<ids.length){open(ids[j]);
document.querySelector('.card[data-note="'+ids[j]+'"]').scrollIntoView({block:'nearest',behavior:'smooth'})}}
const API=location.protocol.startsWith('http');
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Arxiv-Daily':'1'},body:JSON.stringify(data)});
const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j}
function markZ(id){document.querySelectorAll('.zt[data-id="'+id+'"]').forEach(b=>{b.classList.remove('busy');b.classList.add('done');
b.querySelector('.zt-ico').textContent='✓';b.querySelector('.zt-label').textContent=b.classList.contains('small')?'In Zotero':'In Zotero';b.title='Already in your Zotero library'})}
function markF(id,r){document.querySelectorAll('.fb[data-id="'+id+'"]').forEach(b=>b.classList.toggle('done',b.dataset.rating===r))}
function markO(id,uri){document.querySelectorAll('.ob[data-ob="'+id+'"]').forEach(a=>{a.href=uri;a.hidden=false;a.title='Open the note in Obsidian'})}
function refresh(){if(!API)return;fetch('/api/state').then(r=>r.json()).then(s=>{s.zotero.forEach(markZ);Object.entries(s.feedback).forEach(([i,r])=>markF(i,r));
Object.entries(s.obsidian||{}).forEach(([i,u])=>markO(i,u))}).catch(()=>{})}
refresh();
document.addEventListener('click',async e=>{const zt=e.target.closest('.zt');
if(zt){e.stopPropagation();if(zt.classList.contains('done')||zt.classList.contains('busy'))return;
if(!API){say('Zotero saving needs the helper: open http://127.0.0.1:8765 (it starts with ./launchd/install.sh)');return}
zt.classList.add('busy');zt.querySelector('.zt-label').textContent='Saving…';
try{const r=await post('/api/zotero',{id:zt.dataset.id});markZ(zt.dataset.id);
say(r.status==='exists'?'Already in Zotero ('+r.collection+')':'Saved to Zotero → '+r.collection+(r.obsidian?' · Obsidian note: '+r.obsidian:'')+(r.obsidian_error?' · Obsidian failed: '+r.obsidian_error:''));refresh()}
catch(err){zt.classList.remove('busy');zt.querySelector('.zt-label').textContent=zt.classList.contains('small')?'Zotero':'Save to Zotero';say('Zotero: '+err.message)}
return}
const fb=e.target.closest('.fb');
if(fb){e.stopPropagation();
if(!API){copy(fb.dataset.cmd).then(()=>{markF(fb.dataset.id,fb.dataset.rating);say('Copied: '+fb.dataset.cmd+' (paste in Terminal and add a reason inside the quotes)')});return}
const why=prompt(fb.dataset.rating==='+'?'👍 What did you like? (optional, helps the memory learn)':'👎 What was off? (optional, helps the memory learn)','');
if(why===null)return;
try{await post('/api/feedback',{id:fb.dataset.id,rating:fb.dataset.rating,note:why});markF(fb.dataset.id,fb.dataset.rating);
say(fb.dataset.rating==='+'?'👍 Recorded. Your memory will learn from it':'👎 Recorded. Your memory will learn from it')}
catch(err){say('Feedback failed: '+err.message)}
return}
if(e.target.closest('a'))return;
const st=e.target.closest('.p-step');if(st){step(+st.dataset.dir);return}
if(e.target.closest('.p-close')||e.target.closest('.scrim')){close();return}
const c=e.target.closest('[data-note]');if(c&&!panel.contains(c))open(c.dataset.note)});
document.addEventListener('keydown',e=>{if(e.metaKey||e.ctrlKey||e.altKey)return;
if(cur>=0){if(e.key==='Escape')close();else if(e.key==='ArrowRight'||e.key==='j'){e.preventDefault();step(1)}
else if(e.key==='ArrowLeft'||e.key==='k'){e.preventDefault();step(-1)}}
else if(e.key==='Enter'&&document.activeElement.matches('.card[data-note]'))open(document.activeElement.dataset.note)});
if(location.hash.length>1)open(decodeURIComponent(location.hash.slice(1)),false);
"""


def render(data: dict, prev_day: str | None, next_day: str | None) -> str:
    day = date.fromisoformat(data["date"])
    read, flagged, rest = data["read"], data["flagged"], data["rest"]
    nav = "".join([f'<a href="{prev_day}.html">← {prev_day[5:]}</a>' if prev_day else "",
                   f'<a href="{next_day}.html">{next_day[5:]} →</a>' if next_day else ""])
    cards = "".join(_card(r) for r in read) or '<p class="empty">Nothing crossed the must-read bar today.</p>'
    flagged_html = (f'<h2>Worth a look <span class="count">{len(flagged)}</span></h2>'
                    f'<ul class="list">{"".join(_row(r) for r in flagged)}</ul>') if flagged else ""
    rest_html = (f'<details class="lower"><summary>Scored lower · {len(rest)}</summary>'
                 f'<ul class="list">{"".join(_row(r, False) for r in rest)}</ul></details>') if rest else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>arXiv · {day:%a %d %b}</title><style>{CSS}</style></head>
<body><div class="wrap">
<header class="mast">
  <div class="kicker"><span>arXiv daily · astro-ph</span><nav>{nav}</nav></div>
  <h1>{day:%A, %-d %B %Y}</h1>
  <div class="stats"><span><b>{data['n_total']}</b> announced</span><span><b>{data['n_cands']}</b> shortlisted</span>
  <span><b>{len(read)}</b> must-read</span><span><b>{len(flagged)}</b> worth a look</span></div>
</header>
<h2>Must read <span class="count">{len(read)}</span></h2>
{cards}
{flagged_html}
{rest_html}
<p class="foot">Click a card to read its note · ← → step through papers · Esc closes · ＋ Zotero saves the paper, PDF and note · 👍 / 👎 teach your memory</p>
</div>
<div class="scrim"></div>
<aside class="panel" role="dialog" aria-modal="true" aria-label="Paper note" aria-hidden="true">
  <div class="p-bar">
    <button class="p-step" data-dir="-1" title="Previous paper (←)">←</button>
    <span class="p-pos"></span>
    <button class="p-step" data-dir="1" title="Next paper (→)">→</button>
    <button class="p-close" title="Close (Esc)">✕</button>
  </div>
  <div class="p-body"></div>
</aside>
<div class="toast"></div><script>{JS}</script></body></html>
"""


def render_all() -> Path | None:
    """Re-render every day so prev/next links stay current. Returns the newest page."""
    days = sorted(p.stem for p in DIGESTS.glob("*.json"))
    for i, d in enumerate(days):
        data = json.loads((DIGESTS / f"{d}.json").read_text())
        page = render(data, days[i - 1] if i else None, days[i + 1] if i + 1 < len(days) else None)
        (DIGESTS / f"{d}.html").write_text(page)
    return DIGESTS / f"{days[-1]}.html" if days else None
