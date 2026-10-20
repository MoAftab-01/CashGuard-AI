"""Only the bundled, public fictional history is accepted in public demo mode."""

import hashlib
import json
from functools import lru_cache

from config import SAMPLE_DATA_PATH, TRANSACTION_COLUMNS
from src.data_processing import Transaction, validate_csv


def transaction_digest(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2000:
        return None
    try:
        canonical = [Transaction.model_validate(row).model_dump(mode="json") for row in rows]
        return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).digest()
    except (ValueError, TypeError):
        return None


@lru_cache(maxsize=1)
def public_fixture():
    """The sole process cache contains public synthetic fixture data, never inputs."""
    raw = SAMPLE_DATA_PATH.read_text(encoding="utf-8-sig")
    imported = validate_csv(SAMPLE_DATA_PATH)
    rows = [{key: row[key] for key in TRANSACTION_COLUMNS} for row in imported.data.to_dict("records")]
    return raw, transaction_digest(rows)


def accepts_public_payload(path, payload):
    if not isinstance(payload, dict):
        return False
    if path == "/api/v1/models/status":
        return set(payload) <= {"model", "timeout_seconds"}
    raw, digest = public_fixture()
    if path == "/api/v1/transactions/csv":
        return payload.get("csv_text") == raw
    candidate = transaction_digest(payload.get("transactions"))
    return candidate is not None and candidate == digest
