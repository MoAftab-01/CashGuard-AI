import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services.analytics_service import AnalyticsService
from src.llm_service import LocalLLMError
from src.observability import JsonFormatter, Metrics, ObservedModel, request_id
from src.settings import Settings


def test_http_counts_latency_errors_and_private_cardinality(monkeypatch):
    app = create_app(Settings(allowed_hosts=("testserver",)))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/PRIVATE-ACCOUNT?description=PRIVATE-DESCRIPTION").status_code == 404
        assert client.post("/api/v1/forecast", json={"PRIVATE-FIELD": 1}).status_code == 422
        monkeypatch.setattr(AnalyticsService, "summary", lambda *_: (_ for _ in ()).throw(RuntimeError("PRIVATE-ERROR")))
        body = dict(transactions=[dict(date="2026-01-01", description="PRIVATE-TRANSACTION",
                                      amount="1.00", category="Income")], opening_balance="0")
        assert client.post("/api/v1/analytics/summary", json=body).status_code == 500
        text = client.get("/metrics").text
    assert 'route="/health",status_class="2xx"} 1.0' in text
    assert 'route="unmatched",status_class="4xx"} 1.0' in text
    assert 'route="/api/v1/forecast",status_class="4xx"} 1.0' in text
    assert 'route="/api/v1/analytics/summary",status_class="5xx"} 1.0' in text
    assert "cashguard_http_duration_seconds_count" in text
    assert "PRIVATE" not in text
    assert app.state.metrics.registry.get_sample_value("cashguard_local_model_available") == -1


def test_operation_timers_success_failure_and_no_label_growth():
    metrics = Metrics()
    with metrics.measure("forecast"):
        pass
    with pytest.raises(ValueError), metrics.measure("anomaly"):
        raise ValueError("private")
    with pytest.raises(ValueError, match="Unsupported operation"):
        with metrics.measure("PRIVATE-DESCRIPTION"):
            pass
    assert metrics.registry.get_sample_value("cashguard_operation_duration_seconds_count",
           {"operation": "forecast", "result": "success"}) == 1
    assert metrics.registry.get_sample_value("cashguard_operation_duration_seconds_count",
           {"operation": "anomaly", "result": "error"}) == 1
    metrics.observe_http("/private/123", "PRIVATE", 999, .01)
    assert 'method="OTHER",route="unmatched",status_class="other"' in metrics.render().decode()
    assert "PRIVATE" not in metrics.render().decode()


@pytest.mark.parametrize("code,availability", [("timeout", -1), ("connection_error", 0), ("model_missing", 0),
                                              ("invalid_response", -1), ("PRIVATE", -1)])
def test_model_failures_are_bounded_and_timed(code, availability):
    metrics = Metrics()
    def fail(_):
        if code == "PRIVATE":
            raise RuntimeError("PRIVATE")
        raise LocalLLMError(code)
    observed = ObservedModel(SimpleNamespace(settings=None, generate=fail), metrics)
    with pytest.raises(RuntimeError):
        observed.generate({})
    assert metrics.registry.get_sample_value("cashguard_local_model_available") == availability
    reason = code if code in Metrics.FAILURES else "unexpected"
    assert metrics.registry.get_sample_value("cashguard_llm_failures_total", {"reason": reason}) == 1
    assert metrics.registry.get_sample_value("cashguard_operation_duration_seconds_count",
           {"operation": "llm", "result": "error"}) == 1
    assert "PRIVATE" not in metrics.render().decode()


def test_model_success_and_metrics_disabled_are_separate_from_health():
    metrics = Metrics()
    value = object()
    assert ObservedModel(SimpleNamespace(settings=None, generate=lambda _: value), metrics).generate({}) is value
    assert metrics.registry.get_sample_value("cashguard_local_model_available") == 1
    app = create_app(Settings(allowed_hosts=("testserver",), metrics_enabled=False))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 404
    assert app.state.metrics.registry.get_sample_value("cashguard_http_requests_total",
           {"route": "/health", "method": "GET", "status_class": "2xx"}) is None
    assert Metrics().registry.get_sample_value("cashguard_local_model_available") == -1


def test_json_logging_excludes_messages_exceptions_and_financial_values():
    record = logging.LogRecord("cashguard.api", logging.ERROR, "", 0, "PRIVATE PAYLOAD", (), None)
    record.exc_text = "PRIVATE TRACEBACK"
    record.event_type = "http_request"
    record.duration_seconds = .25
    record.status = 422
    token = request_id.set("qa-correlation-1")
    try:
        encoded = JsonFormatter().format(record)
    finally:
        request_id.reset(token)
    event = json.loads(encoded)
    assert event["request_id"] == "qa-correlation-1"
    assert event["severity"] == "ERROR" and event["component"] == "cashguard.api"
    assert event["event_type"] == "http_request" and event["duration_seconds"] == .25
    assert event["timestamp"].endswith("+00:00") and "PRIVATE" not in encoded


def test_actual_api_forecast_and_anomaly_operations_are_instrumented():
    app = create_app(Settings(allowed_hosts=("testserver",)))
    payload = dict(transactions=[dict(date="2026-01-01", description="Receipt", amount="10", category="Income")],
                   opening_balance="0")
    with TestClient(app) as client:
        assert client.post("/api/v1/risk/analyze", json=payload).status_code == 200
    for operation in ("forecast", "anomaly"):
        assert app.state.metrics.registry.get_sample_value("cashguard_operation_duration_seconds_count",
               {"operation": operation, "result": "success"}) == 1
