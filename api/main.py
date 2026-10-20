"""Factory supports isolated tests; the normal dashboard does not import FastAPI."""

import html
import json

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from api.policy import LocalPolicy, error_response
from api.routes.v1 import router
from api.schemas.responses import ErrorResponse, HealthResponse
from src.settings import Settings
from src.observability import Metrics
from src.inference import InferenceBudget, ProviderSettings


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_environment()
    application = FastAPI(title="CashGuard AI", version="0.9.0", docs_url=None, redoc_url=None,
                          description="Local financial research API. Estimates, not bank balances or fraud decisions.",
                          responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
    application.state.settings = settings
    application.state.analytics_ready = True
    application.state.metrics = Metrics(settings.metrics_enabled)
    application.state.provider_settings = ProviderSettings.from_environment(public_demo=settings.public_demo)
    application.state.provider_budget = InferenceBudget(application.state.provider_settings)
    application.add_middleware(LocalPolicy, settings=settings, metrics=application.state.metrics)
    application.include_router(router)

    @application.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        # Do not include Pydantic input/context, URLs, or exception reprs.
        from api.schemas.requests import AnalysisRequest, CSVRequest, ImportRequest, InsightsRequest, ModelRequest, StrictScenario
        from src.data_processing import Transaction
        known = {"body", "query", "path", "header", "scenario", "model", "timeout_seconds"}
        for schema in (AnalysisRequest, CSVRequest, ImportRequest, InsightsRequest, ModelRequest, StrictScenario, Transaction):
            known.update(schema.model_fields)
        issues = [{"row": None, "field": ".".join(str(part) if isinstance(part, int) or part in known else "unknown" for part in item["loc"]),
                   "message": "Invalid value: " + item["type"], "severity": "error"}
                  for item in exc.errors()[:30]]
        return error_response(request.state.request_id, "invalid_request", "Correct the indicated request fields.", issues=issues)

    @application.exception_handler(ValueError)
    @application.exception_handler(ValidationError)
    async def input_error(request: Request, exc):
        return error_response(request.state.request_id, "invalid_analysis",
                              "Check the analysis date, duplicate review, opening cash and scenario settings.")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(request.state.request_id, "http_error", "Resource or method unavailable.", exc.status_code)

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc):
        return error_response(request.state.request_id, "internal_error", "Request could not be completed.", 500)

    @application.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(status="ok", analytics_ready=application.state.analytics_ready)

    @application.get("/ready", response_model=HealthResponse)
    def ready():
        if not application.state.analytics_ready:
            from fastapi.responses import JSONResponse
            return JSONResponse(HealthResponse(status="not_ready", analytics_ready=False).model_dump(), status_code=503)
        return HealthResponse(status="ready", analytics_ready=True)

    @application.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    def documentation():
        # Offline documentation: no third-party scripts can observe financial inputs.
        schema = html.escape(json.dumps(application.openapi(), indent=2))
        return "<!doctype html><title>CashGuard API</title><h1>CashGuard local API</h1><p>" \
               "Local mode must remain on loopback. Hosted endpoints require configured service credentials. Money is decimal text or integer cents. " \
               "<a href='/openapi.json'>OpenAPI JSON</a></p><pre>" + schema + "</pre>"

    @application.get("/metrics", include_in_schema=False)
    def metrics():
        from starlette.responses import Response
        if not settings.metrics_enabled:
            raise HTTPException(404)
        return Response(application.state.metrics.render(),
                        media_type="text/plain; version=0.0.4; charset=utf-8")

    return application


app = create_app()
