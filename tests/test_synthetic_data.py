from datetime import date

import pandas as pd
import pytest

from scripts.generate_sample_data import generate_transactions
from src.data_processing import validate_csv


def test_sample_is_reproducible_valid_and_spans_210_days():
    first = generate_transactions()
    pd.testing.assert_frame_equal(first, generate_transactions())
    assert first.to_csv(index=False) != generate_transactions(seed=43).to_csv(index=False)
    result = validate_csv(first.to_csv(index=False))
    assert not result.has_errors and not result.issues
    assert (max(result.data["date"]) - min(result.data["date"])).days == 209
    assert first["transaction_id"].is_unique
    assert {"Income", "Housing", "Subscriptions", "Utilities", "Groceries", "Other"} <= set(first["category"])
    assert (first["description"] == "Unexpected repair").sum() == 3
    assert (first["description"] == "Monthly salary").sum() == 7
    assert all(str(value).startswith("SYN-") for value in first["transaction_id"])


def test_custom_history_and_minimum_days():
    data = generate_transactions(start_date=date(2024, 2, 1), days=180)
    assert data["date"].min() == "2024-02-01"
    with pytest.raises(ValueError, match="180"):
        generate_transactions(days=179)
