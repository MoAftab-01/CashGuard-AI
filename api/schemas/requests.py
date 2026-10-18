"""Strict transport bounds; reuse the established transaction/scenario contracts."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, field_validator

from src.data_processing import Transaction
from src.llm_service import OllamaSettings
from src.scenario_simulator import ScenarioConfig


def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Use a finite decimal number, never a boolean")
    return value


Money = Annotated[Decimal, BeforeValidator(numeric), Field(max_digits=12, decimal_places=2, allow_inf_nan=False)]
Percentage = Annotated[Decimal, BeforeValidator(numeric), Field(ge=0, le=1000, allow_inf_nan=False)]
CalendarDate = Annotated[date, BeforeValidator(Transaction.validate_date)]
Currency = Literal["USD", "INR", "EUR", "GBP"]
Engine = Literal["Calibrated amount review", "Calibrated Isolation Forest", "Legacy Isolation Forest"]


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    transactions: list[Transaction] = Field(min_length=1, max_length=2000)
    remove_ambiguous_duplicates: StrictBool = False
    reviewed_duplicates: StrictBool = False


class HistoryRequest(ImportRequest):
    as_of: CalendarDate | None = None
    currency: Currency = "USD"
    anomaly_engine: Engine = "Calibrated amount review"


class AnalysisRequest(HistoryRequest):
    opening_balance: Money
    cash_threshold: Money = Decimal("500.00")
    horizon_days: int = Field(default=30, ge=1, le=365, strict=True)
    include_irregular_income: StrictBool = False

    @field_validator("horizon_days", mode="before")
    @classmethod
    def integer_horizon(cls, value):
        if type(value) is not int:
            raise ValueError("Forecast horizon must be an integer")
        return value


class StrictScenario(ScenarioConfig):
    income_decrease_pct: Annotated[Percentage, Field(le=100)] = Decimal(0)
    expense_increase_pct: Percentage = Decimal(0)
    emergency_expense: Annotated[Money, Field(ge=0)] = Decimal(0)
    emergency_date: CalendarDate | None = None
    delayed_event_id: str | None = Field(default=None, max_length=500)


class ScenarioRequest(AnalysisRequest):
    scenario: StrictScenario


class InsightsRequest(AnalysisRequest):
    # Financial context/templates currently describe the dashboard's 30-day outlook.
    horizon_days: Literal[30] = 30
    model: str = Field(default="gemma3:4b", min_length=1, max_length=128)
    timeout_seconds: int = Field(default=30, ge=1, le=90, strict=True)
    scenario: StrictScenario | None = None

    @field_validator("model")
    @classmethod
    def validated_model(cls, value):
        return OllamaSettings.local_model_name(value)
