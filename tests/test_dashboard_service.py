import io
import re
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from src.dashboard_service import (DashboardInputError, build_dashboard, compare_scenario,
                                    export_transactions, filter_transactions, financial_summaries,
                                    format_cents, session_value)
from src.data_processing import ImportResult, empty_transactions, validate_csv
from src.metrics import calculate_metrics
from src.scenario_simulator import ScenarioConfig, simulate_scenario


def test_dashboard_metrics_match_engine_exactly(demo_dashboard):
    imported, bundle = demo_dashboard
    assert bundle.metrics == calculate_metrics(imported.data, "2500.00")
    assert bundle.metrics.estimated_balance == Decimal("16268.23")
    assert bundle.forecast.current_balance_cents == int(bundle.metrics.estimated_balance * 100)
    assert bundle.data.equals(imported.data)
    assert bundle.anomalies.as_of == bundle.forecast.as_of


def test_changed_opening_and_threshold_update_forecasts_without_stale_results(demo_dashboard):
    imported, base = demo_dashboard
    changed = build_dashboard(imported, "3500.00", cash_threshold="999999.00", anomalies=base.anomalies)
    assert (changed.forecast.daily["balance_cents"] - base.forecast.daily["balance_cents"]).eq(100000).all()
    assert len(changed.forecast.shortage_dates) == 30
    assert not base.forecast.shortage_dates
    assert changed.risk != base.risk


def test_analysis_date_excludes_future_from_all_dashboard_outputs(demo_dashboard):
    imported, _ = demo_dashboard
    cutoff = date(2026, 3, 31)
    bundle = build_dashboard(imported, "2500.00", as_of=cutoff)
    assert bundle.data["date"].max() <= cutoff
    assert bundle.anomalies.data["date"].max() <= cutoff
    expected = calculate_metrics(imported.data.loc[imported.data["date"] <= cutoff], "2500.00")
    assert bundle.metrics == expected
    assert bundle.forecast.current_balance_cents == int(expected.estimated_balance * 100)


def test_irregular_income_control_updates_engine_projection(demo_dashboard):
    imported, base = demo_dashboard
    changed = build_dashboard(imported, "2500.00", include_irregular_income=True, anomalies=base.anomalies)
    assert changed.forecast.daily["inflow_cents"].sum() > base.forecast.daily["inflow_cents"].sum()
    assert changed.metrics == base.metrics


def test_stale_anomaly_report_cannot_be_reused(demo_dashboard):
    imported, bundle = demo_dashboard
    with pytest.raises(DashboardInputError, match="different analysis date"):
        build_dashboard(imported, 0, as_of=date(2026, 6, 30), anomalies=bundle.anomalies)
    altered = imported.data.copy()
    altered.loc[0, "amount_cents"] += 1
    with pytest.raises(DashboardInputError, match="different transactions"):
        build_dashboard(ImportResult(altered), 0, anomalies=bundle.anomalies)


@pytest.mark.parametrize("text", ["", "date,description,amount,category\n", "date,amount\n", "date,description,amount,category\n2026-01-01,Bad,nan,Other\n"])
def test_empty_or_malformed_imports_have_helpful_blocking_messages(text):
    with pytest.raises(DashboardInputError, match="Import has errors"):
        build_dashboard(validate_csv(text), 0)


def test_missing_and_malformed_analytics_data_are_not_fabricated():
    with pytest.raises(DashboardInputError, match="No transactions"):
        build_dashboard(ImportResult(empty_transactions()), 0)
    malformed = ImportResult(pd.DataFrame({"description": ["Bad"]}))
    with pytest.raises(DashboardInputError, match="Missing analytics columns"):
        build_dashboard(malformed, 0)


@pytest.mark.parametrize("opening,threshold", [("", "0"), ("nan", "0"), ("100", "bad"), ("1.001", "0")])
def test_bad_balance_controls_do_not_produce_outputs(demo_dashboard, opening, threshold):
    with pytest.raises(DashboardInputError):
        build_dashboard(demo_dashboard[0], opening, cash_threshold=threshold)


def test_identified_duplicates_are_removed_before_totals_and_ambiguous_ones_require_review():
    header = "date,description,amount,category"
    row = "2026-01-01,Pay,100,Income"
    known = validate_csv(header + ",transaction_id\n" + (row + ",001\n") * 2)
    result = build_dashboard(known, 10)
    assert result.metrics.total_income == 100
    assert result.metrics.estimated_balance == 110
    ambiguous = validate_csv(header + "\n" + (row + "\n") * 2)
    with pytest.raises(DashboardInputError, match="duplicate transactions need review"):
        build_dashboard(ambiguous, 10)
    removed = validate_csv(header + "\n" + (row + "\n") * 2, remove_ambiguous_duplicates=True)
    assert build_dashboard(removed, 10).metrics.total_income == 100
    assert build_dashboard(ambiguous, 10, reviewed_duplicates=True).metrics.total_income == 200


