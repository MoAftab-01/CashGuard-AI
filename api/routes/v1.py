from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.dependencies import analytics_service, model_service
from api.schemas import requests as req
from api.schemas import responses as res
from api.services.analytics_service import AnalyticsService
from src.llm_service import OllamaService, OllamaStatus
from src.inference import create_provider
from src.dashboard_wire import AnomalyWire, DashboardWire, ImportWire, ScenarioWire

router = APIRouter(prefix="/api/v1")
Service = Annotated[AnalyticsService, Depends(analytics_service)]
Model = Annotated[OllamaService, Depends(model_service)]


@router.post("/transactions/csv", response_model=ImportWire)
def import_csv(payload: req.CSVRequest, service: Service):
    return service.import_csv(payload)


@router.post("/dashboard/prepare", response_model=DashboardWire)
def dashboard(payload: req.AnalysisRequest, service: Service):
    return service.dashboard(payload)


@router.post("/dashboard/scenario", response_model=ScenarioWire)
def dashboard_scenario(payload: req.ScenarioRequest, service: Service):
    return service.scenario_wire(payload)


@router.post("/dashboard/anomalies", response_model=AnomalyWire)
def dashboard_anomalies(payload: req.HistoryRequest, service: Service):
    return AnomalyWire.pack(service.anomalies(payload))


@router.post("/models/status", response_model=OllamaStatus)
def model_status(payload: req.ModelRequest, request: Request):
    service = create_provider(request.app.state.provider_settings, request.app.state.provider_budget,
                              getattr(request.state, "session_id", "local"), model=payload.model,
                              timeout_seconds=float(payload.timeout_seconds))
    try:
        return service.check_availability()
    finally:
        service.close()


@router.post("/transactions/validate", response_model=res.ValidationResponse)
def validate(payload: req.ImportRequest, service: Service):
    return service.validate(payload)


@router.post("/analytics/summary", response_model=res.SummaryResponse)
def summary(payload: req.AnalysisRequest, service: Service):
    return service.summary(payload)


@router.post("/forecast", response_model=res.ForecastResponse)
def forecast(payload: req.AnalysisRequest, service: Service):
    return service.forecast_output(payload)


@router.post("/anomalies/detect", response_model=res.AnomalyResponse)
def anomalies(payload: req.HistoryRequest, service: Service):
    return service.anomaly_output(payload)


@router.post("/risk/analyze", response_model=res.RiskResponse)
def risk(payload: req.AnalysisRequest, service: Service):
    return service.risk(payload)


@router.post("/scenarios/simulate", response_model=res.ScenarioResponse)
def scenarios(payload: req.ScenarioRequest, service: Service):
    return service.scenario(payload)


@router.post("/insights/generate", response_model=res.InsightsResponse)
def insights(payload: req.InsightsRequest, service: Service, model: Model):
    return service.insights(payload, model)
