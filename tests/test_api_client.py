from decimal import Decimal

import pytest
import requests
from fastapi.testclient import TestClient

from api.main import create_app
from api.dependencies import model_service
from api.services.analytics_service import AnalyticsService
from src.api_client import ApiClient, ApiClientError
from src.settings import Settings
from src.llm_service import LocalLLMError, OllamaSettings


PAYLOAD = dict(transactions=[dict(date="2026-01-01", description="Fictional receipt", amount="100.25", category="Income"),
                             dict(date="2026-01-02", description="Fictional expense", amount="-25.10", category="Other")],
               opening_balance="10.00")


class Session:
    def __init__(self, handler):
        self.handler, self.calls, self.proxies, self.trust_env, self.closed = handler, [], {"http": "external"}, True, False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.handler(method, url, kwargs)

    def close(self):
        self.closed = True


def response(content, status=200, media="application/json"):
    result = requests.Response()
    result.status_code, result.headers["content-type"] = status, media
    result._content = content.encode() if isinstance(content, str) else content
    result._content_consumed = True
    return result


def test_reusable_client_parity_across_financial_routes_and_health():
    app = create_app(Settings(allowed_hosts=("testserver",)))
    class UnavailableModel:
        settings = OllamaSettings()
        def generate(self, _):
            raise LocalLLMError("connection_error")
    app.dependency_overrides[model_service] = lambda: UnavailableModel()
    with TestClient(app) as server:
        def handler(method, url, options):
            result = server.request(method, url.replace("http://127.0.0.1:8000", ""),
                                    content=options["data"], headers=options["headers"])
            return response(result.content, result.status_code)
        session = Session(handler)
        with ApiClient(session=session) as client:
            assert client.health().status == "ok" and client.ready().analytics_ready
            summary = client.call("summary", PAYLOAD)
            assert summary.mode == "api" and summary.warning is None
            assert summary.value.metrics.estimated_balance == Decimal("85.15")
            assert client.call("forecast", {**PAYLOAD, "horizon_days": 7}).value.horizon_days == 7
            assert client.call("validate", {"transactions": PAYLOAD["transactions"]}).value.analytics_ready
            assert client.call("anomalies", {"transactions": PAYLOAD["transactions"]}).value.unscored_count == 2
            assert client.call("risk", PAYLOAD).value.data_sufficiency
            scenario = client.call("scenario", {**PAYLOAD, "scenario": {"emergency_expense": "10.00", "emergency_date": "2026-01-03"}})
            assert scenario.value.comparison.closing_change_cents == -1000
            insights = client.call("insights", PAYLOAD).value
            assert insights.source == "deterministic" and insights.error_code == "connection_error"
        assert session.closed and not session.trust_env and not session.proxies
        assert all(not options["allow_redirects"] and options["timeout"] == (3, 30) for _, _, options in session.calls)


@pytest.mark.parametrize("url", ["https://127.0.0.1:8000", "http://example.com", "http://host.docker.internal:8000",
                                 "http://192.168.1.1:8000", "http://user:password@localhost:8000", "http://127.0.0.1:8000/path"])
def test_external_credentialed_or_redirectable_urls_rejected_before_transmission(url):
    with pytest.raises(ValueError):
        ApiClient(url)


@pytest.mark.parametrize("error,code", [(requests.ConnectionError("PRIVATE"), "connection_error"),
                                       (requests.Timeout("PRIVATE"), "timeout")])
def test_connection_failures_do_not_silently_fallback(error, code):
    def fail(*args):
        raise error
    with ApiClient(session=Session(fail)) as client:
        with pytest.raises(ApiClientError) as caught:
            client.call("summary", PAYLOAD)
        assert caught.value.code == code and "PRIVATE" not in str(caught.value)
        result = client.call("summary", PAYLOAD, allow_fallback=True, direct=AnalyticsService().summary)
        assert result.mode == "direct_fallback" and "Explicit direct fallback" in result.warning
        assert result.value.metrics.estimated_balance == Decimal("85.15")


@pytest.mark.parametrize("status,code,fallback", [(422, "invalid_request", False), (413, "request_too_large", False),
    (500, "http_error", False), (302, "http_error", False), (503, "busy", True)])
def test_http_errors_are_private_and_only_busy_may_explicitly_fallback(status, code, fallback):
    with ApiClient(session=Session(lambda *args: response("PRIVATE SERVER TRACE", status))) as client:
        if fallback:
            assert client.call("summary", PAYLOAD, allow_fallback=True, direct=AnalyticsService().summary).mode == "direct_fallback"
        else:
            with pytest.raises(ApiClientError) as caught:
                client.call("summary", PAYLOAD, allow_fallback=True,
                            direct=lambda _: pytest.fail("Invalid/error responses must not trigger fallback"))
            assert caught.value.code == code and "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("body,media", [("{}", "application/json"), ("PRIVATE HTML", "text/html"),
                                       ("{broken PRIVATE", "application/json"), ("x" * (8 * 1024 * 1024 + 1), "application/json")],
                         ids=["missing-fields", "html", "broken-json", "oversized"])
def test_incompatible_or_oversized_responses_fail_safely(body, media):
    with ApiClient(session=Session(lambda *args: response(body, media=media))) as client:
        with pytest.raises(ApiClientError, match="incompatible"):
            client.call("summary", PAYLOAD)


def test_bad_payload_cannot_be_sent_or_fallback_and_fallback_requires_opt_in():
    with ApiClient(session=Session(lambda *args: pytest.fail("Invalid input was sent"))) as client:
        with pytest.raises(ApiClientError, match="Correct the request"):
            client.call("forecast", {**PAYLOAD, "horizon_days": True})
        with pytest.raises(ValueError, match="Explicit fallback"):
            client.call("summary", PAYLOAD, allow_fallback=True)
        with pytest.raises(ValueError, match="supported analytics"):
            client.call("PRIVATE_URL", PAYLOAD)
    for timeout in (True, float("nan"), float("inf"), 0, 181):
        with pytest.raises(ValueError):
            ApiClient(timeout_seconds=timeout)