def test_filters_are_inclusive_literal_and_do_not_mutate_data(transactions):
    data = transactions([(date(2026, 1, 1), "A[1] coffee", -100, "Dining"),
                         (date(2026, 1, 2), "A[1] groceries", -200, "Groceries"),
                         (date(2026, 1, 3), "Other income", 1000, "Income")])
    before = data.copy(deep=True)
    filtered = filter_transactions(data, start_date=date(2026, 1, 2), end_date=date(2026, 1, 2),
                                   categories=["Groceries"], search="a[1]", direction="Expenses")
    assert len(filtered) == 1 and filtered.iloc[0]["amount_cents"] == -200
    assert filter_transactions(data, search="does not exist").empty
    pd.testing.assert_frame_equal(data, before)
    with pytest.raises(DashboardInputError, match="Start date"):
        filter_transactions(data, start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))


def test_filtered_export_preserves_exact_amounts_and_neutralizes_formula_text(transactions):
    data = transactions([(date(2026, 1, 1), "=SUM(1,2)", -10, "Other"),
                         (date(2026, 1, 2), "Ordinary", 20, "Income")])
    filtered = filter_transactions(data, direction="Expenses")
    output = pd.read_csv(io.BytesIO(export_transactions(filtered)), dtype=str)
    assert output["amount"].tolist() == ["-0.10"]
    assert output["description"].tolist() == ["'=SUM(1,2)"]
    assert "amount_cents" not in output and "source_row" not in output
    assert data.iloc[0]["description"] == "=SUM(1,2)"


def test_scenario_comparison_uses_engine_results(demo_dashboard):
    _, bundle = demo_dashboard
    result = simulate_scenario(bundle.forecast, ScenarioConfig(income_decrease_pct=20, emergency_expense=20000,
                                                              emergency_date=bundle.forecast.as_of + timedelta(days=1)))
    comparison = compare_scenario(result)
    assert comparison.baseline_minimum_cents == bundle.forecast.daily["balance_cents"].min()
    assert comparison.scenario_minimum_cents == result.forecast.daily["balance_cents"].min()
    assert comparison.closing_change_cents == result.closing_balance_change_cents
    assert comparison.additional_breach_dates


def test_deterministic_summaries_contain_only_output_derived_financial_amounts(demo_dashboard):
    _, bundle = demo_dashboard
    first = financial_summaries(bundle, "USD")
    assert first == financial_summaries(bundle, "USD")
    text = " ".join(body for _, body in first)
    allowed = {format_cents(int(value * 100), "USD") for value in [bundle.metrics.total_income,
               bundle.metrics.total_expenses, bundle.metrics.net_cash_flow, bundle.metrics.estimated_balance,
               bundle.metrics.opening_balance]}
    allowed |= {format_cents(int(bundle.forecast.daily.iloc[-1]["balance_cents"]), "USD"),
                format_cents(int(bundle.forecast.daily["balance_cents"].min()), "USD"),
                format_cents(bundle.forecast.cash_threshold_cents, "USD")}
    amounts = set(re.findall(r"USD -?[\d,]+\.\d{2}", text))
    assert amounts == allowed
    assert f"{bundle.anomalies.anomaly_count} transactions" in text
    assert "not confirmed fraud" in text


def test_session_cache_invalidates_parameters_and_never_shares_user_results():
    alice, bob = {}, {}
    calls = []
    def compute(value):
        calls.append(value)
        return {"cash": value}
    assert session_value(alice, "dashboard", ("data", 100), lambda: compute(100))["cash"] == 100
    assert session_value(alice, "dashboard", ("data", 100), lambda: compute(999))["cash"] == 100
    assert calls == [100]
    assert session_value(bob, "dashboard", ("data", 100), lambda: compute(200))["cash"] == 200
    assert session_value(alice, "dashboard", ("data", 300), lambda: compute(300))["cash"] == 300
    assert len(alice["cashguard_private_cache"]) == 1
    assert bob["cashguard_private_cache"]["dashboard"][1]["cash"] == 200


def test_failed_recalculation_is_not_cached():
    state = {}
    def fail():
        raise ValueError("invalid inputs")
    with pytest.raises(ValueError):
        session_value(state, "dashboard", ("bad",), fail)
    assert "dashboard" not in state["cashguard_private_cache"]
    assert session_value(state, "dashboard", ("bad",), lambda: 42) == 42
