# arxiv-daily-agent

A personal arXiv watcher that learns what you care about. Every weekday it finds new papers, has an LLM (DeepSeek by default) read the
promising ones, writes structured notes, commits them to git, and gives you a heads-up. From the digest page, one
click saves a paper to **Zotero** and creates a linked **Obsidian** note.

```
memory ──► find ──► read ──► write ──► save ──► heads-up
interests  arXiv    LLM      notes +   git       macOS notification
+ feedback RSS +    scores   digest    commit    → local digest page
           keywords abstracts, (md/json/html)       ├─ Save to Zotero
                    reads                           ├─ Obsidian note
                    full text                       └─ 👍 / 👎 feedback ─► back into memory
```

The default configuration targets high-redshift galaxies, reionization, Lyman continuum / Lyα, galaxy assembly and
large survey data releases (JWST, HST, Euclid, Roman, ground-based). Edit `memory/interests.md` to make it yours.

## How it works

| Step | What happens | Code |
|---|---|---|
| **Memory** | Interests live in `memory/interests.md` (prose + a keyword profile). Your reactions to papers accumulate in `memory/feedback.jsonl`. | `memory.py` |
| **Find** | Pulls the latest arXiv announcements (new papers and cross-lists) for your categories, then ranks them with a cheap keyword prefilter. | `fetch.py` |
| **Read** | The LLM scores the candidate abstracts 0–10 against your memory, then reads the **full text** (arXiv HTML, PDF via `pdftotext` as a fallback) of the top few and writes a structured note. | `read.py`, `llm.py` |
| **Write** | One note per must-read paper in a fixed format, plus a daily digest as Markdown, JSON and a self-contained HTML page. | `output.py`, `html.py` |
| **Save** | Notes, digests, memory and dedup state are committed to a private local git repo (see below). | `gitops.py` |
| **Heads-up** | A macOS notification opens the digest page. A failed run notifies you too. | `notify.py` |

The model is any **OpenAI-compatible chat API**: DeepSeek by default (cheap), or any gateway that hosts it (OpenRouter,
Together, Fireworks…) by changing `base_url` and the model names in `config.toml`. Replies are JSON-checked against a schema
and retried with the error fed back if invalid. A `claude-code` provider (headless `claude -p`) is also available.
There are no Python dependencies beyond the standard library.

### Memory that adapts
- **Explicit:** `./run.sh interest "starting a project on [CII] in z>6 galaxies"`, or edit `memory/interests.md` by hand.
- **Implicit:** rate papers 👍/👎. On Mondays, or once 15 ratings are pending, the LLM folds the feedback into the
  *Current focus*, *Avoid* and keyword-profile sections. The *Pinned* section is never changed automatically.
  Every change is validated, logged in `memory/changelog.md` and committed, so `./data-git log -p memory/interests.md`
  shows how your interests evolved (`./data-git` is git for your data repo).
- The scorer also sees your most recent ratings, so feedback takes effect the next day.

### Digest page, Zotero and Obsidian
The pipeline writes `digests/YYYY-MM-DD.html`; a small localhost helper serves it at **http://127.0.0.1:8765**.
Cards show score, TL;DR and chips; clicking one opens the full note in a side panel (← → to step, Esc to close).
- **＋ Zotero** saves a preprint item (full metadata, DOI), the PDF, and your reading note as a child note into the
  collection set in `config.toml`. The Zotero desktop app must be running; it is reached through Zotero's built-in
  connector server, so no API key is needed.
- **Obsidian:** every paper saved to Zotero also gets a note in your vault, filed by topic rules (default folder
  `arXiv/`), with links to the Zotero item and PDF. The Zotero note links back. Existing notes are never overwritten.
- **👍 / 👎** record feedback in one click with an optional reason.

## Requirements
- macOS (notifications and the launchd jobs are macOS-specific; the core pipeline is portable)
- Python 3.11+ (standard library only)
- An API key for an OpenAI-compatible endpoint, [DeepSeek](https://platform.deepseek.com) by default (or Claude Code
  installed and logged in, if you set `provider = "claude-code"`)
- Optional: `brew install terminal-notifier` (clickable banners), `brew install poppler` (PDF fallback for papers
  without an arXiv HTML version), the Zotero desktop app, an Obsidian vault

## Quick start
```sh
git clone git@github.com:sphy2016/arxiv-daily-agent.git
cd arxiv-daily-agent

# 1. Make it yours. memory/interests.md is created from examples/interests.md on first run;
#    put machine-specific settings in config.local.toml (layered over config.toml)
./run.sh status                  # first run creates memory/ and your private data repo

# API key: kept outside the repo. A file works for scheduled jobs too (they don't see your shell env).
mkdir -p ~/.config/arxiv-daily && chmod 700 ~/.config/arxiv-daily
pbpaste > ~/.config/arxiv-daily/api_key && chmod 600 ~/.config/arxiv-daily/api_key   # after copying the key
./run.sh llm-test                # checks endpoint, key, model names and one JSON round trip
$EDITOR memory/interests.md      # topics, scoring guidance, arXiv categories, keyword weights
$EDITOR config.local.toml        # e.g. [obsidian] enabled = true, vault = "~/Obsidian"; models, thresholds

# 2. Try it
./run.sh run --dry-run           # shows keyword candidates only: no LLM calls, nothing written
./run.sh                         # full run: score, read, write, commit, notify

# 3. Automate (weekdays after arXiv updates, + the always-on local page server)
./launchd/install.sh             # remove with: ./launchd/install.sh --uninstall
#    or run it on GitHub instead: see "Run it on GitHub Actions" below
```

