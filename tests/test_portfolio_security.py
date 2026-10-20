import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest
from pathlib import Path

from api.main import create_app
from api.policy import RequestBudget
from config import SAMPLE_DATA_PATH
from src.demo_policy import public_fixture
from src.settings import Settings, configured_api_url

TOKEN = "test-service-token-" + "s" * 32
OPS = "test-operations-token-" + "o" * 32


def public_settings(**updates):
    values = dict(public_demo=True, deployment_profile="staging", execution_mode="api",
                  api_token=TOKEN, ops_token=OPS, allowed_hosts=("testserver",), rate_limit_per_minute=60)
    values.update(updates)
    return Settings(**values)


def test_public_configuration_fails_closed_and_masks_credentials():
    for values in ({"public_demo":True}, {"deployment_profile":"public"},
                   {"api_token":"short-secret"}, {"public_demo":True,"execution_mode":"api","api_token":TOKEN}):
        with pytest.raises(ValidationError) as exc:
            Settings(**values)
        assert "short-secret" not in str(exc.value)
    with pytest.raises(ValueError):
        public_settings(ops_token=TOKEN)


def test_operations_require_separate_auth_and_health_remains_public():
    with TestClient(create_app(public_settings())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        for path in ("/metrics", "/docs", "/openapi.json"):
            assert client.get(path).status_code == 401
            assert client.get(path, headers={"authorization":"Bearer "+TOKEN}).status_code == 401
            assert client.get(path, headers={"authorization":"Bearer "+OPS}).status_code == 200
        assert client.post("/api/v1/transactions/csv",json={"csv_text":public_fixture()[0]}).status_code == 401


def test_public_demo_accepts_only_known_fixture_and_never_echoes_rejected_content(caplog):
    with TestClient(create_app(public_settings())) as client:
        headers={"authorization":"Bearer "+TOKEN}
        valid=client.post("/api/v1/transactions/csv",json={"csv_text":public_fixture()[0]},headers=headers)
        assert valid.status_code == 200
        for payload in ({"csv_text":"PRIVATE_CANARY_FINANCIAL_DATA"},
                        {"csv_text":public_fixture()[0].replace("Salary","PRIVATE_CANARY_FINANCIAL_DATA")}):
            # Ensure the second probe actually changed the fixture.
            if payload["csv_text"] == public_fixture()[0]:
                payload["csv_text"] += "PRIVATE_CANARY_FINANCIAL_DATA"
            rejected=client.post("/api/v1/transactions/csv",json=payload,headers=headers)
            assert rejected.status_code == 403
            assert "PRIVATE_CANARY" not in rejected.text
        assert "PRIVATE_CANARY" not in caplog.text and TOKEN not in caplog.text


def test_rate_limits_ignore_forged_forwarding_headers_and_protect_health():
    with TestClient(create_app(public_settings(rate_limit_per_minute=2))) as client:
        for index in range(2):
            assert client.get("/metrics",headers={"x-forwarded-for":str(index)}).status_code == 401
        response=client.get("/metrics",headers={"x-forwarded-for":"different"})
        assert response.status_code == 429 and response.headers["retry-after"] == "60"
        assert client.get("/ready").status_code == 200


def test_rate_budget_memory_global_bound_and_window_reset():
    clock=[0.0]
    budget=RequestBudget(2,3,2,clock=lambda:clock[0])
    assert budget.accept("a") and budget.accept("b")
    assert not budget.accept("new-client")
    assert budget.accept("a") and not budget.accept("b")
    assert len(budget.clients)==2
    clock[0]=60
    assert budget.accept("new-client")


def test_cors_uses_exact_configured_origins_and_never_wildcards():
    with TestClient(create_app(public_settings(cors_origins=("https://demo.example.com",)))) as client:
        preflight=client.options("/api/v1/forecast",headers={"origin":"https://demo.example.com"})
        assert preflight.status_code == 204
        assert preflight.headers["access-control-allow-origin"]=="https://demo.example.com"
        assert "access-control-allow-credentials" not in preflight.headers
        assert client.get("/ready",headers={"origin":"https://evil.example"}).status_code==403


@pytest.mark.parametrize("url",["https://user:secret@api.example.com", "https://api.example.com?token=private", "http://api.example.com", "https://other.example"])
def test_configured_remote_endpoints_cannot_smuggle_credentials_or_unapproved_hosts(url):
    with pytest.raises(ValueError):
        configured_api_url(url,("api.example.com",))


def test_public_ui_has_no_upload_surface_and_sessions_have_distinct_identifiers(monkeypatch):
    import src.dashboard_backend
    from src.data_processing import validate_csv
    class Backend:
        def __init__(self,*args,**kwargs):
            pass
        def import_csv(self,raw,*args):
            return validate_csv(raw)
    monkeypatch.setattr(src.dashboard_backend,"DashboardBackend",Backend)
    monkeypatch.setenv("CASHGUARD_PUBLIC_DEMO","true")
    monkeypatch.setenv("CASHGUARD_EXECUTION_MODE","api")
    monkeypatch.setenv("CASHGUARD_API_TOKEN",TOKEN)
    monkeypatch.setenv("CASHGUARD_RATE_LIMIT_PER_MINUTE","60")
    app_path=Path(__file__).resolve().parents[1]/"app.py"
    first=AppTest.from_file(app_path,default_timeout=20).run()
    second=AppTest.from_file(app_path,default_timeout=20).run()
    assert not first.exception and not second.exception
    assert not first.file_uploader and not second.file_uploader
    assert first.session_state["cashguard_session_id"] != second.session_state["cashguard_session_id"]
    assert all("Upload CSV" not in radio.options for radio in first.radio)
    first.radio(key="navigation").set_value("Model Evaluation").run()
    assert not first.exception and not first.error
    assert any(metric.label=="F1" and metric.value=="0.9600" for metric in first.metric)
    assert not any(button.label.startswith("Run ") for button in first.button)
