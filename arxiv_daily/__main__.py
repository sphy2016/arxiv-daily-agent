"""CLI: python -m arxiv_daily {run,fb,interest,consolidate,status}"""
import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import DIGESTS, LOGS, STATE, gitops, html, llm, load_config, memory, obsidian, server, zotero
from .fetch import fetch_announcements, prefilter
from .notify import notify
from .output import write_digest, write_note
from .read import read_paper, score

log = logging.getLogger("arxiv_daily")
SEEN = STATE / "seen.json"


def _setup_logging():
    LOGS.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.StreamHandler(sys.stderr), logging.FileHandler(LOGS / f"{date.today():%Y-%m}.log")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def _load_seen() -> dict:
    return json.loads(SEEN.read_text()) if SEEN.exists() else {}


def _save_seen(seen: dict):
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    SEEN.write_text(json.dumps({k: v for k, v in sorted(seen.items()) if v >= cutoff}, indent=0))


def cmd_run(args, cfg):
    run, models = cfg["run"], cfg["models"]
    synced = memory.sync_note_feedback()
    if synced:
        log.info("picked up %d feedback entries from notes", synced)
    if memory.consolidation_due(cfg["memory"]):
        changed, changelog = memory.consolidate(models["memory"])
        log.info("memory consolidation (changed=%s): %s", changed, changelog)
        gitops.commit(f"memory: consolidate feedback\n\n{changelog}")

    profile = memory.load_profile()
    interests = memory.interests_text()
    announced, papers = fetch_announcements(profile["categories"])
    day = announced or date.today()
    seen = _load_seen()
    fresh = [p for p in papers if p.id not in seen]
    log.info("announcement %s: %d papers, %d unseen", day, len(papers), len(fresh))
    if not fresh:
        log.info("nothing new since the last run (next batch after arXiv's next announcement)")
        latest = html.render_all()
        if latest:
            print(f"Latest digest: {latest}")
            if sys.stdin.isatty() and cfg["notify"]["enabled"]:  # manual run: re-show; launchd: stay quiet
                notify("arXiv: nothing new", f"Showing the latest digest ({latest.stem})", server.page_url(cfg, latest))
        return

    cands = prefilter(fresh, profile, run["prefilter_min"], run["max_candidates"])
    log.info("%d candidates after keyword prefilter", len(cands))
    if args.dry_run:
        for p in cands:
            print(f"{p.kw_score:5.1f}  {p.id}  {p.title}")
        return

    scores = score(cands, interests, memory.recent_feedback_block(cfg["memory"]["feedback_context"]),
                   models["score"])
    ranked = sorted(((p, scores[p.id]) for p in cands if p.id in scores), key=lambda x: -x[1]["score"])
    to_read = [x for x in ranked if x[1]["score"] >= run["read_threshold"]][:run["max_reads"]]
    read_ids = {p.id for p, _ in to_read}
    flagged = [x for x in ranked if x[1]["score"] >= run["flag_threshold"] and x[0].id not in read_ids]
    rest = [x for x in ranked if x[1]["score"] < run["flag_threshold"]]

    def _read(item):
        p, s = item
        try:
            note, src = read_paper(p, interests, models["read"], run["max_fulltext_chars"])
            return p, s, note, write_note(p, day, s, note, src)
        except Exception as e:
            log.warning("reading %s failed: %s", p.id, e)
            return None

    with ThreadPoolExecutor(run["parallel_reads"]) as ex:
        results = list(ex.map(_read, to_read))
    read = [r for r in results if r]
    flagged = sorted(flagged + [x for x, r in zip(to_read, results) if r is None], key=lambda x: -x[1]["score"])

    write_digest(day, len(fresh), len(cands), read, flagged, rest)
    digest = html.render_all()
    for p in fresh:
        seen[p.id] = day.isoformat()
    _save_seen(seen)
    gitops.commit(f"digest {day}: {len(read)} read, {len(flagged)} flagged")
    log.info("wrote %s", digest)
    log.info("usage: %s", llm.usage_summary())

    if cfg["notify"]["enabled"] and (read or flagged):
        top = read[0][0].title if read else flagged[0][0].title
        notify(f"arXiv: {len(read)} must-read, {len(flagged)} to skim", top[:180], server.page_url(cfg, digest))


def cmd_fb(args, cfg):
    e = memory.add_feedback(args.id, args.rating, " ".join(args.note))
    gitops.commit(f"feedback {e['rating']} {e['id']}")
    print(f"recorded {e['rating']} for {e['id']} {e['title'][:70]}")


def cmd_interest(args, cfg):
    changed, changelog = memory.update_interests("explicit instruction from the user",
                                                 " ".join(args.text), cfg["models"]["memory"])
    print(changelog)
    if changed:
        gitops.commit(f"memory: {' '.join(args.text)[:60]}\n\n{changelog}")
    else:
        print("(no change)")


