"""Inject stateless analytics and a bounded, strictly loopback Ollama client."""

from api.schemas.requests import InsightsRequest
from api.services.analytics_service import AnalyticsService
from src.llm_service import OllamaService, OllamaSettings
from src.observability import ObservedModel
from fastapi import Request
from src.inference import create_provider


def analytics_service(request: Request):
    return AnalyticsService(request.app.state.metrics)


def model_service(payload: InsightsRequest, request: Request):
    service = create_provider(request.app.state.provider_settings, request.app.state.provider_budget,
                              getattr(request.state, "session_id", "local"), model=payload.model,
                              timeout_seconds=float(payload.timeout_seconds))
    try:
        yield ObservedModel(service, request.app.state.metrics)
    finally:
        service.close()
