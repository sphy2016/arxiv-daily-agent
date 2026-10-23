"""Save step: commit your data (memory, notes, digests, state) to a private local git repo.

The code lives in the public repo (.git); your data lives in a second repo whose git dir is .git-data and whose
work tree is this same folder, so no paths change. Inspect it with ./data-git (e.g. ./data-git log -p memory/interests.md).
"""
import subprocess

from . import ROOT

GIT_DIR = ROOT / ".git-data"
TRACKED = ["memory", "papers", "digests", "state/seen.json", "state/memory_state.json", "state/zotero.json",
           "state/obsidian.json", "config.local.toml"]


def git(*args):
    return subprocess.run(["git", "--git-dir", str(GIT_DIR), "--work-tree", str(ROOT), *args],
                          cwd=ROOT, capture_output=True, text=True)


def _ensure_repo():
    if not GIT_DIR.exists():
        subprocess.run(["git", "--git-dir", str(GIT_DIR), "init", "-q", "-b", "main"], capture_output=True)
        git("config", "core.bare", "false")


def commit(message: str) -> bool:
    _ensure_repo()
    paths = [p for p in TRACKED if (ROOT / p).exists()]
    git("add", "-f", "--", *paths)  # -f: the public repo's .gitignore lists these paths
    if git("diff", "--cached", "--quiet").returncode == 0:
        return False
    r = git("commit", "-m", message)
    if r.returncode != 0:
        raise RuntimeError(f"git commit failed: {r.stderr.strip()}")
    return True
