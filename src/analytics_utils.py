"""Small shared contracts for the UI-independent, date-bounded analytics modules."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from numbers import Integral

import pandas as pd


def positive_integer(value: int, name: str, maximum: int = 3660) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return int(value)


def round_cents(value: Decimal | int) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def transaction_snapshot(data: pd.DataFrame, as_of: date | None = None) -> tuple[pd.DataFrame, date]:
    """Copy validated transactions known by an explicit inclusive calendar cutoff.

    Callers must not pass previews from failed imports. Validate basic analytic
    columns as a defensive API boundary. No future amounts enter validation,
    aggregations, fit statistics or opening-balance reconstruction.
    """
    required = {"date", "amount_cents", "category", "description"}
    if not required <= set(data.columns):
        raise ValueError(f"Missing analytics columns: {', '.join(sorted(required - set(data.columns)))}")
    if as_of is not None and type(as_of) is not date:
        raise ValueError("as_of must be a datetime.date")
    if any(type(value) is not date for value in data["date"]):
        raise ValueError("Use validated calendar dates, not timestamps or strings")
    if as_of is None:
        if data.empty:
            raise ValueError("An explicit as_of date is required for empty history")
        as_of = max(data["date"])
    snapshot = data.loc[data["date"] <= as_of].copy()
    for column in ("category", "description"):
        if any(not isinstance(value, str) or not value.strip() for value in snapshot[column]):
            raise ValueError(f"{column} must contain nonblank text")
    if any(isinstance(value, bool) or not isinstance(value, Integral) or abs(value) >= 10**12
           for value in snapshot["amount_cents"]):
        raise ValueError("amount_cents must contain bounded integer cents from validated transactions")
    return snapshot.sort_values("date", kind="stable").reset_index(drop=True), as_of


def calendar_days(start: date, count: int) -> list[date]:
    try:
        return [start + timedelta(days=offset) for offset in range(count)]
    except OverflowError as exc:
        raise ValueError("Requested calendar range exceeds supported dates") from exc
