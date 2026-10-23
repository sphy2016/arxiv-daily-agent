"""Write step: standard-format paper notes and the daily digest."""
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from . import DATA, DIGESTS, PAPERS
from .fetch import Paper


def _y(v) -> str:
    """JSON scalars/lists are valid YAML, so frontmatter stays machine-readable."""
    return json.dumps(v, ensure_ascii=False)


def note_path(p: Paper, day: date) -> Path:
    return PAPERS / f"{day:%Y}" / f"{day:%m}" / f"{p.id}.md"


def write_note(p: Paper, day: date, s: dict, n: dict, source: str) -> Path:
    path = note_path(p, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    results = "\n".join(f"- {r}" for r in n["key_results"])
    path.write_text(f"""---
id: {_y(p.id)}
title: {_y(p.title)}
authors: {_y(p.authors)}
categories: {_y(p.categories)}
announced: {day.isoformat()}
url: {_y(p.url)}
score: {s['score']}
matched: {_y(s['matched'])}
tags: {_y(n['tags'])}
facilities: {_y(n['facilities'])}
redshift: {_y(n['redshift_range'])}
data_release: {str(n['data_release']).lower()}
read_from: {source}
feedback: ""
---

# {p.title}

{', '.join(p.authors[:6])}{' et al.' if len(p.authors) > 6 else ''} · [arXiv:{p.id}]({p.url}) · score **{s['score']}/10**

> **TL;DR** {n['tldr']}

## Problem
{n['problem']}

## Data & methods
{n['data_methods']}

## Key results
{results}

## Why it matters to you
{n['relevance']}

## Limitations & open questions
{n['limitations']}

## Abstract
{p.abstract}
""")
    return path


def write_digest(day: date, n_total: int, n_cands: int, read: list[tuple[Paper, dict, dict, Path]],
                 flagged: list[tuple[Paper, dict]], rest: list[tuple[Paper, dict]]) -> Path:
    path = DIGESTS / f"{day.isoformat()}.md"
    DIGESTS.mkdir(exist_ok=True)
    lines = [f"# arXiv digest · {day:%a %d %b %Y}", "",
             f"{n_total} new announcements → {n_cands} keyword candidates → "
             f"**{len(read)} must-read**, {len(flagged)} worth a look.", ""]
    if read:
        lines += ["## Must read", ""]
        for p, s, n, np in read:
            rel = os.path.relpath(np, path.parent)
            lines += [f"### [{s['score']}] {p.title}",
                      f"{p.authors[0] if p.authors else ''}{' et al.' if len(p.authors) > 1 else ''} · "
                      f"[abs]({p.url}) · [note]({rel}) · `{p.id}`", "",
                      n["tldr"], "", f"*Why:* {n['relevance']}", ""]
    if flagged:
        lines += ["## Worth a look", ""]
        for p, s in flagged:
            lines += [f"- **[{s['score']}]** [{p.title}]({p.url}) `{p.id}` — {s['reason']}"]
        lines.append("")
    if rest:
        lines += ["<details><summary>Scored lower</summary>", ""]
        lines += [f"- [{s['score']}] [{p.title}]({p.url}) `{p.id}`" for p, s in rest]
        lines += ["", "</details>", ""]
    lines += ["---", "Feedback: `./fb <id> + \"why\"` or `./fb <id> - \"why\"`, or fill in `feedback:` in a note."]
    path.write_text("\n".join(lines) + "\n")

    # Structured sidecar: the source for the HTML page (arxiv_daily/html.py).
    pj = lambda p: {k: v for k, v in asdict(p).items() if k not in ("kw_score", "kw_hits")}
    data = {"date": day.isoformat(), "n_total": n_total, "n_cands": n_cands,
            "read": [{"paper": pj(p), "score": s, "note": n, "note_path": str(np.relative_to(DATA))}
                     for p, s, n, np in read],
            "flagged": [{"paper": pj(p), "score": s} for p, s in flagged],
            "rest": [{"paper": pj(p), "score": s} for p, s in rest]}
    path.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return path
