from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependencies import analytics_service, model_service
from api.schemas import requests as req
from api.schemas import responses as res
from api.services.analytics_service import AnalyticsService
from src.llm_service import OllamaService

router = APIRouter(prefix="/api/v1")
Service = Annotated[AnalyticsService, Depends(analytics_service)]
Model = Annotated[OllamaService, Depends(model_service)]


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
