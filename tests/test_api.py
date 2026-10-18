from copy import deepcopy
from dataclasses import asdict
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.dependencies import model_service
from api.main import create_app
from config import SAMPLE_DATA_PATH, TRANSACTION_COLUMNS
from src.dashboard_service import dashboard_anomalies
from src.data_processing import Transaction, validate_csv
from src.forecasting import forecast_cash_flow
from src.llm_service import LocalLLMError, OllamaSettings
from src.metrics import calculate_metrics
from src.risk_engine import assess_risk
from src.settings import Settings


@pytest.fixture
def client():
    with TestClient(create_app(Settings(allowed_hosts=("testserver",)))) as instance:
        yield instance


@pytest.fixture
def payload():
    return {"transactions": [
        {"date": "2026-01-01", "description": "Receipt", "amount": "100.25", "category": "Income", "transaction_id": "1"},
        {"date": "2026-01-02", "description": "Expense", "amount": "-25.10", "category": "Other", "transaction_id": "2"},
    ], "opening_balance": "10.00"}


@pytest.fixture
def demo_payload():
    data = validate_csv(SAMPLE_DATA_PATH).data
    rows = [Transaction(**{name: row[name] for name in TRANSACTION_COLUMNS}).model_dump(mode="json")
            for row in data.to_dict("records")]
    return dict(transactions=rows, opening_balance="2500.00", cash_threshold="500.00")


