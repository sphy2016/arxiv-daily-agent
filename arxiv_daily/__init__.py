"""Personal arXiv watcher: memory -> find -> read -> write -> git."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY = ROOT / "memory"
PAPERS = ROOT / "papers"
DIGESTS = ROOT / "digests"
STATE = ROOT / "state"
LOGS = ROOT / "logs"


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
    local = ROOT / "config.local.toml"
    if local.exists():
        with open(local, "rb") as f:
            _merge(cfg, tomllib.load(f))
    return cfg
