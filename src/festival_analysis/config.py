from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SOURCE_DATA_DIR = REPO_ROOT / "source-data"
FESTIVAL_NAMES_CSV = SOURCE_DATA_DIR / "festival-names.csv"
FESTIVALS_CSV = SOURCE_DATA_DIR / "festivals.csv"
COUNTRIES_CSV = SOURCE_DATA_DIR / "countries.csv"

DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "festival.duckdb"

CACHE_DIR = REPO_ROOT / ".cache" / "ra"

RA_ENDPOINT = "https://ra.co/graphql"
RA_USER_AGENT = "festival-analysis/0.1 (+https://github.com/local)"
