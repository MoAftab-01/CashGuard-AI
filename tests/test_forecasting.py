from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.data_processing import empty_transactions
from src.forecasting import forecast_cash_flow, rolling_backtest


def test_monthly_projection_reconciles_and_does_not_double_count(regular_history):
    before = regular_history.copy(deep=True)
    result = forecast_cash_flow(regular_history, "1000.00")
    assert result.as_of == date(2026, 4, 30)
    assert len(result.daily) == 30
    assert result.current_balance_cents == 780000
    assert result.daily["inflow_cents"].sum() == 300000
    assert result.daily["outflow_cents"].sum() == 130000
    assert result.daily.iloc[-1]["balance_cents"] == 950000
    assert len(result.recurring_patterns) == 2
    assert {pattern.occurrences for pattern in result.recurring_patterns} == {4}
    assert result.daily.iloc[0]["date"] == date(2026, 5, 1)
    assert result.daily.iloc[-1]["date"] == date(2026, 5, 30)
    assert np.array_equal(result.daily["balance_cents"], result.current_balance_cents + result.daily["net_cents"].cumsum())
    pd.testing.assert_frame_equal(before, regular_history)
    pd.testing.assert_frame_equal(result.daily, forecast_cash_flow(regular_history, "1000.00").daily)


def test_forecast_excludes_future_from_balance_patterns_and_spending(regular_history, transactions):
    cutoff = date(2026, 3, 31)
    prior = regular_history.loc[regular_history["date"] <= cutoff]
    poison = transactions([(date(2026, 4, 1), "Salary", 999999999, "Income"),
                           (date(2026, 4, 2), "Future expense", -987654321, "Other")])
    first = forecast_cash_flow(prior, 100, as_of=cutoff)
    second = forecast_cash_flow(pd.concat([regular_history, poison]), 100, as_of=cutoff)
    pd.testing.assert_frame_equal(first.daily, second.daily)
    assert first.events == second.events
    assert first.recurring_patterns == second.recurring_patterns
    assert first.current_balance_cents == second.current_balance_cents
    assert first.assumptions == second.assumptions


def test_month_end_does_not_drift_after_february(transactions):
    data = transactions([(date(2026, 1, 31), "Pay", 10000, "Income"),
                         (date(2026, 2, 28), "Pay", 10000, "Income"),
                         (date(2026, 3, 31), "Pay", 10000, "Income")])
    result = forecast_cash_flow(data, 0, horizon_days=62)
    assert [event.date for event in result.events if event.kind == "recurring"] == [date(2026, 4, 30), date(2026, 5, 31)]


@pytest.mark.parametrize("spacing,cadence", [(7, "weekly"), (14, "biweekly")])
def test_supported_periods(transactions, spacing, cadence):
    start = date(2026, 1, 1)
    data = transactions([(start + timedelta(days=spacing * offset), "Bill", -5000, "Subscriptions") for offset in range(4)])
    result = forecast_cash_flow(data, 0)
    assert result.recurring_patterns[0].cadence == cadence
    assert result.events[0].date == start + timedelta(days=spacing * 4)
    assert all(event.kind == "recurring" for event in result.events)


def test_irregular_income_excluded_unless_explicitly_enabled(transactions):
    data = transactions([(date(2026, 1, 1), "Project A", 10000, "Freelance"),
                         (date(2026, 1, 10), "Project B", 20000, "Freelance")])
    conservative = forecast_cash_flow(data, 0)
    assert conservative.daily["inflow_cents"].sum() == 0
    assert any("irregular income" in warning.lower() for warning in conservative.warnings)
    opted_in = forecast_cash_flow(data, 0, include_irregular_income=True)
    assert opted_in.daily["inflow_cents"].sum() == 90000


def test_inadequate_or_missed_recurring_evidence_is_not_scheduled(transactions):
    data = transactions([(date(2026, month, 1), "Pay", 10000, "Income") for month in (1, 2)])
    assert not forecast_cash_flow(data, 0).recurring_patterns
    data = transactions([(date(2026, month, 1), "Pay", 10000, "Income") for month in (1, 2, 3)])
    stale = forecast_cash_flow(data, 0, as_of=date(2026, 4, 10))
    assert not stale.recurring_patterns
    assert any("stale" in warning.lower() for warning in stale.warnings)


def test_variable_amounts_and_skipped_months_do_not_imply_regular_payments(transactions):
    variable = transactions([(date(2026, month, 1), "Pay", cents, "Income")
                             for month, cents in [(1, 10000), (2, 50000), (3, 10000)]])
    missing = transactions([(date(2026, month, 1), "Pay", 10000, "Income") for month in (1, 2, 4)])
    assert not forecast_cash_flow(variable, 0).recurring_patterns
    assert not forecast_cash_flow(missing, 0).recurring_patterns


def test_empty_and_future_only_history_use_opening_balance(transactions):
    for data in [empty_transactions(), transactions([(date(2027, 1, 1), "Future", -50000, "Other")])]:
        result = forecast_cash_flow(data, "123.45", as_of=date(2026, 1, 1), cash_threshold=200)
        assert result.daily["balance_cents"].tolist() == [12345] * 30
        assert len(result.shortage_dates) == 30
        assert result.history_days == result.history_rows == 0
        assert any("No history" in warning for warning in result.warnings)
    with pytest.raises(ValueError, match="explicit as_of"):
        forecast_cash_flow(empty_transactions(), 0)


