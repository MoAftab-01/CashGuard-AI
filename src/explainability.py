"""Deterministic ledger and training comparisons, not causal model attribution."""

import numpy as np
import pandas as pd

from src.analytics_utils import positive_integer
from src.forecasting import _group_key


def threshold_breaches(forecast) -> pd.DataFrame:
    """Reconcile each breach to prior cash, that day's flows and the threshold."""
    frame = forecast.daily.copy()
    previous = [forecast.current_balance_cents, *frame["balance_cents"].tolist()[:-1]]
    frame["previous_balance_cents"] = previous
    frame["gap_to_threshold_cents"] = forecast.cash_threshold_cents - frame["balance_cents"]
    frame["status"] = ["Crosses below threshold" if balance >= forecast.cash_threshold_cents
                       else "Remains below threshold" for balance in previous]
    event_types = {}
    for event in forecast.events:
        event_types.setdefault(event.date, set()).add(event.kind)
    frame["event_types"] = frame["date"].map(lambda day: ", ".join(sorted(event_types.get(day, set()))) or "No projected events")
    return frame.loc[frame["below_threshold"]].reset_index(drop=True)


def anomaly_comparisons(history, scored_row, *, limit=3) -> pd.DataFrame:
    """Closest absolute amounts from the same reference population, training only.

    Never present later/same-day records as supporting training evidence. The
    median displayed by the detector uses the full reference population; these
    selected examples are contextual comparisons, not mathematical attribution.
    """
    positive_integer(limit, "limit", 20)
    end = scored_row["training_end"]
    if pd.isna(end):
        return history.iloc[:0].copy()
    if end >= scored_row["date"]:
        raise ValueError("Comparison training cutoff must precede the scored date")
    prior = history.loc[history["date"] <= end].copy()
    direction = np.sign(int(scored_row["amount_cents"]))
    same_direction = prior.loc[np.sign(prior["amount_cents"]) == direction]
    same_category = same_direction.loc[same_direction["category"] == scored_row["category"]]
    reference = same_category if len(same_category) >= 3 else same_direction if len(same_direction) else prior
    if scored_row.get("reference_scope") == "Recurring payment":
        key = _group_key(scored_row)
        reference = prior.loc[prior.apply(lambda row: _group_key(row) == key, axis=1)]
    distance = (reference["amount_cents"].abs() - abs(int(scored_row["amount_cents"]))).abs()
    return reference.loc[distance.sort_values(kind="stable").head(limit).index].copy()


def ranked_risk_factors(risk):
    return tuple(sorted(risk.factors, key=lambda factor: (factor.evaluated, factor.points), reverse=True))
