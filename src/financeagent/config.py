"""Environment-driven configuration and API clients (replaces the notebook's getpass cells)."""

import os
import tempfile
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# .env.local (gitignored, holds real keys) wins over .env
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv(PROJECT_ROOT / ".env")


def _writable_data_dir() -> Path:
    configured = os.environ.get("FINANCEAGENT_DATA_DIR")
    if configured:
        return Path(configured).resolve()
    default = PROJECT_ROOT / "data"
    try:
        default.mkdir(parents=True, exist_ok=True)
        return default.resolve()
    except OSError:
        # Read-only filesystem (e.g. serverless). Note: /tmp is ephemeral there,
        # so the SQLite ledger and file sandbox won't survive between invocations.
        return Path(tempfile.gettempdir()) / "financeagent-data"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")

MODEL = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-pro")

DATA_DIR = _writable_data_dir()
SANDBOX_DIR = DATA_DIR / "sandbox"
DB_PATH = DATA_DIR / "finance.db"

# The static frontend lives next to pyproject.toml in the repo; when the package
# is imported from a bundle (e.g. serverless), fall back to the working directory.
FRONTEND_DIR = next(
    (p for p in (PROJECT_ROOT / "frontend", Path.cwd() / "frontend") if p.is_dir()),
    None,
)

FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"


@lru_cache(maxsize=1)
def get_openai_client():
    from openai import OpenAI

    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill in your keys.")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)


@lru_cache(maxsize=1)
def get_tavily_client():
    from tavily import TavilyClient

    return TavilyClient(api_key=TAVILY_API_KEY)