def cmd_consolidate(args, cfg):
    changed, changelog = memory.consolidate(cfg["models"]["memory"])
    print(changelog)
    if changed:
        gitops.commit(f"memory: consolidate feedback\n\n{changelog}")


def cmd_zotero(args, cfg):
    r = zotero.save(args.id, cfg["zotero"], force=args.force, obsidian_cfg=cfg.get("obsidian"))
    if r["status"] == "saved":
        gitops.commit(f"zotero: saved {args.id}")
    print(f"{args.id}: {r['status']} ({r['collection']})" + (f" · Obsidian: {r['obsidian']}" if r.get("obsidian") else ""))


def cmd_obsidian(args, cfg):
    """Write the Obsidian note for an already-saved paper (e.g. papers saved before Obsidian was set up)."""
    entry = obsidian.digest_entry(args.id)
    m = zotero._digest_meta(args.id) or zotero.arxiv_meta(args.id)
    path = obsidian.write(args.id, m, cfg["obsidian"], zotero.saved().get(args.id, {}).get("collection", ""))
    gitops.commit(f"obsidian: note for {args.id}")
    print(path)


def cmd_serve(args, cfg):
    server.serve(cfg)


def cmd_llm_test(args, cfg):
    """Check the LLM connection end to end: key, endpoint, model names, and one tiny JSON round trip."""
    c = cfg["llm"]
    print(f"provider: {c['provider']}  base_url: {c['base_url']}  models: {cfg['models']}")
    if c["provider"] == "openai-compatible":
        print(f"api key: {llm.key_source(c)}")
        try:
            names = llm.list_models(c)
            print("endpoint lists:", ", ".join(names[:12]) or "(nothing)")
            missing = {m for m in cfg["models"].values() if names and m not in names}
            if missing:
                print(f"WARNING: not in that list: {', '.join(sorted(missing))}. Fix [models] in config.toml.")
        except Exception as e:
            print(f"(could not list models: {e})")
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "sum": {"type": "integer"}},
              "required": ["ok", "sum"]}
    out = llm.ask("Return ok=true and sum = 2 + 3.", schema, cfg["models"]["score"])
    print("round trip:", out, "| " + llm.usage_summary())
    if out.get("sum") != 5:
        sys.exit("the model answered, but not correctly. Try another model.")
    print("OK")


def cmd_status(args, cfg):
    p = memory.load_profile()
    fb = memory.load_feedback()
    print(f"categories: {', '.join(p['categories'])}")
    print(f"keywords: {len(p.get('keywords', {}))}, negative: {len(p.get('negative', {}))}, authors: {len(p.get('authors', []))}")
    print(f"feedback entries: {len(fb)} ({sum(e['rating'] == '+' for e in fb)}+ / {sum(e['rating'] == '-' for e in fb)}-)")
    print(f"seen papers: {len(_load_seen())}")


def main():
    ap = argparse.ArgumentParser(prog="arxiv_daily")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="find -> read -> write -> commit -> notify")
    r.add_argument("--dry-run", action="store_true", help="only show keyword candidates; no LLM calls, no writes")
    f = sub.add_parser("fb", help="rate a paper: fb <id> +|- [note...]")
    f.add_argument("id"), f.add_argument("rating"), f.add_argument("note", nargs="*")
    i = sub.add_parser("interest", help='tell memory about a change: interest "now also into X"')
    i.add_argument("text", nargs="+")
    sub.add_parser("consolidate", help="fold new feedback into interests.md now")
    z = sub.add_parser("zotero", help="save a paper to Zotero: zotero <id>")
    z.add_argument("id"), z.add_argument("--force", action="store_true", help="save again even if saved before")
    sub.add_parser("serve", help="run the local helper behind the digest pages")
    o = sub.add_parser("obsidian", help="write the Obsidian note for a paper: obsidian <id>")
    o.add_argument("id")
    sub.add_parser("llm-test", help="check the LLM endpoint, key and model names")
    sub.add_parser("status")
    args = ap.parse_args()

    _setup_logging()
    cfg = load_config()
    try:
        {"run": cmd_run, "fb": cmd_fb, "interest": cmd_interest,
         "consolidate": cmd_consolidate, "status": cmd_status, "zotero": cmd_zotero, "serve": cmd_serve, "obsidian": cmd_obsidian, "llm-test": cmd_llm_test}[args.cmd](args, cfg)
    except Exception as e:
        log.exception("%s failed", args.cmd)
        if args.cmd == "run" and cfg["notify"]["enabled"]:
            notify("arXiv daily FAILED", f"{type(e).__name__}: {e}"[:180] + " — see logs/")
        sys.exit(1)


if __name__ == "__main__":
    main()