def test_threshold_is_strict_and_sparse_spending_allocates_fractional_cents(transactions):
    data = transactions([(date(2026, 1, 1), "Tiny bill", -1, "Other"),
                         (date(2026, 1, 3), "No flow", 0, "Other")])
    result = forecast_cash_flow(data, "1.01", horizon_days=3, cash_threshold="1.00")
    assert result.daily["outflow_cents"].tolist() == [0, 1, 0]
    assert result.daily["balance_cents"].tolist() == [100, 99, 99]
    assert len(result.shortage_dates) == 2
    assert any("Insufficient history" in warning for warning in result.warnings)


def test_lookback_does_not_drop_older_balance_movements(regular_history):
    whole = forecast_cash_flow(regular_history, 0)
    recent = forecast_cash_flow(regular_history, 0, lookback_days=30)
    assert whole.current_balance_cents == recent.current_balance_cents
    assert recent.history_days == 30
    assert not recent.recurring_patterns


@pytest.mark.parametrize("kwargs", [{"horizon_days": 0}, {"horizon_days": 366}, {"horizon_days": True},
                                    {"lookback_days": 0}, {"include_irregular_income": "yes"},
                                    {"cash_threshold": "nan"}, {"as_of": "2026-01-01"}])
def test_invalid_forecast_controls(regular_history, kwargs):
    with pytest.raises(ValueError):
        forecast_cash_flow(regular_history, 0, **kwargs)


def test_backtest_uses_complete_future_folds_and_computes_real_errors(regular_history):
    result = rolling_backtest(regular_history, 0)
    assert len(result.folds) == 1
    assert len(result.predictions) == 30
    assert result.metrics == {"net_mae": 0, "net_rmse": 0, "balance_mae": 0, "balance_rmse": 0}
    assert all(result.predictions["cutoff"] < result.predictions["date"])
    assert result.folds.iloc[0]["train_end"] < result.folds.iloc[0]["test_start"]
    assert result.folds.iloc[0]["test_end"] <= regular_history["date"].max()


def test_backtest_predictions_do_not_learn_from_heldout_amounts(regular_history):
    cutoff = date(2026, 3, 31)
    changed = regular_history.copy(deep=True)
    changed.loc[changed["date"] > cutoff, "amount_cents"] *= 100
    a = rolling_backtest(regular_history)
    b = rolling_backtest(changed)
    columns = ["cutoff", "date", "predicted_net_cents", "predicted_balance_cents"]
    pd.testing.assert_frame_equal(a.predictions[columns], b.predictions[columns])
    errors = (b.predictions["predicted_net_cents"] - b.predictions["actual_net_cents"]) / 100
    assert b.metrics["net_mae"] == pytest.approx(np.abs(errors).mean())
    assert b.metrics["net_rmse"] == pytest.approx(np.sqrt((errors**2).mean()))
    assert b.metrics["net_mae"] > 0


def test_sparse_backtest_has_no_fabricated_metrics_and_overlap_is_disclosed(regular_history):
    result = rolling_backtest(regular_history, min_history_days=120)
    assert result.predictions.empty and result.folds.empty
    assert all(value is None for value in result.metrics.values())
    overlap = rolling_backtest(regular_history, min_history_days=60, step_days=15)
    assert any("Overlapping" in warning for warning in overlap.warnings)
    assert len(overlap.folds) == 3


def test_malformed_analytics_input_is_rejected(regular_history):
    with pytest.raises(ValueError, match="Missing analytics"):
        forecast_cash_flow(regular_history.drop(columns=["amount_cents"]), 0)
    bad = regular_history.copy()
    bad["amount_cents"] = bad["amount_cents"].astype(float) + 0.1
    with pytest.raises(ValueError, match="integer cents"):
        forecast_cash_flow(bad, 0)


def test_account_schedules_are_not_conflated(transactions):
    data = transactions([(date(2026, month, 1), "Pay", cents, "Income")
                         for month in (1, 2, 3) for cents in (10000, 30000)])
    data["account"] = ["A", "B"] * 3
    result = forecast_cash_flow(data, 0, horizon_days=31)
    assert len(result.recurring_patterns) == 2
    assert result.daily["inflow_cents"].sum() == 40000


def test_calendar_bounds_are_explicit_and_out_of_range_recurrences_are_safe(transactions):
    data = transactions([(date(9999, month, 1), "Pay", 10000, "Income") for month in (10, 11, 12)])
    assert len(forecast_cash_flow(data, 0, horizon_days=1).daily) == 1
    with pytest.raises(ValueError, match="calendar range"):
        forecast_cash_flow(data, 0, as_of=date.max, horizon_days=1)


def test_backtest_cutoff_ignores_later_observations(regular_history):
    cutoff = date(2026, 3, 31)
    full = rolling_backtest(regular_history, as_of=cutoff, min_history_days=60)
    truncated = rolling_backtest(regular_history.loc[regular_history["date"] <= cutoff], min_history_days=60)
    pd.testing.assert_frame_equal(full.predictions, truncated.predictions)
    assert full.metrics == truncated.metrics
