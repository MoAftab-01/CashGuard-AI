"""Offline chronological distribution diagnostics, never an automatic retrain trigger.

Financial amounts are discrete and temporally dependent: KS distance is reported,
but its IID continuous-sample p-value is deliberately withheld. Thresholds are
documented heuristic review policies, not calibrated statistical guarantees.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from scipy.spatial.distance import jensenshannon
from scipy.stats import ks_2samp

from src.analytics_utils import transaction_snapshot


class DriftConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    min_rows: int = Field(default=100, ge=30, strict=True)
    min_days: int = Field(default=30, ge=14, strict=True)
    min_scored: int = Field(default=50, ge=30, strict=True)
    min_residuals: int = Field(default=50, ge=30, strict=True)
    ks_threshold: float = Field(default=.2, gt=0, le=1, strict=True)
    js_threshold: float = Field(default=.1, gt=0, le=1, strict=True)
    ratio_delta: float = Field(default=.2, gt=0, strict=True)
    alert_delta: float = Field(default=.1, gt=0, le=1, strict=True)


@dataclass(frozen=True)
class DriftSignal:
    name: str
    sufficient: bool
    statistic: float | None
    threshold: float
    flagged: bool | None
    reference_value: float | None = None
    current_value: float | None = None
    explanation: str = ""


@dataclass(frozen=True)
class DriftReport:
    status: str
    reference_rows: int
    current_rows: int
    reference_start: date | None
    reference_end: date | None
    current_start: date | None
    current_end: date | None
    reference_fingerprint: str
    current_fingerprint: str
    signals: tuple[DriftSignal, ...]
    warnings: tuple[str, ...]


def _history(frame, flags):
    copy = frame.copy()
    if flags is not None:
        if len(flags) != len(copy) or isinstance(flags, pd.Series) and not flags.index.equals(copy.index):
            raise ValueError("Alert flags must align with the original transaction rows")
        if any(not pd.isna(value) and not isinstance(value, (bool, np.bool_)) for value in flags):
            raise ValueError("Alert flags must be boolean or unscored/null")
        copy["_monitor_flag"] = list(flags)
    return transaction_snapshot(copy, max(copy["date"]) if len(copy) else date.min)[0]


def _span(frame):
    return (max(frame["date"]) - min(frame["date"])).days + 1 if len(frame) else 0


def _fingerprint(frame):
    columns = ["date", "description", "category", "amount_cents"]
    return hashlib.sha256(frame[columns].to_csv(index=False, lineterminator="\n").encode()).hexdigest()


def _ratio(frame):
    income = sum(int(cents) for cents in frame.amount_cents if cents > 0)
    expense = -sum(int(cents) for cents in frame.amount_cents if cents < 0)
    return expense / income if income else None


def monitor_distributions(reference, current, *, reference_flags=None, current_flags=None, config=None):
    config = config or DriftConfig()
    reference, current = _history(reference, reference_flags), _history(current, current_flags)
    if len(reference) and len(current) and max(reference.date) >= min(current.date):
        raise ValueError("Reference must end strictly before the later monitoring window")
    sufficient = min(len(reference), len(current)) >= config.min_rows and min(_span(reference), _span(current)) >= config.min_days
    signals = []
    if sufficient:
        values = [np.log1p(frame.amount_cents.map(lambda cents: abs(int(cents))).to_numpy(dtype=float))
                  for frame in (reference, current)]
        distance = float(ks_2samp(*values, method="asymp").statistic)
        signals.append(DriftSignal("absolute_amount_distribution", True, distance, config.ks_threshold,
                                  distance >= config.ks_threshold, explanation="KS distance over log absolute amounts; IID p-value withheld."))
        categories = sorted(set(reference.category) | set(current.category))
        probabilities = [frame.category.value_counts().reindex(categories, fill_value=0).to_numpy(dtype=float)
                         for frame in (reference, current)]
        divergence = float(jensenshannon(*probabilities, base=2) ** 2)
        signals.append(DriftSignal("category_distribution", True, divergence, config.js_threshold,
                                  divergence >= config.js_threshold, explanation="Jensen-Shannon divergence in bits over the union of categories, including new categories."))
        old, new = _ratio(reference), _ratio(current)
        delta = abs(new - old) if old is not None and new is not None else None
        signals.append(DriftSignal("expense_to_income_ratio", delta is not None, delta, config.ratio_delta,
                                  delta >= config.ratio_delta if delta is not None else None, old, new,
                                  "Absolute ratio change; unavailable without observed income in both windows."))
    else:
        for name, threshold in (("absolute_amount_distribution", config.ks_threshold),
                                ("category_distribution", config.js_threshold), ("expense_to_income_ratio", config.ratio_delta)):
            signals.append(DriftSignal(name, False, None, threshold, None,
                                      explanation=f"Need at least {config.min_rows} transactions spanning {config.min_days} days in each window."))
    counts, rates = [], []
    for frame in (reference, current):
        flags = frame["_monitor_flag"].dropna() if "_monitor_flag" in frame else []
        counts.append(len(flags))
        rates.append(sum(bool(value) for value in flags) / len(flags) if len(flags) else None)
    alert_sufficient = sufficient and min(counts) >= config.min_scored
    delta = abs(rates[1] - rates[0]) if alert_sufficient else None
    signals.append(DriftSignal("alert_rate", alert_sufficient, delta, config.alert_delta,
                              delta >= config.alert_delta if alert_sufficient else None,
                              rates[0] if alert_sufficient else None, rates[1] if alert_sufficient else None,
                              "Unscored rows are excluded; matching review policy is required. Rate differences are not fraud probabilities."))
    status = "review_required" if any(item.flagged for item in signals) else "no_material_shift_observed" if sufficient else "insufficient_data"
    return DriftReport(status, len(reference), len(current),
                       min(reference.date) if len(reference) else None, max(reference.date) if len(reference) else None,
                       min(current.date) if len(current) else None, max(current.date) if len(current) else None,
                       _fingerprint(reference), _fingerprint(current), tuple(signals),
                       ("Drift is not proof of model failure and does not trigger retraining.",
                        "Fixed effect thresholds are review heuristics, not significance or false-positive guarantees.",
                        "Seasonality, payday timing, correlated transactions and window composition can change these diagnostics.",
                        "Missing alert flags remain unassessed. Compare identical engine/calibration policies."))


def compare_forecast_residuals(reference, current, *, observed_as_of, config=None):
    """Compare realized, matched-lead balance errors; do not score future outcomes."""
    config = config or DriftConfig()
    if type(observed_as_of) is not date:
        raise ValueError("observed_as_of must be a calendar date")
    arrays, leads = [], []
    for frame in (reference, current):
        required = {"cutoff", "date", "predicted_balance_cents", "actual_balance_cents"}
        if not required <= set(frame.columns):
            raise ValueError("Residuals require cutoff, date, predicted and actual balance cents")
        if any(type(value) is not date for column in ("cutoff", "date") for value in frame[column]):
            raise ValueError("Residual timestamps must be calendar dates")
        if any(not origin < day <= observed_as_of for origin, day in zip(frame.cutoff, frame.date)):
            raise ValueError("Residuals must be out-of-sample and already observed")
        if frame.duplicated(["cutoff", "date"]).any():
            raise ValueError("Residual origin/date pairs must be unique")
        for column in ("predicted_balance_cents", "actual_balance_cents"):
            if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer))
                   or abs(int(value)) >= 10**15 for value in frame[column]):
                raise ValueError("Residual monetary values must be finite integer cents")
        arrays.append(np.asarray([int(predicted) - int(actual) for predicted, actual in
                                 zip(frame.predicted_balance_cents, frame.actual_balance_cents)], dtype=float) / 100)
        leads.append(Counter((day - origin).days for origin, day in zip(frame.cutoff, frame.date)))
    if len(reference) and len(current) and max(reference.date) >= min(current.date):
        raise ValueError("Residual reference outcomes must precede current outcomes")
    if len(reference) and len(current) and any(leads[0][lead] * len(current) != leads[1][lead] * len(reference) for lead in set(leads[0]) | set(leads[1])):
        raise ValueError("Residual windows must use matching lead-day proportions")
    enough = min(len(reference), len(current)) >= config.min_residuals and min(reference.cutoff.nunique(), current.cutoff.nunique()) >= 2
    distance = float(ks_2samp(*arrays, method="asymp").statistic) if enough else None
    return {"signal": DriftSignal("forecast_residual_distribution", enough, distance, config.ks_threshold,
                                  distance >= config.ks_threshold if enough else None,
                                  explanation="Realized predicted-minus-actual balance errors; matched lead-day proportions. KS p-value withheld."),
            "reference_mae": float(np.abs(arrays[0]).mean()) if enough else None,
            "current_mae": float(np.abs(arrays[1]).mean()) if enough else None,
            "reference_bias": float(arrays[0].mean()) if enough else None,
            "current_bias": float(arrays[1].mean()) if enough else None,
            "warning": "At least two origins and sufficient realized outcomes are required. Overlapping origins are dependent; timestamps alone cannot prove upstream feature provenance."}
