"""Inject stateless analytics and a bounded, strictly loopback Ollama client."""

from api.schemas.requests import InsightsRequest
from api.services.analytics_service import AnalyticsService
from src.llm_service import OllamaService, OllamaSettings
from src.observability import ObservedModel
from fastapi import Request


def analytics_service(request: Request):
    return AnalyticsService(request.app.state.metrics)


def model_service(payload: InsightsRequest, request: Request):
    settings = OllamaSettings.from_environment(model=payload.model,
                                               timeout_seconds=float(payload.timeout_seconds))
    settings = settings.model_copy(update={"max_attempts": 1})
    with OllamaService(settings) as service:
        yield ObservedModel(service, request.app.state.metrics)
