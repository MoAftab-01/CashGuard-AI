from decimal import Decimal

import pytest

from src.data_processing import empty_transactions, validate_csv
from src.metrics import balance_history, calculate_metrics, category_expenses, money_to_cents, monthly_summary


def sample():
    return validate_csv("date,description,amount,category\n2026-01-01,Pay,1000.10,Income\n2026-01-01,Food,-100.20,Groceries\n2026-02-02,Rent,-200.30,Housing\n").data


def test_exact_metrics_reconcile_to_opening_balance():
    metrics = calculate_metrics(sample(), "500.05")
    assert metrics.total_income == Decimal("1000.10")
    assert metrics.total_expenses == Decimal("300.50")
    assert metrics.net_cash_flow == Decimal("699.60")
    assert metrics.estimated_balance == Decimal("1199.65")
    assert metrics.transaction_count == 3
    assert str(metrics.start_date) == "2026-01-01"


def test_small_amounts_do_not_accumulate_float_error():
    data = validate_csv("date,description,amount,category\n2026-01-01,A,0.10,Income\n2026-01-01,B,0.20,Income\n2026-01-01,C,-0.30,Other\n").data
    assert calculate_metrics(data, "0").estimated_balance == Decimal("0.00")


def test_daily_and_monthly_reconciliation():
    data = sample()
    monthly = monthly_summary(data)
    assert monthly["month"].tolist() == ["2026-01", "2026-02"]
    assert monthly["net"].tolist() == [899.9, -200.3]
    assert balance_history(data, "500.05")["estimated_balance"].tolist() == [1399.95, 1199.65]
    assert category_expenses(data)["expenses"].tolist() == [200.3, 100.2]


def test_empty_data_and_negative_opening_balance():
    data = empty_transactions()
    metrics = calculate_metrics(data, "-100.25")
    assert metrics.estimated_balance == Decimal("-100.25")
    assert metrics.start_date is None and metrics.end_date is None
    assert monthly_summary(data).empty
    assert category_expenses(data).empty
    assert balance_history(data, "-100.25").empty


@pytest.mark.parametrize("amount", ["nan", "inf", "bad", "", "1.001", "10000000000", True])
def test_invalid_opening_balance(amount):
    with pytest.raises(ValueError):
        money_to_cents(amount)


def test_expense_only_and_income_only():
    for amount in ("10.25", "-10.25"):
        data = validate_csv(f"date,description,amount,category\n2026-01-01,Entry,{amount},Other\n").data
        metrics = calculate_metrics(data, 0)
        assert metrics.net_cash_flow == Decimal(amount)
        assert metrics.total_income >= 0 and metrics.total_expenses >= 0
