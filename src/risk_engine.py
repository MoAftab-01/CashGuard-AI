"""Transparent heuristic indicators, not a credit score or regulated risk rating."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType

import numpy as np
import pandas as pd

from src.analytics_utils import calendar_days, positive_integer, transaction_snapshot
from src.anomaly_detection import AnomalyResult
from src.forecasting import ForecastResult

# Fixed budgeting policy, not learned weights. Detailed boundaries are stated in
# each factor's explanation and docs/phase5_evaluation.md. Total capacity = 100.
RISK_WEIGHTS = MappingProxyType({"projected_shortfall": 30, "low_cash_buffer": 25,
                                "expense_to_income": 20, "spending_volatility": 15,
                                "unusual_activity": 10})
MODERATE_SCORE = 30
HIGH_SCORE = 60


@dataclass(frozen=True)
class RiskFactor:
    name: str
    points: int
    max_points: int
    observed_value: float | None
    explanation: str
    evaluated: bool = True


@dataclass(frozen=True)
class RiskResult:
    score: int | None
    level: str
    data_sufficiency: str
    factors: tuple[RiskFactor, ...]
    warnings: tuple[str, ...]


def assess_risk(data: pd.DataFrame, forecast: ForecastResult, *, anomalies: AnomalyResult | None = None,
                history_window_days: int = 90) -> RiskResult:
    """Use historical rows through the forecast cutoff and its future estimates.

    Additive points: projected shortfall 30, current cash buffer 25,
    expense/income ratio 20, daily expense volatility 15, unusual activity 10.
    Scores with missing inputs are provisional lower bounds, not calibrated risk.
    """
    positive_integer(history_window_days, "history_window_days")
    known, cutoff = transaction_snapshot(data, forecast.as_of)
    earliest = cutoff - timedelta(days=min(history_window_days - 1, (cutoff - date.min).days))
    history = known.loc[known["date"] >= earliest]
    days = (cutoff - min(history["date"])).days + 1 if len(history) else 0
    expenses = -sum(int(value) for value in history["amount_cents"] if value < 0)
    income = sum(int(value) for value in history["amount_cents"] if value > 0)
    daily_expense = expenses / max(days, 1)
    minimum = int(forecast.daily["balance_cents"].min())
    shortfall_points = 30 if minimum < 0 else 15 if forecast.shortage_dates else 0
    shortfall = RiskFactor("projected_shortfall", shortfall_points, RISK_WEIGHTS["projected_shortfall"], minimum / 100,
                           "30 points if any projected balance is negative; 15 if only the configured threshold is breached. Review payment timing and planned outflows.")
    buffer = forecast.current_balance_cents / daily_expense if daily_expense else None
    buffer_points = (25 if forecast.current_balance_cents < 0 or (buffer is not None and buffer < 7)
                     else 12 if buffer is not None and buffer < 30 else 0)
    cash_buffer = RiskFactor("low_cash_buffer", buffer_points, RISK_WEIGHTS["low_cash_buffer"], buffer,
                             "Current balance divided by historical daily expenses: 25 points below 7 days (or negative cash); 12 below 30 days. With no expenses, coverage is undefined. Consider retaining a cash buffer.")
    ratio = expenses / income if income else None
    ratio_points = 20 if (income == 0 and expenses > 0) or (ratio is not None and ratio > 1) else 10 if ratio is not None and ratio >= 0.8 else 0
    expense_ratio = RiskFactor("expense_to_income", ratio_points, RISK_WEIGHTS["expense_to_income"], ratio,
                               "20 points for expenses above income or expenses with no observed income; 10 for a ratio from 0.8 through 1. Review recurring commitments and income stability.")
    volatility = None
    if expenses and days:
        start = min(history["date"])
        totals = (-history.loc[history["amount_cents"] < 0].groupby("date")["amount_cents"].sum()).to_dict()
        daily = np.asarray([totals.get(day, 0) for day in calendar_days(start, days)], dtype=float)
        volatility = float(daily.std(ddof=0) / daily.mean())
    volatility_points = 15 if volatility is not None and volatility > 1 else 7 if volatility is not None and volatility > 0.5 else 0
    spending_volatility = RiskFactor("spending_volatility", volatility_points, RISK_WEIGHTS["spending_volatility"], volatility,
                                     "Daily expense coefficient of variation (including zero-spend days): 15 points above 1; 7 above 0.5. Lumpy rent can raise this indicator; plan for large bill dates.")
    warnings = ["Heuristic, unvalidated budgeting indicator; not a credit score or regulated financial risk rating.",
                *forecast.warnings]
    anomaly_rate = None
    anomaly_points = 0
    scored_rows = 0
    if anomalies is not None:
        # Reject later-fit reports: filtering dates alone does not undo fit leakage.
        if anomalies.as_of > cutoff:
            raise ValueError("Anomaly report cutoff must not be later than forecast cutoff")
        reports = anomalies.data.loc[(anomalies.data["date"] <= cutoff) & (anomalies.data["date"] >= earliest)]
        assessed = reports.loc[reports["is_anomaly"].notna()]
        if any(end is None or end >= day for end, day in zip(assessed["training_end"], assessed["date"])):
            raise ValueError("Anomaly report contains in-sample or nonchronological scores")
        if "calibration_end" in assessed and any(pd.isna(end) or end >= day for end, day in zip(assessed["calibration_end"], assessed["date"])):
            raise ValueError("Anomaly report contains nonchronological calibration scores")
        scored_rows = len(assessed)
        if scored_rows:
            anomaly_rate = int(assessed["is_anomaly"].sum()) / scored_rows
            anomaly_points = 10 if anomaly_rate > 0.1 else 5 if anomaly_rate > 0 else 0
    unusual = RiskFactor("unusual_activity", anomaly_points, RISK_WEIGHTS["unusual_activity"], anomaly_rate,
                          "10 points if over 10% of scored transactions are unusual; 5 if any are unusual. Investigate records; this is not evidence of fraud.", scored_rows > 0)
    factors = (shortfall, cash_buffer, expense_ratio, spending_volatility, unusual)
    if not scored_rows:
        warnings.append("Unusual activity is unavailable; its zero contribution is not evidence of normal activity. The total is a provisional lower bound.")
    if days < 30 or len(history) < 30:
        warnings.append("Limited data: fewer than 30 observed calendar days or 30 transactions in the risk window.")
    if anomalies is not None and scored_rows < len(history):
        warnings.append("Only part of the historical window has anomaly scores; the observed rate excludes unscored rows.")
    if not days:
        return RiskResult(None, "Insufficient data", "insufficient", factors, tuple(warnings))
    limited = days < 30 or len(history) < 30 or not scored_rows
    score = sum(factor.points for factor in factors)
    level = "High" if score >= HIGH_SCORE else "Moderate" if score >= MODERATE_SCORE else "Low"
    return RiskResult(score, level, "limited" if limited else "adequate for heuristics", factors, tuple(warnings))
