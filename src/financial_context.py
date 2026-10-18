"""Validated, minimized financial evidence for local explanations.

No descriptions, merchant names, accounts, transaction IDs, raw histories or
free-form category labels cross this boundary. Missing metrics stay missing.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.dashboard_service import DashboardBundle, format_cents
from src.scenario_simulator import ScenarioResult

FACTOR_NAMES = ("projected_shortfall", "low_cash_buffer", "expense_to_income", "spending_volatility", "unusual_activity")


class ContextError(ValueError):
    """Financial evidence could not be validated; never includes input values."""


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RiskContribution(EvidenceModel):
    name: Literal["projected_shortfall", "low_cash_buffer", "expense_to_income", "spending_volatility", "unusual_activity"]
    points: int = Field(ge=0, le=100, strict=True)
    maximum: int = Field(gt=0, le=100, strict=True)
    assessed: bool

    @model_validator(mode="after")
    def check_points(self) -> RiskContribution:
        if self.points > self.maximum:
            raise ValueError("Invalid contribution")
        return self


class ScenarioEvidence(EvidenceModel):
    income_reduction_pct: Decimal = Field(ge=0, le=100)
    expense_increase_pct: Decimal = Field(ge=0, le=1000)
    emergency_expense_cents: int = Field(ge=0, strict=True)
    payment_delay_days: int = Field(ge=0, le=365, strict=True)
    minimum_balance_cents: int = Field(strict=True)
    closing_balance_cents: int = Field(strict=True)
    closing_change_cents: int = Field(strict=True)
    threshold_breach_dates: tuple[date, ...]
    deferred_payments: int = Field(ge=0, strict=True)


class FinancialContext(EvidenceModel):
    currency: Literal["USD", "INR", "EUR", "GBP"]
    analysis_date: date
    period_start: date | None
    period_end: date | None
    estimated_balance_cents: int | None = Field(default=None, strict=True)
    opening_balance_cents: int | None = Field(default=None, strict=True)
    historical_income_cents: int | None = Field(default=None, ge=0, strict=True)
    historical_expenses_cents: int | None = Field(default=None, ge=0, strict=True)
    historical_net_cents: int | None = Field(default=None, strict=True)
    transaction_count: int | None = Field(default=None, ge=0, strict=True)
    expense_to_income_ratio: Decimal | None = Field(default=None, ge=0)
    cash_buffer_days: Decimal | None = None
    forecast_horizon_days: int = Field(ge=1, le=365, strict=True)
    minimum_projected_balance_cents: int | None = Field(default=None, strict=True)
    projected_closing_balance_cents: int | None = Field(default=None, strict=True)
    cash_threshold_cents: int = Field(strict=True)
    threshold_breach_dates: tuple[date, ...]
    risk_score: int | None = Field(default=None, ge=0, le=100, strict=True)
    risk_level: Literal["Low", "Moderate", "High", "Insufficient data"]
    data_sufficiency: Literal["limited", "insufficient", "adequate for heuristics"]
    risk_contributions: tuple[RiskContribution, ...]
    anomaly_scored_count: int = Field(ge=0, strict=True)
    unusual_count: int = Field(ge=0, strict=True)
    unscored_count: int = Field(ge=0, strict=True)
    unusual_expense_count: int = Field(ge=0, strict=True)
    largest_unusual_expense_cents: int | None = Field(default=None, ge=0, strict=True)
    scenario: ScenarioEvidence | None = None

    @model_validator(mode="after")
    def check_consistency(self) -> FinancialContext:
        if self.period_start and self.period_end and not self.period_start <= self.period_end <= self.analysis_date:
            raise ValueError("Invalid analysis period")
        if self.unusual_expense_count > self.unusual_count or self.unusual_count > self.anomaly_scored_count:
            raise ValueError("Invalid anomaly coverage")
        if self.transaction_count is not None and self.anomaly_scored_count + self.unscored_count != self.transaction_count:
            raise ValueError("Inconsistent transaction coverage")
        names = [item.name for item in self.risk_contributions]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate risk contributions")
        if self.risk_score is not None and sum(item.points for item in self.risk_contributions) != self.risk_score:
            raise ValueError("Risk score does not reconcile")
        try:
            end = self.analysis_date + timedelta(days=self.forecast_horizon_days)
        except OverflowError:
            raise ValueError("Projection exceeds supported calendar dates") from None
        for dates in (self.threshold_breach_dates, self.scenario.threshold_breach_dates if self.scenario else ()):
            if any(not self.analysis_date < day <= end for day in dates) or len(set(dates)) != len(dates):
                raise ValueError("Invalid projection dates")
        income, expenses, net = self.historical_income_cents, self.historical_expenses_cents, self.historical_net_cents
        if all(value is not None for value in (income, expenses, net)) and income - expenses != net:
            raise ValueError("Historical metrics do not reconcile")
        if all(value is not None for value in (self.opening_balance_cents, net, self.estimated_balance_cents)):
            if self.opening_balance_cents + net != self.estimated_balance_cents:
                raise ValueError("Balance does not reconcile")
        return self

    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def _cents(value: object) -> int | None:
    if value is None:
        return None
    amount = Decimal(str(value))
    if not amount.is_finite() or amount * 100 != (amount * 100).to_integral_value():
        raise ValueError("Invalid monetary evidence")
    return int(amount * 100)


def build_financial_context(bundle: DashboardBundle, currency: str = "USD", *,
                            scenario: ScenarioResult | None = None) -> FinancialContext:
    """Extract engine outputs; do not ask an LLM to calculate missing values."""
    try:
        m, f, a, r = bundle.metrics, bundle.forecast, bundle.anomalies, bundle.risk
        if a.as_of != f.as_of:
            raise ValueError("Mismatched evidence cutoff")
        factors = {item.name: item for item in r.factors}
        flagged = a.data.loc[a.data["is_anomaly"].fillna(False) & (a.data["amount_cents"] < 0)]
        scenario_evidence = None
        if scenario is not None:
            original = scenario.baseline
            if (original.as_of != f.as_of or original.current_balance_cents != f.current_balance_cents
                    or original.cash_threshold_cents != f.cash_threshold_cents or not original.daily.equals(f.daily)):
                raise ValueError("Scenario belongs to different analytics")
            scenario_evidence = ScenarioEvidence(
                income_reduction_pct=scenario.config.income_decrease_pct,
                expense_increase_pct=scenario.config.expense_increase_pct,
                emergency_expense_cents=int(scenario.config.emergency_expense * 100),
                payment_delay_days=scenario.config.delay_days,
                minimum_balance_cents=int(scenario.forecast.daily["balance_cents"].min()),
                closing_balance_cents=int(scenario.forecast.daily.iloc[-1]["balance_cents"]),
                closing_change_cents=scenario.closing_balance_change_cents,
                threshold_breach_dates=scenario.forecast.shortage_dates,
                deferred_payments=len(scenario.deferred_events),
            )
        def observed(name: str) -> Decimal | None:
            value = factors[name].observed_value if name in factors else None
            return Decimal(str(value)) if value is not None else None
        return FinancialContext(
            currency=currency, analysis_date=f.as_of, period_start=m.start_date, period_end=m.end_date,
            estimated_balance_cents=_cents(m.estimated_balance), opening_balance_cents=_cents(m.opening_balance),
            historical_income_cents=_cents(m.total_income), historical_expenses_cents=_cents(m.total_expenses),
            historical_net_cents=_cents(m.net_cash_flow), transaction_count=m.transaction_count,
            expense_to_income_ratio=observed("expense_to_income"), cash_buffer_days=observed("low_cash_buffer"),
            forecast_horizon_days=f.horizon_days,
            minimum_projected_balance_cents=int(f.daily["balance_cents"].min()) if not f.daily.empty else None,
            projected_closing_balance_cents=int(f.daily.iloc[-1]["balance_cents"]) if not f.daily.empty else None,
            cash_threshold_cents=f.cash_threshold_cents, threshold_breach_dates=f.shortage_dates,
            risk_score=r.score, risk_level=r.level, data_sufficiency=r.data_sufficiency,
            risk_contributions=tuple(RiskContribution(name=item.name, points=item.points, maximum=item.max_points,
                                                     assessed=item.evaluated) for item in r.factors),
            anomaly_scored_count=a.scored_count, unusual_count=a.anomaly_count,
            unscored_count=len(a.data) - a.scored_count, unusual_expense_count=len(flagged),
            largest_unusual_expense_cents=int(flagged["amount_cents"].abs().max()) if not flagged.empty else None,
            scenario=scenario_evidence,
        )
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError, ArithmeticError) as exc:
        raise ContextError("Financial context is inconsistent or incomplete. Recalculate analytics before generating insights.") from None


class EvidenceFact(EvidenceModel):
    label: str
    value: str
    basis: str


def evidence_catalog(context: FinancialContext) -> dict[str, EvidenceFact]:
    """Trusted display values live here, never in model-generated numeric prose."""
    facts: dict[str, EvidenceFact] = {}
    def add(key: str, label: str, value: object, basis: str) -> None:
        if value is not None:
            facts[key] = EvidenceFact(label=label, value=str(value), basis=basis)
    for key, label, value, basis in (
        ("estimated_balance", "Estimated cash balance", context.estimated_balance_cents, "Estimated"),
        ("historical_income", "Total income", context.historical_income_cents, "Historical"),
        ("historical_expenses", "Total expenses", context.historical_expenses_cents, "Historical"),
        ("historical_net", "Net cash flow", context.historical_net_cents, "Historical"),
        ("forecast_minimum", "Minimum projected balance", context.minimum_projected_balance_cents, "Projected estimate"),
        ("forecast_closing", "Projected closing balance", context.projected_closing_balance_cents, "Projected estimate"),
        ("cash_threshold", "Minimum cash threshold", context.cash_threshold_cents, "User configured"),
        ("unusual_expense_peak", "Largest flagged expense", context.largest_unusual_expense_cents, "Unusual, not confirmed fraud"),
    ):
        if value is not None:
            add(key, label, format_cents(value, context.currency), basis)
    add("analysis_date", "Analysis date", context.analysis_date, "Inclusive historical cutoff")
    if context.period_start is not None and context.period_end is not None:
        add("analysis_period", "Observed period", f"{context.period_start} through {context.period_end}", "Historical")
    add("expense_ratio", "Expense-to-income ratio", context.expense_to_income_ratio, "Historical risk window; ratio, not percentage")
    add("cash_buffer", "Cash buffer in days", context.cash_buffer_days, "Historical expense coverage")
    add("forecast_horizon", "Forecast horizon in days", context.forecast_horizon_days, "Projected estimate")
    add("threshold_breaches", "Days below threshold", len(context.threshold_breach_dates), "Projected estimate")
    add("threshold_dates", "Below-threshold dates", ", ".join(day.isoformat() for day in context.threshold_breach_dates) or "None projected", "Projected estimate")
    add("risk_indicator", "Risk indicator", context.risk_level, "Unvalidated heuristic, not a credit score")
    add("risk_score", "Risk points", context.risk_score, "Unvalidated heuristic")
    add("data_sufficiency", "Data sufficiency", context.data_sufficiency, "Coverage, not statistical confidence")
    add("anomaly_scored", "Transactions scored", context.anomaly_scored_count, "Chronological model coverage")
    add("anomaly_unusual", "Transactions flagged unusual", context.unusual_count, "Not confirmed fraud")
    add("anomaly_unscored", "Unscored transactions", context.unscored_count, "Not assessed as normal")
    add("unusual_expenses", "Expenses flagged unusual", context.unusual_expense_count, "Not confirmed fraud")
    for item in context.risk_contributions:
        add(f"factor_{item.name}", item.name.replace("_", " ").title(),
            f"{item.points}/{item.maximum} points" if item.assessed else "Not assessed", "Heuristic risk contribution")
    add("scenario_status", "Scenario availability", "Configured" if context.scenario else "No scenario configured", "Hypothetical")
    if context.scenario:
        scenario = context.scenario
        for key, label, value in (
            ("scenario_closing", "Scenario projected closing balance", scenario.closing_balance_cents),
            ("scenario_minimum", "Scenario minimum balance", scenario.minimum_balance_cents),
            ("scenario_change", "Scenario closing balance change", scenario.closing_change_cents),
            ("scenario_emergency", "Configured emergency expense", scenario.emergency_expense_cents),
        ):
            add(key, label, format_cents(value, context.currency), "Hypothetical scenario")
        add("scenario_income_reduction", "Income reduction percentage", scenario.income_reduction_pct, "User configured percentage")
        add("scenario_expense_increase", "Expense increase percentage", scenario.expense_increase_pct, "User configured percentage")
        add("scenario_delay", "Payment delay in days", scenario.payment_delay_days, "User configured")
        add("scenario_breaches", "Scenario below-threshold days", len(scenario.threshold_breach_dates), "Hypothetical")
        add("scenario_deferred", "Payments deferred beyond horizon", scenario.deferred_payments, "Hypothetical")
    return facts
