"""Deterministic stress scenarios applied to the baseline event ledger."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.analytics_utils import round_cents
from src.forecasting import ForecastEvent, ForecastResult, project_events


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    income_decrease_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    expense_increase_pct: Decimal = Field(default=Decimal(0), ge=0, le=1000)
    emergency_expense: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    emergency_date: date | None = None
    delayed_event_id: str | None = None
    delay_days: int = Field(default=0, ge=0, le=365, strict=True)

    @model_validator(mode="after")
    def check_linked_controls(self) -> ScenarioConfig:
        if self.emergency_expense > 0 and self.emergency_date is None:
            raise ValueError("An emergency_date is required for an emergency expense")
        if bool(self.delayed_event_id) != (self.delay_days > 0):
            raise ValueError("A delayed_event_id and positive delay_days must be provided together")
        if self.delayed_event_id is not None and not self.delayed_event_id.strip():
            raise ValueError("delayed_event_id must be nonblank")
        return self


@dataclass(frozen=True)
class ScenarioResult:
    baseline: ForecastResult
    forecast: ForecastResult
    config: ScenarioConfig
    deferred_events: tuple[ForecastEvent, ...]

    @property
    def closing_balance_change_cents(self) -> int:
        return int(self.forecast.daily.iloc[-1]["balance_cents"]) - int(self.baseline.daily.iloc[-1]["balance_cents"])


def simulate_scenario(baseline: ForecastResult, config: ScenarioConfig) -> ScenarioResult:
    """Reduce future income, increase future expenses, add an emergency, or delay
    one selected recurring inflow. Opening balance and historical rows stay fixed.

    An inflow delayed beyond the horizon is preserved in deferred_events and is
    excluded from in-horizon totals. It is never silently moved to the final day.
    """
    if not isinstance(config, ScenarioConfig):
        raise ValueError("Pass a validated ScenarioConfig")
    end = baseline.as_of + timedelta(days=baseline.horizon_days)
    if config.emergency_date is not None and not baseline.as_of < config.emergency_date <= end:
        raise ValueError("Emergency date must fall within the forecast horizon")
    if config.delayed_event_id is not None:
        selected = next((event for event in baseline.events if event.event_id == config.delayed_event_id), None)
        if selected is None:
            raise ValueError("Delayed payment event does not exist in the baseline")
        if selected.amount_cents <= 0 or selected.kind != "recurring":
            raise ValueError("Only a positive recurring payment can be delayed")
    events = []
    deferred = []
    for event in baseline.events:
        multiplier = (1 - config.income_decrease_pct / 100 if event.amount_cents > 0
                      else 1 + config.expense_increase_pct / 100)
        changed = replace(event, amount_cents=round_cents(Decimal(event.amount_cents) * multiplier))
        if event.event_id == config.delayed_event_id:
            try:
                changed = replace(changed, date=changed.date + timedelta(days=config.delay_days))
            except OverflowError as exc:
                raise ValueError("Delayed date exceeds supported calendar range") from exc
            if changed.date > end:
                deferred.append(changed)
                continue
        events.append(changed)
    if config.emergency_expense:
        # Emergency is the user's explicit amount, added after recurring-expense inflation.
        events.append(ForecastEvent("scenario-emergency", config.emergency_date,
                                    -int(config.emergency_expense * 100), "emergency", "One-time emergency expense"))
    ordered = tuple(sorted(events, key=lambda event: (event.date, event.event_id)))
    warnings = (*baseline.warnings, "Scenario changes are hypothetical; they are not predictions of actual future events.")
    if deferred:
        warnings += ("The delayed payment falls beyond the projection horizon and is excluded from its inflows.",)
    daily = project_events(baseline.as_of, baseline.horizon_days, baseline.current_balance_cents,
                           baseline.cash_threshold_cents, ordered)
    forecast = replace(baseline, daily=daily, events=ordered, warnings=warnings,
                       assumptions=(*baseline.assumptions,
                                    f"Scenario: income -{config.income_decrease_pct}%, expenses +{config.expense_increase_pct}%; round each event half up to integer cents.",
                                    "Emergency expense is added at its exact supplied amount after percentage changes; income delays apply after scaling."))
    return ScenarioResult(baseline, forecast, config, tuple(deferred))
