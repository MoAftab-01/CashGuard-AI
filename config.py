"""Shared configuration; paths resolve independently of the working directory."""

from pathlib import Path
import sys

if sys.version_info < (3, 11):
    raise RuntimeError("CashGuard AI requires Python 3.11+. Run with the project's .venv interpreter.")

PROJECT_ROOT = Path(__file__).resolve().parent
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "synthetic_transactions.csv"
MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_TRANSACTIONS = 100_000
REQUIRED_COLUMNS = ("date", "description", "amount", "category")
OPTIONAL_COLUMNS = ("transaction_id", "account", "merchant")
TRANSACTION_COLUMNS = (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS)
SYNTHETIC_SEED = 42
SYNTHETIC_START_DATE = "2026-01-01"
SYNTHETIC_DAYS = 210

# Local inference only; environment overrides are validated by OllamaSettings.
DEFAULT_OLLAMA_MODEL = "gemma3:4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
