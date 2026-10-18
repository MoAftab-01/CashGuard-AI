"""Fixed-seed fictional benchmarks. Ground truth never appears in feature data."""

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from src.analytics_utils import positive_integer
from src.data_processing import validate_csv


@dataclass(frozen=True)
class SyntheticBenchmark:
    train: pd.DataFrame
    test: pd.DataFrame
    labels: pd.DataFrame


def synthetic_csv(rows=1000, *, days=180, seed=42) -> bytes:
    """Mixed income/expenses with unique IDs, variable costs and calendar gaps."""
    positive_integer(rows, "rows", 100_000)
    positive_integer(days, "days", 3660)
    rng = np.random.default_rng(seed)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "description", "amount", "category", "transaction_id"])
    categories = [("Groceries", -2400), ("Transport", -800), ("Shopping", -6500), ("Income", 16000)]
    for index in range(rows):
        day = date(2025, 1, 1) + timedelta(days=index * days // rows)
        category, typical = categories[index % len(categories)]
        cents = int(round(typical * rng.lognormal(0, 0.3)))
        writer.writerow([day, f"Fictional {category}", Decimal(cents) / 100, category, f"BENCH-{index:07d}"])
    return output.getvalue().encode("utf-8")


def anomaly_benchmark(*, seed=42) -> SyntheticBenchmark:
    """120 training days, then 60 holdout days, four transactions per day.

    Predeclared policy: multiply the first (grocery expense) on every fifth
    holdout day by 12. Twelve injected large expenses out of 240 test rows.
    Other financial unusualness remains unlabeled: this is deliberately narrow.
    """
    imported = validate_csv(synthetic_csv(720, days=180, seed=seed))
    if imported.has_errors:
        raise RuntimeError("Internal synthetic benchmark failed validation")
    frame = imported.data.copy()
    cutoff = date(2025, 1, 1) + timedelta(days=119)
    train, test = frame.loc[frame["date"] <= cutoff].copy(), frame.loc[frame["date"] > cutoff].copy()
    injected = np.asarray([(day - cutoff).days % 5 == 0 and category == "Groceries"
                           for day, category in zip(test["date"], test["category"])], dtype=bool)
    test.loc[injected, "amount_cents"] *= 12
    test["amount"] = test["amount_cents"].map(lambda cents: Decimal(int(cents)) / 100)
    labels = pd.DataFrame({"transaction_id": test["transaction_id"].tolist(), "is_injected": injected})
    return SyntheticBenchmark(train.reset_index(drop=True), test.reset_index(drop=True), labels)
