"""Allowlisted structured events; no payloads, prompts, exception text or secrets."""

import contextvars
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, ProcessCollector, generate_latest

request_id = contextvars.ContextVar("cashguard_request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = {"timestamp": datetime.now(timezone.utc).isoformat(),
                 "severity": record.levelname, "component": record.name,
                 "request_id": request_id.get(),
                 "event_type": getattr(record, "event_type", "component_event")}
        # Existing engine text messages are deliberately not copied: some future
        # third-party dependency might log inputs or exception details.
        for name in ("duration_seconds", "status", "route", "method", "code"):
            value = getattr(record, name, None)
            if value is not None:
                event[name] = value
        return json.dumps(event, allow_nan=False)


def configure_logging(level="INFO"):
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


class Metrics:
    """Per-application metrics with bounded labels and no financial values."""

    ROUTES = frozenset({"/health", "/ready", "/docs", "/openapi.json", "/metrics",
        "/api/v1/transactions/csv", "/api/v1/dashboard/prepare", "/api/v1/dashboard/anomalies",
        "/api/v1/dashboard/scenario", "/api/v1/models/status",
        "/api/v1/transactions/validate", "/api/v1/analytics/summary", "/api/v1/forecast",
        "/api/v1/anomalies/detect", "/api/v1/risk/analyze", "/api/v1/scenarios/simulate", "/api/v1/insights/generate"})
    OPERATIONS = frozenset({"forecast", "anomaly", "llm"})
    FAILURES = frozenset({"connection_error", "timeout", "model_missing", "remote_model", "unsupported_model",
                        "invalid_response", "http_error", "invalid_metadata", "configuration", "unexpected",
                        "disabled", "quota_exceeded"})

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.registry = CollectorRegistry()
        ProcessCollector(registry=self.registry)
        self.active = Gauge("cashguard_inflight_analytics", "Accepted analytics requests currently using capacity", registry=self.registry)
        self.provider_available = Gauge("cashguard_inference_available", "Observed availability, -1 unassessed",
                                        ["provider"], registry=self.registry)
        for provider in ("ollama", "huggingface", "deterministic"):
            self.provider_available.labels(provider).set(-1)
        self.requests = Counter("cashguard_http_requests", "HTTP requests by route template and status class",
                                ["route", "method", "status_class"], registry=self.registry)
        self.latency = Histogram("cashguard_http_duration_seconds", "HTTP request duration",
                                  ["route", "method"], registry=self.registry)
        self.operations = Histogram("cashguard_operation_duration_seconds", "API service operation duration",
                                     ["operation", "result"], registry=self.registry,
                                     buckets=(.01, .05, .1, .5, 1, 2, 5, 10, 30, 60, 120, 180))
        self.llm_failures = Counter("cashguard_llm_failures", "Local generation failures by bounded reason",
                                   ["reason"], registry=self.registry)
        self.model_available = Gauge("cashguard_local_model_available", "Last requested local model availability: -1 unknown, 0 unavailable, 1 available",
                                    registry=self.registry)
        self.model_available.set(-1)

    def observe_http(self, route, method, status, seconds):
        if not self.enabled:
            return
        route = route if route in self.ROUTES else "unmatched"
        method = method if method in {"GET", "POST", "HEAD", "OPTIONS"} else "OTHER"
        status_class = f"{status // 100}xx" if 100 <= status < 600 else "other"
        self.requests.labels(route, method, status_class).inc()
        self.latency.labels(route, method).observe(seconds)

    @contextmanager
    def measure(self, operation):
        if operation not in self.OPERATIONS:
            raise ValueError("Unsupported operation label")
        beginning, result = perf_counter(), "success"
        try:
            yield
        except Exception:
            result = "error"
            raise
        finally:
            if self.enabled:
                self.operations.labels(operation, result).observe(perf_counter() - beginning)

    def model_failure(self, code, provider="ollama"):
        if not self.enabled:
            return
        provider = provider if provider in {"ollama", "huggingface", "deterministic"} else "ollama"
        code = code if code in self.FAILURES else "unexpected"
        self.llm_failures.labels(code).inc()
        if code in {"connection_error", "model_missing", "remote_model", "unsupported_model", "invalid_metadata", "configuration", "disabled"}:
            self.provider_available.labels(provider).set(0)
            if provider == "ollama":
                self.model_available.set(0)

    def render(self):
        return generate_latest(self.registry)


class ObservedModel:
    def __init__(self, service, metrics):
        self.service, self.metrics, self.settings = service, metrics, service.settings

    def generate(self, context):
        from src.llm_service import LocalLLMError
        provider = getattr(self.settings, "provider", "ollama")
        provider = provider if provider in {"ollama", "huggingface", "deterministic"} else "ollama"
        try:
            with self.metrics.measure("llm"):
                result = self.service.generate(context)
            if self.metrics.enabled:
                self.metrics.provider_available.labels(provider).set(1)
                if provider == "ollama":
                    self.metrics.model_available.set(1)
            return result
        except LocalLLMError as exc:
            self.metrics.model_failure(exc.code, provider)
            raise
        except Exception:
            self.metrics.model_failure("unexpected", provider)
            raise
