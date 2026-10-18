"""Exact money is decimal text/integer cents; unknown model values remain null."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from api.schemas.requests import Currency
from src.data_processing import Transaction
from src.financial_context import EvidenceFact
from src.insight_prompts import StructuredInsights


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Issue(ResponseModel):
    row: int | None = None
    field: str
    message: str
    severity: Literal["error", "warning"] = "error"


class ErrorDetail(ResponseModel):
    code: str
    message: str
    issues: list[Issue] = []


class ErrorResponse(ResponseModel):
    request_id: str
    error: ErrorDetail


class ValidationResponse(ResponseModel):
    valid: bool
    analytics_ready: bool
    input_rows: int
    duplicates_removed: int
    issues: list[Issue]
    transactions: list[Transaction]


class FinancialMetrics(ResponseModel):
    transaction_count: int
    total_income: Decimal
    total_expenses: Decimal
    net_cash_flow: Decimal
    opening_balance: Decimal
    estimated_balance: Decimal
    start_date: date | None
    end_date: date | None


class SummaryResponse(ResponseModel):
    currency: Currency
    as_of: date
    balance_basis: Literal["reconstructed_estimate"] = "reconstructed_estimate"
    metrics: FinancialMetrics
    warnings: list[str]


class ProjectionDay(ResponseModel):
    date: date
    inflow_cents: int
    outflow_cents: int
    net_cents: int
    balance_cents: int
    below_threshold: bool


class Event(ResponseModel):
    event_id: str
    date: date
    amount_cents: int
    kind: str
    description: str


class ForecastResponse(ResponseModel):
    currency: Currency
    as_of: date
    horizon_days: int
    current_balance_cents: int
    cash_threshold_cents: int
    history_days: int
    history_rows: int
    daily: list[ProjectionDay]
    events: list[Event]
    shortage_dates: list[date]
    assumptions: list[str]
    warnings: list[str]
    balance_basis: Literal["reconstructed_estimate"] = "reconstructed_estimate"


class AnomalyRow(ResponseModel):
    date: date
    description: str
    category: str
    amount_cents: int
    is_anomaly: bool | None
    anomaly_score: float | None
    explanation: str
    training_end: date | None
    calibration_end: date | None = None
    severity: str | None = None
    decision_threshold: float | None = None
    calibrated_percentile: float | None = None


class AnomalyResponse(ResponseModel):
    currency: Currency
    as_of: date
    engine: str
    scored_count: int
    anomaly_count: int
    unscored_count: int
    transactions: list[AnomalyRow]
    warnings: list[str]


class RiskFactor(ResponseModel):
    name: str
    points: int
    max_points: int
    observed_value: float | None
    explanation: str
    evaluated: bool


class RiskResponse(ResponseModel):
    currency: Currency
    as_of: date
    score: int | None
    level: str
    data_sufficiency: str
    factors: list[RiskFactor]
    warnings: list[str]
    shortage_dates: list[date]


class Comparison(ResponseModel):
    baseline_minimum_cents: int
    scenario_minimum_cents: int
    closing_change_cents: int
    additional_breach_dates: list[date]
    resolved_breach_dates: list[date]


class ScenarioResponse(ResponseModel):
    baseline: ForecastResponse
    simulated: ForecastResponse
    comparison: Comparison
    deferred_events: list[Event]


class InsightsResponse(ResponseModel):
    source: Literal["ai", "deterministic"]
    model: str
    context_fingerprint: str
    insights: StructuredInsights | None
    evidence: dict[str, EvidenceFact]
    fallback: list[tuple[str, str]]
    message: str
    error_code: str | None


class HealthResponse(ResponseModel):
    status: str
    analytics_ready: bool
    optional_services_required: bool = False