### Two repos, one folder
This public repo holds only the **code** and the example files. Everything personal (your interests, ratings, notes,
digests, dedup state, `config.local.toml`) is committed automatically to a **second, private repo** whose git dir is
`.git-data` in the same folder, so nothing in the code needs to know about it. This repo's `.gitignore` excludes those
paths, so personal data can't be pushed by accident. Use `./data-git <git args>` to inspect the data repo, and add your
own private remote to it if you want a backup:
```sh
./data-git remote add origin <your-private-repo-url> && ./data-git push -u origin main
```

## Run it on GitHub Actions (instead of your Mac)
The daily run can happen on GitHub's servers, so it no longer depends on your Mac being awake. The workflow lives in
your **private data repo**, checks out this public code next to it, runs the pipeline, and pushes the results back.
Your Mac then pulls them for the local page, Zotero and Obsidian (those need your Mac).

1. Create an empty **private** repo on GitHub (e.g. `arxiv-daily-data`).
2. Copy `examples/github-action/daily.yml` to `.github/workflows/daily.yml` in it, and put your GitHub user name in
   the `repository:` line.
3. In that repo: *Settings > Secrets and variables > Actions > New repository secret*:
   `DEEPSEEK_API_KEY` (required) and `NTFY_TOPIC` (optional, see below).
4. Seed it from your existing data and turn the local daily job off (the Action replaces it):
   ```sh
   ./data-git remote -v             # must be empty or your PRIVATE repo; never the public code repo
   ./data-git remote add origin git@github.com:YOU/arxiv-daily-data.git   # or: remote set-url origin <url>
   mkdir -p .github/workflows && cp examples/github-action/daily.yml .github/workflows/
   $EDITOR .github/workflows/daily.yml    # put your GitHub user name in the repository: line
   ./data-git add -f .github && ./data-git commit -m "Add workflow" && ./data-git push -u origin main
   ./launchd/install.sh --no-daily
   ```
   (Syncing refuses to run if the data repo's `origin` equals the code repo's, so your data can't reach the public repo.)
5. Run it once from the repo's *Actions* tab (*arxiv-daily > Run workflow*) and check the run summary.

From then on the Action runs Monday to Friday at 06:30 UTC, after arXiv's feed rolls over (04:00 UTC in summer, 05:00 in
winter). Your Mac syncs the data repo automatically (on every commit it makes, and every 15 minutes while the page
server runs); `./run.sh sync` does it by hand. The digest is also shown in each run's summary, and GitHub emails you if
a run fails. To get a push on your phone when a digest is ready, install the [ntfy](https://ntfy.sh) app, subscribe to
a long random topic name, and store that name as the `NTFY_TOPIC` secret (anyone who knows the topic can read it).
Cost: roughly 3-5 Actions minutes a day, well inside the free allowance for private repos, plus your API usage.

## Commands
```sh
./run.sh                          # full daily run
./run.sh llm-test                 # check the LLM endpoint, key and model names
./run.sh run --dry-run            # keyword candidates only
./fb <arxiv-id> + "why"           # 👍 (or - for 👎); the note feeds the memory
./run.sh interest "<plain-language change>"
./run.sh consolidate              # fold feedback into interests.md now
./run.sh zotero <arxiv-id>        # save to Zotero (+ Obsidian note)
./run.sh obsidian <arxiv-id>      # (re)create the Obsidian note for a paper
./run.sh serve                    # the page server (launchd runs this for you)
./run.sh sync                     # pull/push the private data repo (digests from the Action, your feedback)
./run.sh status                   # memory / feedback / dedup summary
```
Feedback can also be typed into a note's `feedback:` frontmatter field; it is picked up on the next run.

## Configuration
All knobs are in [`config.toml`](config.toml): prefilter and score thresholds, how many papers get full reads per
day, the LLM endpoint and which model does scoring / reading / memory updates, the Zotero collection and tags, the Obsidian vault
and topic-to-folder rules, and the helper's port. Interests are deliberately **not** in the config; they live in
[`memory/interests.md`](memory/interests.md).

## Repository layout
```
arxiv_daily/        the package: fetch, read, memory, output, html, server, zotero, obsidian, notify, gitops, llm
examples/           interests.md template, copied to memory/ on first run
launchd/install.sh  installs the daily job and the page server (--no-daily when the Action does the daily run)
examples/github-action/daily.yml   the workflow for your private data repo
data-git            git for your private data repo
CLAUDE.md           notes for Claude Code sessions working in this repo

created locally, committed to your private data repo (not this one):
memory/             interests.md (editable), feedback.jsonl, changelog.md
papers/YYYY/MM/     one note per must-read paper
digests/            YYYY-MM-DD.md / .json / .html
state/              dedup, Zotero and Obsidian records
config.local.toml   your machine-specific overrides
```

## Privacy and security
- Paper text is passed to the model as data, and the model has **no tools** (it only returns JSON); the PDF fallback extracts
  text locally with `pdftotext`).
- The page server binds to `127.0.0.1` only, serves just `digests/` and `papers/`, and write endpoints require a
  same-origin request with a custom header.
- Your reading history, ratings, notes and local paths live only in the private data repo (`.git-data`), never in this
  public repository. Check `git status` before pushing if you change `.gitignore`.

## Known limits
- arXiv's RSS feed only covers the latest announcement. If the Mac is off for several announcement days, the next run
  sees only the newest one.
- arXiv announces Sunday to Thursday at 20:00 US Eastern, i.e. Monday to Friday morning in Asia and Europe, so
  Saturday and Sunday runs find nothing new and exit quietly.
- Notes are English. Scores are model judgments; use feedback to calibrate them. With a hosted API, your interest text,
  ratings and the paper text are sent to that provider (DeepSeek's own API is served from China).
