from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard_service import ANOMALY_ENGINES, build_dashboard, dashboard_anomalies
from src.financial_context import build_financial_context
from src.insight_workflow import generate_report
from src.llm_service import OllamaService
from src.scenario_simulator import ScenarioConfig, simulate_scenario
from tests.test_llm_service import FakeResponse, FakeSession, chat, metadata

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_complete_calibrated_pipeline_reconciles_and_unavailable_llm_falls_back(demo_dashboard):
    imported, legacy = demo_dashboard
    report = dashboard_anomalies(imported.data)
    bundle = build_dashboard(imported, "2500.00", anomalies=report)
    assert bundle.metrics == legacy.metrics
    assert bundle.metrics.estimated_balance == bundle.metrics.opening_balance + bundle.metrics.total_income - bundle.metrics.total_expenses
    pd.testing.assert_frame_equal(bundle.forecast.daily, legacy.forecast.daily)
    assert report.scored_count > 0 and bundle.risk.score is not None
    scenario = simulate_scenario(bundle.forecast, ScenarioConfig(income_decrease_pct=20,
                                expense_increase_pct=10, emergency_expense="500.00",
                                emergency_date=bundle.forecast.as_of + timedelta(days=1)))
    assert scenario.closing_balance_change_cents < 0
    assert int(scenario.forecast.daily.iloc[-1].balance_cents) == scenario.forecast.current_balance_cents + sum(event.amount_cents for event in scenario.forecast.events)
    context = build_financial_context(bundle, "INR", scenario=scenario)
    assert context.estimated_balance_cents == 1626823 and context.currency == "INR"
    assert context.unusual_count == report.anomaly_count
    session = FakeSession([FakeResponse({"models": []})])
    fallback = generate_report(bundle, OllamaService(session=session), scenario=scenario)
    assert fallback.source == "deterministic" and fallback.error_code == "model_missing"
    assert "16,268.23" in str(fallback.fallback)
    assert all(not url.endswith("chat") for _, url, _ in session.calls)


def test_numeric_model_claims_rejected_with_calibrated_evidence(demo_dashboard, valid_ai_payload):
    imported = demo_dashboard[0]
    bundle = build_dashboard(imported, "2500.00", anomalies=dashboard_anomalies(imported.data))
    valid_ai_payload["financial_health"]["explanation"] = "Your balance is 999999999."
    session = FakeSession([*metadata(), chat(valid_ai_payload), chat(valid_ai_payload)])
    result = generate_report(bundle, OllamaService(session=session))
    assert result.source == "deterministic" and result.error_code == "invalid_response"
    assert "999999999" not in str(result)


def test_dashboard_engine_changes_recalculate_review_and_risk():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.text_input(key="opening_balance").set_value("2500.00").run()
    app.sidebar.radio(key="navigation").set_value("Anomaly Detection").run()
    selected = next(item.value for item in app.metric if item.label == "Transactions scored")
    assert not app.exception and selected != "0"
    app.multiselect(key="anomaly_severity").set_value(["High priority"]).run()
    assert not app.exception
    for engine in ANOMALY_ENGINES[1:]:
        app.sidebar.selectbox(key="anomaly_engine").set_value(engine).run()
        assert not app.exception
    legacy = next(item.value for item in app.metric if item.label == "Transactions scored")
    assert int(legacy) > int(selected)
    app.sidebar.radio(key="navigation").set_value("Risk Analysis").run()
    assert not app.exception
    app.sidebar.selectbox(key="anomaly_engine").set_value(ANOMALY_ENGINES[0]).run()
    assert not app.exception


def test_dashboard_shows_matched_candidate_results_without_llm_inference():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.radio(key="navigation").set_value("Model Evaluation").run()
    assert not app.exception and not app.metric
    app.button(key="run_candidate_comparison").click().run()
    assert not app.exception
    frame = app.dataframe[0].value
    assert len(frame) == 6 and frame["selected"].sum() == 1
    assert frame.test_rows.nunique() == 1
    assert frame.loc[frame.selected, "method"].iloc[0] == "context_stat"
    assert app.selectbox(key="candidate_chart_method").value == "context_stat"
