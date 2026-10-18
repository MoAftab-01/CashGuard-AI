"""Bounded loopback-only transport for future UI integration; no implicit fallback."""

import json
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

import requests
from pydantic import ValidationError

from api.schemas import requests as req
from api.schemas import responses as res
from src.settings import loopback_url

T = TypeVar("T")


@dataclass(frozen=True)
class BackendResult(Generic[T]):
    value: T
    mode: str
    warning: str | None = None


class ApiClientError(RuntimeError):
    MESSAGES = {
        "connection_error": "The local API is unavailable. Start it with python -m api.",
        "timeout": "The local API did not respond before the configured timeout.",
        "busy": "The local API is busy. Retry after the current analysis finishes.",
        "invalid_request": "Correct the request fields or transaction validation issues.",
        "request_too_large": "The request exceeds the local API byte limit. Use a smaller history.",
        "invalid_response": "The local API returned an incompatible response. Check client/server versions.",
        "http_error": "The local API could not complete the request. Check its local status and logs.",
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
        "validate": ("/api/v1/transactions/validate", req.ImportRequest, res.ValidationResponse),
        "summary": ("/api/v1/analytics/summary", req.AnalysisRequest, res.SummaryResponse),
        "forecast": ("/api/v1/forecast", req.AnalysisRequest, res.ForecastResponse),
        "anomalies": ("/api/v1/anomalies/detect", req.HistoryRequest, res.AnomalyResponse),
        "risk": ("/api/v1/risk/analyze", req.AnalysisRequest, res.RiskResponse),
        "scenario": ("/api/v1/scenarios/simulate", req.ScenarioRequest, res.ScenarioResponse),
        "insights": ("/api/v1/insights/generate", req.InsightsRequest, res.InsightsResponse),
    }

    def __init__(self, base_url="http://127.0.0.1:8000", *, timeout_seconds=30, session=None):
        self.base_url = loopback_url(base_url)
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 180:
            raise ValueError("Client timeout must be between 1 and 180 seconds")
        self.timeout_seconds = timeout_seconds
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
        headers = {"accept": "application/json"}
        if encoded is not None:
            headers["content-type"] = "application/json"
        try:
            with self.session.request("GET" if encoded is None else "POST", self.base_url + path,
                                      data=encoded, headers=headers, stream=True,
                                      timeout=(min(3, self.timeout_seconds), self.timeout_seconds),
                                      allow_redirects=False) as response:
                status = response.status_code
                if status != 200:
                    code = {422: "invalid_request", 413: "request_too_large", 503: "busy"}.get(status, "http_error")
                    raise ApiClientError(code, status)
                if response.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                    raise ApiClientError("invalid_response", status)
                content = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
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
