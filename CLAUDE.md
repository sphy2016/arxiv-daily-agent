# arxiv-daily: notes for Claude sessions in this repo

Personal arXiv watcher for an astronomer (high-z galaxies, reionization, LyC/Lyα, galaxy assembly, survey data releases).
The pipeline is `python3 -m arxiv_daily run` (see README.md). The headless `claude -p` calls are in `arxiv_daily/llm.py`.

- When the user tells you their interests changed, update `memory/interests.md`. Keep the section structure, never drop
  *Pinned* items unless explicitly asked, and keep the ```toml profile block valid. Its keys are single-quoted regex literals.
  Check it with `python3 -c "from arxiv_daily import memory; memory.load_profile()"`, then commit with a `memory: ...` message.
- To record a reaction to a paper: `./fb <id> +|- "note"`.
- Generated files (`papers/`, `digests/`, `state/seen.json`) are written by the pipeline. Don't hand-edit them, except a note's `feedback:` field.
- Two git repos share this folder: `.git` is the public code repo, `.git-data` is the private data repo (memory, notes,
  digests, state, config.local.toml). `gitops.commit` writes to the data repo; use `./data-git` to inspect it. Never `git add`
  personal data in the public repo; its `.gitignore` excludes it.
- Put machine-specific settings in `config.local.toml`, not `config.toml`, because the latter is public.
