"""Central filesystem locations for the J-Search project."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / 'data'
OUTPUT_DIR = ROOT_DIR / 'output'

DB_PATH = DATA_DIR / 'jsearch.db'
DASHBOARD_PATH = OUTPUT_DIR / 'dashboard.html'
DASHBOARD_STATIC_DIR = ROOT_DIR / 'app' / 'dashboard_static'
