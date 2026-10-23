"""Personal arXiv watcher: memory -> find -> read -> write -> git."""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # the code
DATA = Path(os.environ.get("ARXIV_DAILY_DATA") or ROOT).resolve()   # your data; a separate repo in CI
MEMORY = DATA / "memory"
PAPERS = DATA / "papers"
DIGESTS = DATA / "digests"
STATE = DATA / "state"
LOGS = DATA / "logs"


for _d in (MEMORY, PAPERS, DIGESTS, STATE, LOGS):
    _d.mkdir(exist_ok=True)


def _merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        base[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def load_config() -> dict:
    """config.toml (shared defaults, public) overlaid with config.local.toml (your machine, private data repo)."""
    with open(ROOT / "config.toml", "rb") as f:
        cfg = tomllib.load(f)
    local = DATA / "config.local.toml"
    if local.exists():
        with open(local, "rb") as f:
            _merge(cfg, tomllib.load(f))
    return cfg
