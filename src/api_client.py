"""Bounded loopback-only transport for future UI integration; no implicit fallback."""

import json
from time import sleep, monotonic
from uuid import uuid4
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

import requests
from pydantic import ValidationError

from api.schemas import requests as req
from api.schemas import responses as res
from src.settings import configured_api_url
from src.dashboard_wire import AnomalyWire, DashboardWire, ImportWire, ScenarioWire

T = TypeVar("T")


@dataclass(frozen=True)
class BackendResult(Generic[T]):
    value: T
    mode: str
    warning: str | None = None


class ApiClientError(RuntimeError):
    MESSAGES = {
        "connection_error": "The analytics API is unavailable. Retry or contact the operator. For local development, start python -m api.",
        "timeout": "The analytics API did not respond before the configured timeout.",
        "busy": "The analytics API is busy. Retry after the current analysis finishes.",
        "invalid_request": "Correct the request fields or transaction validation issues.",
        "request_too_large": "The request exceeds the local API byte limit. Use a smaller history.",
        "invalid_response": "The local API returned an incompatible response. Check client/server versions.",
        "http_error": "The local API could not complete the request. Check its local status and logs.",
        "unauthorized": "The configured API credential is missing or invalid. Contact the demo operator.",
        "rate_limited": "The demo request limit has been reached. Wait briefly before trying again.",
    }

    def __init__(self, code, status=None):
        self.code, self.status = code, status
        self.retryable = code in {"connection_error", "timeout", "busy"}
        super().__init__(self.MESSAGES[code])


class ApiClient:
    """No proxies, redirects, external DNS, payload logging, cache or automatic retry.

    Explicit fallback returns provenance plus a visible warning for a future UI.
    Callers must display that warning and continue using a coherent backend for the
    current analysis; this module does not switch any existing Streamlit page.
    """

    CONTRACTS = {
        "import_csv": ("/api/v1/transactions/csv", req.CSVRequest, ImportWire),
        "dashboard": ("/api/v1/dashboard/prepare", req.AnalysisRequest, DashboardWire),
        "dashboard_scenario": ("/api/v1/dashboard/scenario", req.ScenarioRequest, ScenarioWire),
        "dashboard_anomalies": ("/api/v1/dashboard/anomalies", req.HistoryRequest, AnomalyWire),
        "model_status": ("/api/v1/models/status", req.ModelRequest, res.ModelStatusResponse),
        "validate": ("/api/v1/transactions/validate", req.ImportRequest, res.ValidationResponse),
        "summary": ("/api/v1/analytics/summary", req.AnalysisRequest, res.SummaryResponse),
        "forecast": ("/api/v1/forecast", req.AnalysisRequest, res.ForecastResponse),
        "anomalies": ("/api/v1/anomalies/detect", req.HistoryRequest, res.AnomalyResponse),
        "risk": ("/api/v1/risk/analyze", req.AnalysisRequest, res.RiskResponse),
        "scenario": ("/api/v1/scenarios/simulate", req.ScenarioRequest, res.ScenarioResponse),
        "insights": ("/api/v1/insights/generate", req.InsightsRequest, res.InsightsResponse),
    }

    def __init__(self, base_url="http://127.0.0.1:8000", *, timeout_seconds=30, session=None, max_retries=0,
                 allowed_hosts=(), allow_private_http=False, token=None, session_id=None):
        self.base_url = configured_api_url(base_url, allowed_hosts, allow_private_http=allow_private_http)
        self.token = token.get_secret_value() if hasattr(token, "get_secret_value") else token
        self.session_id = session_id
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 180:
            raise ValueError("Client timeout must be between 1 and 180 seconds")
        self.timeout_seconds = timeout_seconds
        if type(max_retries) is not int or not 0 <= max_retries <= 2:
            raise ValueError("Use zero to two bounded retries")
        self.max_retries = max_retries
        self.session = session if session is not None else requests.Session()
        self.session.trust_env = False
        self.session.proxies.clear()

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _request(self, path, response_model, encoded=None):
        retries = 0 if path == "/api/v1/insights/generate" else self.max_retries
        for attempt in range(retries + 1):
            try:
                return self._request_once(path, response_model, encoded)
            except ApiClientError as exc:
                if not exc.retryable or attempt == retries:
                    raise
                sleep(.1 * (2 ** attempt))

    def _request_once(self, path, response_model, encoded=None):
        deadline = monotonic() + self.timeout_seconds
        headers = {"accept": "application/json", "x-request-id": uuid4().hex}
        if self.token:
            headers["authorization"] = "Bearer " + self.token
        if self.session_id:
            headers["x-cashguard-session"] = self.session_id
        if encoded is not None:
            headers["content-type"] = "application/json"
        try:
            with self.session.request("GET" if encoded is None else "POST", self.base_url + path,
                                      data=encoded, headers=headers, stream=True,
                                      timeout=(min(3, self.timeout_seconds), self.timeout_seconds),
                                      allow_redirects=False) as response:
                status = response.status_code
                if status != 200:
                    code = {401: "unauthorized", 403: "unauthorized", 429: "rate_limited",
                            422: "invalid_request", 413: "request_too_large", 503: "busy"}.get(status, "http_error")
                    raise ApiClientError(code, status)
                if response.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                    raise ApiClientError("invalid_response", status)
                content = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if monotonic() > deadline:
                        raise ApiClientError("timeout")
                    content.extend(chunk)
                    if len(content) > 8 * 1024 * 1024:
                        raise ApiClientError("invalid_response", status)
                try:
                    return response_model.model_validate_json(bytes(content))
                except (ValidationError, ValueError):
                    raise ApiClientError("invalid_response", status) from None
        except requests.Timeout:
            raise ApiClientError("timeout") from None
        except requests.RequestException:
            raise ApiClientError("connection_error") from None

    def health(self):
        return self._request("/health", res.HealthResponse)

    def ready(self):
        return self._request("/ready", res.HealthResponse)

    def call(self, operation, payload, *, allow_fallback=False, direct: Callable | None = None):
        if operation not in self.CONTRACTS:
            raise ValueError("Choose a supported analytics operation")
        if type(allow_fallback) is not bool or allow_fallback and not callable(direct):
            raise ValueError("Explicit fallback requires a direct callable and boolean opt-in")
        path, request_model, response_model = self.CONTRACTS[operation]
        try:
            request = request_model.model_validate(payload)
        except (ValidationError, ValueError):
            raise ApiClientError("invalid_request") from None
        encoded = json.dumps(request.model_dump(mode="json"), allow_nan=False, separators=(",", ":")).encode()
        if len(encoded) > 1024 * 1024:
            raise ApiClientError("request_too_large")
        try:
            return BackendResult(self._request(path, response_model, encoded), "api")
        except ApiClientError as exc:
            if not allow_fallback or not exc.retryable:
                raise
            # Revalidate fallback against the same response contract. Invalid local
            # results and programming errors are surfaced rather than masked.
            value = response_model.model_validate(direct(request))
            return BackendResult(value, "direct_fallback",
                                 "Local API unavailable or busy. Explicit direct fallback was used; all displayed analytics must use this mode.")
