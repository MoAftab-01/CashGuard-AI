from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from src.anomaly_detection import AnomalyResult, detect_anomalies
from src.data_processing import empty_transactions
from src.forecasting import forecast_cash_flow
from src.risk_engine import assess_risk


def at_balance(data, cents, **kwargs):
    opening = Decimal(cents - sum(int(value) for value in data["amount_cents"])) / 100
    return forecast_cash_flow(data, opening, **kwargs)


def factor(result, name):
    return next(item for item in result.factors if item.name == name)


def test_risk_factors_are_bounded_additive_and_explainable(regular_history):
    forecast = at_balance(regular_history, 1000)
    anomaly = detect_anomalies(regular_history)
    result = assess_risk(regular_history, forecast, anomalies=anomaly)
    assert result.score == sum(item.points for item in result.factors)
    assert 0 <= result.score <= 100
    assert all(0 <= item.points <= item.max_points and item.explanation for item in result.factors)
    assert sum(item.max_points for item in result.factors) == 100
    assert {item.name for item in result.factors} == {"projected_shortfall", "low_cash_buffer", "expense_to_income", "spending_volatility", "unusual_activity"}
    assert any("not a credit score" in warning for warning in result.warnings)


def test_negative_forecast_and_positive_threshold_breach_have_distinct_points(transactions):
    data = transactions([(date(2026, 1, 1), "No flow", 0, "Other")])
    negative = assess_risk(data, at_balance(data, -1))
    threshold = assess_risk(data, at_balance(data, 1000, cash_threshold=20))
    assert factor(negative, "projected_shortfall").points == 30
    assert factor(threshold, "projected_shortfall").points == 15
    assert factor(negative, "low_cash_buffer").points == 25


@pytest.mark.parametrize("days_of_cash,points", [(6, 25), (7, 12), (29, 12), (30, 0)])
def test_cash_buffer_boundaries(transactions, days_of_cash, points):
    data = transactions([(date(2026, 1, 1) + timedelta(days=i), "Spend", -1000, "Other") for i in range(40)])
    result = assess_risk(data, at_balance(data, 1000 * days_of_cash))
    assert factor(result, "low_cash_buffer").points == points
    assert factor(result, "low_cash_buffer").observed_value == days_of_cash


@pytest.mark.parametrize("income,points", [(0, 20), (900, 20), (1000, 10), (1250, 10), (2000, 0)])
def test_expense_income_ratio_boundaries(transactions, income, points):
    data = transactions([(date(2026, 1, 1), "Expense", -1000, "Other"),
                         (date(2026, 1, 2), "Income", income, "Income")])
    result = assess_risk(data, at_balance(data, 100000))
    assert factor(result, "expense_to_income").points == points
    if income == 0:
        assert factor(result, "expense_to_income").observed_value is None


def test_volatility_includes_zero_spend_calendar_days(transactions):
    data = transactions([(date(2026, 1, 1), "Bill", -10000, "Other"),
                         (date(2026, 1, 2), "No flow", 0, "Other")])
    result = assess_risk(data, at_balance(data, 100000))
    assert factor(result, "spending_volatility").observed_value == 1
    assert factor(result, "spending_volatility").points == 7


def test_no_history_or_no_anomaly_scores_does_not_imply_low_risk(regular_history):
    empty = empty_transactions()
    forecast = forecast_cash_flow(empty, 0, as_of=date(2026, 1, 1))
    result = assess_risk(empty, forecast)
    assert result.score is None and result.level == "Insufficient data"
    assert result.data_sufficiency == "insufficient"
    partial = assess_risk(regular_history, at_balance(regular_history, 1000000))
    assert not factor(partial, "unusual_activity").evaluated
    assert partial.data_sufficiency == "limited"
    assert any("lower bound" in warning for warning in partial.warnings)


def test_unusual_rate_denominator_excludes_unscored_rows(regular_history):
    forecast = at_balance(regular_history, 100000)
    report = regular_history.copy()
    report["is_anomaly"] = pd.array([pd.NA] * len(report), dtype="boolean")
    report["training_end"] = report["date"].map(lambda day: day - timedelta(days=1))
    report.loc[report.index[-10:], "is_anomaly"] = [True] + [False] * 9
    result = assess_risk(regular_history, forecast, anomalies=AnomalyResult(report, forecast.as_of, ()))
    assert factor(result, "unusual_activity").observed_value == 0.1
    assert factor(result, "unusual_activity").points == 5


def test_risk_cutoff_is_immune_to_future_amounts(regular_history):
    forecast = forecast_cash_flow(regular_history, 1000, as_of=date(2026, 3, 31))
    future_changed = regular_history.copy()
    future_changed.loc[future_changed["date"] > forecast.as_of, "amount_cents"] *= 10000
    assert assess_risk(regular_history, forecast) == assess_risk(future_changed, forecast)


def test_future_or_in_sample_anomaly_reports_are_rejected(regular_history):
    forecast = forecast_cash_flow(regular_history, 0, as_of=date(2026, 3, 31))
    future_report = detect_anomalies(regular_history)
    with pytest.raises(ValueError, match="cutoff"):
        assess_risk(regular_history, forecast, anomalies=future_report)
    report = detect_anomalies(regular_history, as_of=forecast.as_of)
    broken = report.data.copy()
    mask = broken["is_anomaly"].notna()
    broken.loc[mask, "training_end"] = broken.loc[mask, "date"]
    with pytest.raises(ValueError, match="in-sample"):
        assess_risk(regular_history, forecast, anomalies=replace(report, data=broken))
