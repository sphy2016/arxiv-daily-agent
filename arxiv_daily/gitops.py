"""Save step: commit your data (memory, notes, digests, state) to a private git repo.

Two layouts:
  - local (default): the code repo is `.git`; your data lives in a second repo whose git dir is `.git-data` and whose
    work tree is this same folder. Inspect it with ./data-git (e.g. ./data-git log -p memory/interests.md).
  - CI: $ARXIV_DAILY_DATA points at a clone of the private data repo (a normal `.git`); the workflow pushes it.
If the data repo has a remote ("origin"), commits are also synced to it (pull --rebase, then push), best effort.
"""
import logging
import subprocess

from . import DATA, ROOT

log = logging.getLogger("arxiv_daily")
SEPARATE = DATA != ROOT
GIT_DIR = DATA / ".git-data"
TRACKED = ["memory", "papers", "digests", "state/seen.json", "state/memory_state.json", "state/zotero.json",
           "state/obsidian.json", "config.local.toml", ".github"]


def git(*args):
    base = ["git"] if SEPARATE else ["git", "--git-dir", str(GIT_DIR), "--work-tree", str(DATA)]
    return subprocess.run([*base, *args], cwd=DATA, capture_output=True, text=True)


def _ensure_repo():
    if not SEPARATE and not GIT_DIR.exists():
        subprocess.run(["git", "--git-dir", str(GIT_DIR), "init", "-q", "-b", "main"], capture_output=True)
        git("config", "core.bare", "false")


def _url(cmd: list[str], cwd) -> str:
    r = subprocess.run([*cmd, "remote", "get-url", "origin"], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip().removesuffix(".git").lower() if r.returncode == 0 else ""


def has_remote() -> bool:
    """True if the data repo has an origin that is NOT the public code repo (never publish data there)."""
    url = _url(["git", "--git-dir", str(GIT_DIR), "--work-tree", str(DATA)] if not SEPARATE else ["git"], DATA)
    if not url:
        return False
    if not SEPARATE and url == _url(["git"], ROOT):
        log.warning("data repo's origin is the same as the code repo's (%s): refusing to sync. "
                    "Point it at your PRIVATE data repo: ./data-git remote set-url origin <url>", url)
        return False
    return True


def sync() -> bool:
    """Rebase onto the remote, then push. Returns False (and logs) if anything fails; never raises."""
    if not has_remote():
        return True
    for step in (("pull", "--rebase", "--autostash", "-q", "origin", "main"), ("push", "-q", "origin", "main")):
        r = git(*step)
        if r.returncode != 0:
            log.warning("data repo sync (%s) failed: %s", step[0], r.stderr.strip()[:300])
            return False
    return True


def commit(message: str) -> bool:
    _ensure_repo()
    paths = [p for p in TRACKED if (DATA / p).exists()]
    git("add", "-f", "--", *paths)  # -f: the public repo's .gitignore lists these paths
    if git("diff", "--cached", "--quiet").returncode == 0:
        return False
    r = git("commit", "-m", message)
    if r.returncode != 0:
        raise RuntimeError(f"git commit failed: {r.stderr.strip()}")
    if not SEPARATE:  # in CI the workflow does the final push itself
        sync()
    return True
