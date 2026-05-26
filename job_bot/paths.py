"""Project root and standard data paths."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
TRACKER_DIR = DATA_DIR / "trackers"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.json"
JOB_CATEGORIES_PATH = CONFIG_DIR / "job_categories.json"
ENV_PATH = ROOT / ".env"
