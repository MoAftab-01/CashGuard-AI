"""Generate fictional activity; randomness is only for sample data, never forecasts."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import SAMPLE_DATA_PATH, SYNTHETIC_DAYS, SYNTHETIC_SEED, SYNTHETIC_START_DATE

logger = logging.getLogger(__name__)


def generate_transactions(
    start_date: date = date.fromisoformat(SYNTHETIC_START_DATE),
    days: int = SYNTHETIC_DAYS,
    seed: int = SYNTHETIC_SEED,
) -> pd.DataFrame:
    """Return at least 180 calendar days of reproducible single-currency activity."""
    if days < 180:
        raise ValueError("Generate at least 180 days of history")
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []

    def add(day: date, description: str, cents: int, category: str, merchant: str) -> None:
        rows.append({"date": day.isoformat(), "description": description,
                     "amount": f"{Decimal(cents) / 100:.2f}", "category": category,
                     "transaction_id": f"SYN-{len(rows) + 1:06d}",
                     "account": "Synthetic checking", "merchant": merchant})

    # Fixed schedule exposes recurring patterns for future modeling; all names fictional.
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        if day.day == 1:
            add(day, "Monthly salary", 420000, "Income", "Example Studio")
        if day.day == 3:
            add(day, "Monthly rent", -140000, "Housing", "Example Property")
        if day.day == 7:
            add(day, "Streaming subscription", -1599, "Subscriptions", "Example Stream")
        if day.day == 10:
            add(day, "Utilities bill", -int(rng.integers(12000, 20001)), "Utilities", "Example Utilities")
        if day.day == 15:
            add(day, "Internet subscription", -5500, "Subscriptions", "Example Internet")
        if day.day == 20 and rng.random() < 0.75:
            add(day, "Freelance project payment", int(rng.integers(30000, 90001)), "Freelance", "Example Client")
        if day.weekday() == 5:
            add(day, "Weekly groceries", -int(rng.integers(4500, 11001)), "Groceries", "Example Market")
        if day.weekday() < 5 and rng.random() < 0.55:
            add(day, "Local commute", -int(rng.integers(300, 1001)), "Transport", "Example Transit")
        if rng.random() < 0.24:
            add(day, "Meal out", -int(rng.integers(1200, 4501)), "Dining", "Example Cafe")
        if offset in (47, 119, 173):
            add(day, "Unexpected repair", -int(rng.integers(35000, 95001)), "Other", "Example Repairs")
        if offset == 90:
            add(day, "Medical appointment", -18500, "Healthcare", "Example Clinic")
        if offset in (0, days - 1):
            add(day, "Household supplies", -2500, "Shopping", "Example Supplies")
    return pd.DataFrame(rows).sort_values(["date", "transaction_id"], kind="stable").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=SAMPLE_DATA_PATH)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date.fromisoformat(SYNTHETIC_START_DATE))
    parser.add_argument("--days", type=int, default=SYNTHETIC_DAYS)
    parser.add_argument("--seed", type=int, default=SYNTHETIC_SEED)
    args = parser.parse_args()
    if args.days < 180:
        parser.error("--days must be at least 180")
    frame = generate_transactions(args.start_date, args.days, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False, lineterminator="\n")
    logger.info("Generated %d fictional transactions over %d days at %s", len(frame), args.days, args.output)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
