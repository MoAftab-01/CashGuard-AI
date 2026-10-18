"""CSV validation and normalization with exact, two-decimal monetary values."""

from __future__ import annotations

import csv
import io
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from config import MAX_CSV_BYTES, MAX_TRANSACTIONS, REQUIRED_COLUMNS, TRANSACTION_COLUMNS

logger = logging.getLogger(__name__)
CATEGORY_ALIASES = {
    "salary": "Income", "payroll": "Income", "income": "Income",
    "freelance": "Freelance", "freelancing": "Freelance",
    "rent": "Housing", "housing": "Housing", "utilities": "Utilities",
    "utility": "Utilities", "grocery": "Groceries", "groceries": "Groceries",
    "subscription": "Subscriptions", "subscriptions": "Subscriptions",
    "dining": "Dining", "restaurants": "Dining", "transport": "Transport",
    "transportation": "Transport", "healthcare": "Healthcare",
    "medical": "Healthcare", "shopping": "Shopping", "other": "Other",
}


class Transaction(BaseModel):
    """One transaction in a single, user-selected currency (no FX conversion)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    date: Date
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(max_digits=12, decimal_places=2, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=100)
    transaction_id: str | None = Field(default=None, max_length=200)
    account: str | None = Field(default=None, max_length=200)
    merchant: str | None = Field(default=None, max_length=200)

    @field_validator("date", mode="before")
    @classmethod
    def validate_date(cls, value: object) -> Date:
        if isinstance(value, Date) and type(value) is Date:
            return value
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
            raise ValueError("Use a calendar date in YYYY-MM-DD format")
        return Date.fromisoformat(value.strip())

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Amount must be a number, not a boolean")
        return value

    @field_validator("category")
    @classmethod
    def standardize_category(cls, value: str) -> str:
        normalized = " ".join(value.split()).casefold()
        return CATEGORY_ALIASES.get(normalized, normalized.title())

    @field_validator("transaction_id", "account", "merchant", mode="before")
    @classmethod
    def empty_optional_to_none(cls, value: object) -> object:
        return None if value is None or (isinstance(value, str) and not value.strip()) else value


@dataclass(frozen=True)
class ValidationIssue:
    row: int | None
    field: str
    message: str
    severity: Literal["error", "warning"] = "error"


@dataclass
class ImportResult:
    """Valid rows are a preview only until every blocking error is corrected."""

    data: pd.DataFrame
    issues: list[ValidationIssue] = field(default_factory=list)
    input_rows: int = 0
    duplicates_removed: int = 0

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def empty_transactions() -> pd.DataFrame:
    return pd.DataFrame(columns=[*TRANSACTION_COLUMNS, "amount_cents", "source_row"])


def validate_csv(
    source: bytes | str | Path, *, remove_ambiguous_duplicates: bool = False
) -> ImportResult:
    """Read a UTF-8 CSV, preserving IDs as text and reporting ending line numbers.

    Identical records sharing (account, transaction_id) are deduplicated. All
    conflicting records for such an ID are excluded and block analytics. Repeated
    ID-less records are kept with a warning unless explicitly opted into removal.
    No input files are changed. Unknown columns are ignored with a warning.
    """
    result = ImportResult(empty_transactions())
    try:
        if isinstance(source, Path):
            with source.open("rb") as handle:
                raw = handle.read(MAX_CSV_BYTES + 1)
        else:
            raw = source.encode("utf-8") if isinstance(source, str) else source
        if len(raw) > MAX_CSV_BYTES:
            raise ValueError("CSV exceeds the 10 MiB limit")
        text = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = [name.strip().lower() for name in next(reader, [])]
        if not header or any(not name for name in header):
            raise ValueError("CSV must have nonblank column headers")
        if len(header) != len(set(header)):
            raise ValueError("CSV has duplicate column headers after normalization")
        missing = set(REQUIRED_COLUMNS) - set(header)
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
        if set(header) - set(TRANSACTION_COLUMNS):
            result.issues.append(ValidationIssue(1, "columns", "Extra columns are ignored", "warning"))
        records: list[tuple[int, Transaction]] = []
        for values in reader:
            if not values:  # Physically empty lines are ignored, not comma-only records.
                continue
            result.input_rows += 1
            if result.input_rows > MAX_TRANSACTIONS:
                raise ValueError(f"CSV exceeds the {MAX_TRANSACTIONS:,} transaction limit")
            row = reader.line_num
            if len(values) != len(header):
                result.issues.append(ValidationIssue(row, "row", "Field count does not match headers"))
                continue
            payload = {key: val for key, val in zip(header, values) if key in TRANSACTION_COLUMNS}
            try:
                records.append((row, Transaction.model_validate(payload)))
            except ValidationError as exc:
                for error in exc.errors(include_input=False, include_url=False):
                    result.issues.append(ValidationIssue(row, str(error["loc"][0]), error["msg"]))
        if not result.input_rows:
            result.issues.append(ValidationIssue(None, "file", "CSV contains no transactions"))
        _resolve_duplicates(records, result, remove_ambiguous_duplicates)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        # Fatal file errors invalidate the whole parse; never return a truncated dataset.
        result.data = empty_transactions()
        result.issues.append(ValidationIssue(None, "file", str(exc)))
    logger.info("CSV validation: rows=%d accepted=%d errors=%s removed=%d",
                result.input_rows, len(result.data), result.has_errors, result.duplicates_removed)
    return result


def _resolve_duplicates(
    records: list[tuple[int, Transaction]], result: ImportResult, remove_ambiguous: bool
) -> None:
    groups: dict[tuple[str | None, str], list[tuple[int, Transaction]]] = defaultdict(list)
    for row, transaction in records:
        if transaction.transaction_id is not None:
            groups[(transaction.account, transaction.transaction_id)].append((row, transaction))
    conflicts: set[tuple[str | None, str]] = set()
    for key, group in groups.items():
        if len({tuple(t.model_dump().values()) for _, t in group}) > 1:
            conflicts.add(key)
            for row, _ in group:
                result.issues.append(ValidationIssue(row, "transaction_id", "Conflicting records share this account and ID; correct the source"))
    seen: set[tuple[object, ...]] = set()
    accepted: list[dict[str, object]] = []
    for row, transaction in records:
        if (transaction.account, transaction.transaction_id) in conflicts:
            continue
        signature = tuple(transaction.model_dump().values())
        if signature in seen:
            remove = transaction.transaction_id is not None or remove_ambiguous
            result.issues.append(ValidationIssue(row, "duplicate", "Repeated normalized record removed" if remove else "Possible duplicate kept: no transaction ID; review before removing", "warning"))
            if remove:
                result.duplicates_removed += 1
                continue
        seen.add(signature)
        accepted.append({**transaction.model_dump(), "amount_cents": int(transaction.amount * 100), "source_row": row})
    if accepted:
        result.data = pd.DataFrame(accepted).sort_values(["date", "source_row"], kind="stable").reset_index(drop=True)
