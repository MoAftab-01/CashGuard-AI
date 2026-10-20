import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
import requests
from fastapi.testclient import TestClient
from pandas.testing import assert_frame_equal

from api.main import create_app
from config import SAMPLE_DATA_PATH
from src.api_client import ApiClient, ApiClientError
from src.dashboard_backend import DashboardBackend
from src.dashboard_service import build_dashboard, dashboard_anomalies
from src.dashboard_wire import DashboardWire, Table, dataframe
from src.data_processing import validate_csv
from src.settings import Settings
from src.scenario_simulator import ScenarioConfig, simulate_scenario
from src.insight_prompts import StructuredInsights
from src.llm_service import OllamaSettings, OllamaStatus
from api.dependencies import model_service
from streamlit.testing.v1 import AppTest


@pytest.fixture
def backend():
    with TestClient(create_app(Settings(allowed_hosts=("testserver",)))) as server:
        class Transport(requests.Session):
            def request(self, method, url, **kwargs):
                reply = server.request(method, url.replace("http://127.0.0.1:8000", ""),
                                       content=kwargs.get("data"), headers=kwargs.get("headers"))
                result = requests.Response()
                result.status_code, result._content = reply.status_code, reply.content
                result._content_consumed = True
                result.headers.update(reply.headers)
                return result
        with ApiClient(session=Transport()) as client:
            adapter = DashboardBackend(Settings(execution_mode="api"), client=client)
            adapter.test_application = server.app
            yield adapter


def payload(backend, imported, **overrides):
    values = dict(as_of=imported.data.date.max(), threshold="500.00", irregular=False,
                  reviewed=False, engine="Calibrated amount review")
    values.update(overrides)
    return backend.payload(imported, "2500.00", **values)


def test_api_overview_matches_every_engine_output_and_nullable_dates(backend):
    imported = validate_csv(SAMPLE_DATA_PATH)
    result = backend.dashboard(payload(backend, imported))
    anomalies = dashboard_anomalies(imported.data)
    direct = build_dashboard(imported, "2500.00", anomalies=anomalies)
    assert result.metrics == direct.metrics
    assert result.risk == direct.risk
    for name in ("data", "balance_history", "monthly", "spending"):
        assert_frame_equal(getattr(result, name), getattr(direct, name))
    assert_frame_equal(result.forecast.daily, direct.forecast.daily)
    assert_frame_equal(result.anomalies.data, direct.anomalies.data)
    assert result.forecast.recurring_patterns == direct.forecast.recurring_patterns
    assert result.forecast.events == direct.forecast.events


def test_api_csv_validation_preserves_duplicates_malformed_rows_and_exact_money(backend):
    raw = b"date,description,amount,category\n2026-01-01,Fictional,0.01,Other\n2026-01-01,Fictional,0.01,Other\n2026-01-02,Bad,no-money,Other\n"
    api = backend.import_csv(raw)
    direct = validate_csv(raw)
    assert api.issues == direct.issues and api.input_rows == direct.input_rows
    assert_frame_equal(api.data, direct.data)
    assert api.data.amount.iloc[0] == Decimal("0.01")


def test_api_parameters_and_cutoffs_cannot_reuse_future_or_other_session_data(backend):
    imported = validate_csv(SAMPLE_DATA_PATH)
    earlier = date(2026, 4, 1)
    first = backend.dashboard(payload(backend, imported, as_of=earlier))
    second = backend.dashboard(payload(backend, imported, threshold="20000.00"))
    again = backend.dashboard(payload(backend, imported, as_of=earlier))
    assert first.data.date.max() <= earlier
    assert second.forecast.cash_threshold_cents == 2000000
    assert first.forecast.cash_threshold_cents == 50000
    assert first.metrics == again.metrics
    assert_frame_equal(first.anomalies.data, again.anomalies.data)