def post(client, path, payload):
    response = client.post("/api/v1/" + path, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_summary_matches_engine_and_money_is_exact_text(client, payload):
    data = validate_csv("date,description,amount,category\n2026-01-01,Receipt,100.25,Income\n2026-01-02,Expense,-25.10,Other\n").data
    expected = calculate_metrics(data, "10.00")
    result = post(client, "analytics/summary", payload)
    for field in ("total_income", "total_expenses", "net_cash_flow", "estimated_balance"):
        assert isinstance(result["metrics"][field], str)
        assert Decimal(result["metrics"][field]) == getattr(expected, field)
    assert result["balance_basis"] == "reconstructed_estimate"


@pytest.mark.parametrize("horizon", [1, 7, 30, 365])
def test_forecast_parity_and_future_rows_do_not_leak(client, demo_payload, horizon):
    demo_payload.update(horizon_days=horizon, as_of="2026-06-30")
    expected = forecast_cash_flow(validate_csv(SAMPLE_DATA_PATH).data, "2500.00", as_of=date(2026, 6, 30),
                                 horizon_days=horizon, cash_threshold="500.00")
    result = post(client, "forecast", demo_payload)
    assert [row["balance_cents"] for row in result["daily"]] == expected.daily.balance_cents.tolist()
    assert result["shortage_dates"] == [day.isoformat() for day in expected.shortage_dates]
    changed = deepcopy(demo_payload)
    changed["transactions"].append(dict(date="2026-12-31", description="Future", amount="9999999.99", category="Income", transaction_id="future"))
    assert post(client, "forecast", changed) == result


def test_threshold_changes_breaches_without_changing_projected_cash(client, demo_payload):
    normal = post(client, "forecast", demo_payload)
    high = post(client, "forecast", {**demo_payload, "cash_threshold": "999999.00"})
    assert len(high["shortage_dates"]) == 30 and not normal["shortage_dates"]
    assert [row["balance_cents"] for row in high["daily"]] == [row["balance_cents"] for row in normal["daily"]]


@pytest.mark.parametrize("engine", ["Calibrated amount review", "Calibrated Isolation Forest", "Legacy Isolation Forest"])
def test_anomalies_and_risk_match_selected_direct_engine(client, demo_payload, engine):
    demo_payload["anomaly_engine"] = engine
    history = validate_csv(SAMPLE_DATA_PATH).data
    expected = dashboard_anomalies(history, engine=engine)
    anomaly_request = {key: value for key, value in demo_payload.items() if key not in {"opening_balance", "cash_threshold"}}
    result = post(client, "anomalies/detect", anomaly_request)
    assert (result["scored_count"], result["anomaly_count"]) == (expected.scored_count, expected.anomaly_count)
    for row in result["transactions"]:
        if row["is_anomaly"] is not None:
            assert row["training_end"] < row["date"]
            if row["calibration_end"]:
                assert row["calibration_end"] < row["date"]
        else:
            assert row["anomaly_score"] is None
    forecast = forecast_cash_flow(history, "2500.00", cash_threshold="500.00")
    risk = assess_risk(history, forecast, anomalies=expected)
    reported = post(client, "risk/analyze", demo_payload)
    assert reported["score"] == risk.score
    assert reported["factors"] == [asdict(factor) for factor in risk.factors]


def test_scenario_emergency_income_and_ledger_invariants(client, demo_payload):
    baseline = post(client, "forecast", demo_payload)
    scenario = post(client, "scenarios/simulate", {**demo_payload, "scenario": {
        "emergency_expense": "500.00", "emergency_date": baseline["daily"][0]["date"], "income_decrease_pct": 20}})
    assert scenario["baseline"] == baseline
    assert scenario["comparison"]["closing_change_cents"] == -134000
    for name in ("baseline", "simulated"):
        previous = scenario[name]["current_balance_cents"]
        for row in scenario[name]["daily"]:
            assert row["net_cents"] == row["inflow_cents"] - row["outflow_cents"]
            assert row["balance_cents"] == previous + row["net_cents"]
            previous = row["balance_cents"]


def test_duplicates_follow_existing_explicit_review_policy(client, payload):
    same = deepcopy(payload)
    same["transactions"].append(same["transactions"][0])
    result = post(client, "transactions/validate", {"transactions": same["transactions"]})
    assert result["analytics_ready"] and result["duplicates_removed"] == 1
    assert post(client, "analytics/summary", same)["metrics"] == post(client, "analytics/summary", payload)["metrics"]
    same["transactions"][-1] = {**same["transactions"][-1], "amount": "101.00"}
    assert not post(client, "transactions/validate", {"transactions": same["transactions"]})["valid"]
    assert client.post("/api/v1/analytics/summary", json=same).status_code == 422
    repeated = deepcopy(payload)
    for row in repeated["transactions"]:
        row.pop("transaction_id")
    repeated["transactions"].append(repeated["transactions"][0])
    assert client.post("/api/v1/analytics/summary", json=repeated).status_code == 422
    removed = post(client, "analytics/summary", {**repeated, "remove_ambiguous_duplicates": True})
    assert removed["metrics"]["transaction_count"] == 2
    assert post(client, "analytics/summary", {**repeated, "reviewed_duplicates": True})["metrics"]["transaction_count"] == 3


@pytest.mark.parametrize("field,value", [("opening_balance", True), ("opening_balance", "NaN"),
    ("opening_balance", "Infinity"), ("opening_balance", "10000000000"), ("opening_balance", "1.001"),
    ("horizon_days", True), ("horizon_days", 30.0), ("horizon_days", "30"), ("horizon_days", 0), ("horizon_days", 366),
    ("cash_threshold", False), ("include_irregular_income", 1), ("currency", "XYZ"),
    ("as_of", "01/01/2026"), ("as_of", "2026-01-01T00:00:00"), ("as_of", "2026-02-30"),
    ("transactions", []), ("unexpected", 123)])
def test_invalid_requests_are_bounded_and_private(client, payload, field, value):
    response = client.post("/api/v1/forecast", json={**payload, field: value})
    assert response.status_code == 422
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "input" not in str(response.json().get("input", {}))


@pytest.mark.parametrize("amount", [True, "NaN", "Infinity", "1.001", "10000000000", {}, []])
def test_invalid_transaction_amounts_never_return_partial_totals(client, payload, amount):
    payload["transactions"][0]["amount"] = amount
    payload["transactions"][0]["description"] = "PRIVATE-DESCRIPTION-DO-NOT-LOG"
    response = client.post("/api/v1/analytics/summary", json=payload)
    assert response.status_code == 422
    assert "PRIVATE-DESCRIPTION-DO-NOT-LOG" not in response.text
    assert "metrics" not in response.json()


def test_missing_fields_and_malformed_json(client):
    for content in (b"{}", b"{broken", b"null", b"[]"):
        response = client.post("/api/v1/forecast", content=content, headers={"content-type": "application/json"})
        assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("scenario", [{"income_decrease_pct": True}, {"expense_increase_pct": "NaN"},
    {"emergency_expense": -1}, {"income_decrease_pct": 101}, {"delay_days": True},
    {"emergency_expense": 5}, {"delay_days": 1}, {"emergency_date": "2026/01/01"}])
def test_invalid_scenarios(client, payload, scenario):
    assert client.post("/api/v1/scenarios/simulate", json={**payload, "scenario": scenario}).status_code == 422


def test_ollama_failure_retains_deterministic_evidence(client, demo_payload):
    class Unavailable:
        settings = OllamaSettings()

        def generate(self, context):
            raise LocalLLMError("connection_error")

    client.app.dependency_overrides[model_service] = lambda: Unavailable()
    result = post(client, "insights/generate", demo_payload)
    assert result["source"] == "deterministic" and result["error_code"] == "connection_error"
    assert result["insights"] is None and result["evidence"]["estimated_balance"]["value"] == "USD 16,268.23"


def test_health_readiness_schema_and_offline_documentation(client):
    assert client.get("/health").status_code == client.get("/ready").status_code == 200
    client.app.state.analytics_ready = False
    assert client.get("/health").status_code == 200 and client.get("/ready").status_code == 503
    assert "/api/v1/forecast" in client.get("/openapi.json").json()["paths"]
    assert "<script" not in client.get("/docs").text


def test_security_transport_limits_and_correlations(payload):
    with TestClient(create_app(Settings(allowed_hosts=("testserver",), max_request_bytes=1024))) as client:
        assert client.post("/api/v1/forecast", content=b"x" * 1025, headers={"content-type": "application/json"}).status_code == 413
        assert client.post("/api/v1/forecast", json=payload, headers={"content-encoding": "gzip"}).status_code == 415
        assert client.post("/api/v1/forecast", content=b"{}").status_code == 415
        assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
        assert client.post("/api/v1/forecast", json=payload, headers={"origin": "https://evil.example"}).status_code == 403
        response = client.get("/health", headers={"x-request-id": "valid-request_1"})
        assert response.headers["x-request-id"] == "valid-request_1"
        assert response.headers["cache-control"] == "no-store"
        assert "access-control-allow-origin" not in response.headers


def test_unexpected_errors_do_not_echo_secrets(client, payload, monkeypatch, caplog):
    from api.services.analytics_service import AnalyticsService

    def fail(*args):
        raise RuntimeError("PRIVATE-FINANCIAL-TEXT")

    monkeypatch.setattr(AnalyticsService, "summary", fail)
    response = client.post("/api/v1/analytics/summary", json=payload)
    assert response.status_code == 500
    assert "PRIVATE-FINANCIAL-TEXT" not in response.text + caplog.text