def test_wire_rejects_nonfinite_and_malformed_table_shapes():
    with pytest.raises(ValueError):
        Table.model_validate_json('{"columns":[],"rows":[{"score":NaN}]}')
    with pytest.raises(ValueError, match="shape"):
        dataframe({"columns":[{"name":"amount","dtype":"object"}],"rows":[{"other":"1.00"}]})


def test_overview_ui_routes_through_api_without_direct_ui_financial_calls(backend, monkeypatch):
    import src.dashboard_backend
    import src.dashboard_service
    monkeypatch.setenv("CASHGUARD_EXECUTION_MODE", "api")
    monkeypatch.setattr(src.dashboard_backend, "DashboardBackend", lambda _, **kwargs: backend)
    def forbidden(*args, **kwargs):
        raise AssertionError("UI performed direct financial calculations in API mode")
    monkeypatch.setattr(src.dashboard_service, "build_dashboard", forbidden)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.button(key="start_demo").click().run()
    assert not app.exception and not app.error
    values = {metric.label: metric.value for metric in app.metric}
    assert values["Estimated cash balance"] == "USD 16,268.23"


def test_api_forecast_ui_recalculates_threshold_without_local_forecasting(backend, monkeypatch):
    import src.dashboard_backend
    import src.dashboard_service
    monkeypatch.setenv("CASHGUARD_EXECUTION_MODE", "api")
    monkeypatch.setattr(src.dashboard_backend, "DashboardBackend", lambda _, **kwargs: backend)
    monkeypatch.setattr(src.dashboard_service, "build_dashboard", lambda *a, **k: pytest.fail("Unexpected direct UI call"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.button(key="start_demo").click().run()
    app.radio(key="navigation").set_value("Cash Flow Forecast").run()
    assert not app.exception and not app.error
    initial = {metric.label: metric.value for metric in app.metric}
    app.text_input(key="cash_threshold").set_value("20000.00").run()
    changed = {metric.label: metric.value for metric in app.metric}
    assert initial["Days below threshold"] == "0"
    assert int(changed["Days below threshold"]) > 0


def test_api_anomaly_view_preserves_reference_explanations_and_all_engine_choices(backend):
    imported = validate_csv(SAMPLE_DATA_PATH)
    for engine in ("Calibrated amount review", "Calibrated Isolation Forest", "Legacy Isolation Forest"):
        result = backend.anomalies(imported, as_of=imported.data.date.max(), engine=engine, currency="USD")
        direct = dashboard_anomalies(imported.data, engine=engine)
        assert_frame_equal(result.data, direct.data)
        assert result.warnings == direct.warnings
        assert result.scored_count == direct.scored_count


def test_api_risk_page_uses_same_backend_after_navigation(backend, monkeypatch):
    import src.dashboard_backend
    import src.dashboard_service
    monkeypatch.setenv("CASHGUARD_EXECUTION_MODE", "api")
    monkeypatch.setattr(src.dashboard_backend, "DashboardBackend", lambda _, **kwargs: backend)
    monkeypatch.setattr(src.dashboard_service, "build_dashboard", lambda *a, **k: pytest.fail("Unexpected direct UI call"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.button(key="start_demo").click().run()
    app.radio(key="navigation").set_value("Risk Analysis").run()
    assert not app.exception and not app.error
    assert any("Risk" in item.value for item in app.title)


def test_api_scenario_preserves_baseline_and_changes_only_projected_ledger(backend):
    imported = validate_csv(SAMPLE_DATA_PATH)
    request = payload(backend, imported)
    baseline = backend.dashboard(request)
    config = ScenarioConfig(emergency_expense="500.00", emergency_date=baseline.forecast.daily.iloc[0].date,
                            income_decrease_pct=20)
    result = backend.scenario(request, config)
    direct = simulate_scenario(baseline.forecast, config)
    assert_frame_equal(result.baseline.daily, baseline.forecast.daily)
    assert_frame_equal(result.forecast.daily, direct.forecast.daily)
    assert result.closing_balance_change_cents < -50000
    assert result.deferred_events == direct.deferred_events


def test_api_scenario_ui_never_executes_local_scenario_engine(backend, monkeypatch):
    import src.dashboard_backend
    import src.ui.pages
    monkeypatch.setenv("CASHGUARD_EXECUTION_MODE", "api")
    monkeypatch.setattr(src.dashboard_backend, "DashboardBackend", lambda _, **kwargs: backend)
    monkeypatch.setattr(src.ui.pages, "simulate_scenario", lambda *a, **k: pytest.fail("Unexpected local scenario"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.button(key="start_demo").click().run()
    app.radio(key="navigation").set_value("Scenario Simulator").run()
    app.text_input(key="scenario_emergency").set_value("500.00").run()
    assert not app.exception and not app.error
    assert {m.label:m.value for m in app.metric}["Closing balance change"] == "USD -500.00"


def test_ai_ui_uses_api_generation_once_and_invalidates_on_changed_evidence(backend, monkeypatch, valid_ai_payload):
    import src.dashboard_backend
    import api.routes.v1
    from copy import deepcopy
    calls = []
    class Model:
        settings = OllamaSettings()
        def __init__(self, *args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def close(self):
            pass
        def check_availability(self):
            return OllamaStatus(True, "ready", "Test provider available", self.settings.model)
        def generate(self, context):
            calls.append(context.fingerprint())
            assert "transaction_id" not in context.model_dump_json()
            return StructuredInsights.model_validate(deepcopy(valid_ai_payload))
    backend.test_application.dependency_overrides[model_service] = lambda: Model()
    monkeypatch.setattr(api.routes.v1, "create_provider", lambda *args, **kwargs: Model())
    monkeypatch.setenv("CASHGUARD_EXECUTION_MODE", "api")
    monkeypatch.setattr(src.dashboard_backend, "DashboardBackend", lambda _, **kwargs: backend)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.button(key="start_demo").click().run()
    app.radio(key="navigation").set_value("AI Insights").run()
    assert calls == [] and not app.exception
    app.button(key="generate_ai_insights").click().run()
    assert len(calls) == 1 and not app.exception and not app.error
    assert any(s.value == "AI-generated explanations" for s in app.header)
    app.run()
    assert len(calls) == 1
    app.text_input(key="cash_threshold").set_value("20000.00").run()
    assert len(calls) == 1 and not any(s.value == "AI-generated explanations" for s in app.header)


def test_disabled_backend_keeps_calculated_summaries_without_offering_model_generation(backend, monkeypatch):
    import src.dashboard_backend
    import api.routes.v1
    from src.inference import DeterministicProvider
    monkeypatch.setattr(api.routes.v1, "create_provider", lambda *args, **kwargs: DeterministicProvider())
    backend.test_application.dependency_overrides[model_service] = lambda: pytest.fail("Disabled provider must not generate")
    monkeypatch.setenv("CASHGUARD_EXECUTION_MODE", "api")
    monkeypatch.setattr(src.dashboard_backend, "DashboardBackend", lambda _, **kwargs: backend)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.button(key="start_demo").click().run()
    app.radio(key="navigation").set_value("AI Insights").run()
    assert not app.exception and not app.error
    assert app.button(key="generate_ai_insights").disabled
    assert any(item.value == "Calculated financial summaries" for item in app.header)
    assert any("16,268.23" in item.value for item in app.markdown)


def test_transient_retries_are_bounded_and_never_repeat_inference(backend):
    class Broken(requests.Session):
        calls = 0
        def request(self, *args, **kwargs):
            self.calls += 1
            raise requests.Timeout()
    transport = Broken()
    with ApiClient(session=transport, max_retries=2) as client:
        with pytest.raises(ApiClientError, match="timeout"):
            client.health()
        assert transport.calls == 3
        transport.calls = 0
        imported = validate_csv(SAMPLE_DATA_PATH)
        with pytest.raises(ApiClientError, match="timeout"):
            client.call("insights", payload(backend, imported))
        assert transport.calls == 1
