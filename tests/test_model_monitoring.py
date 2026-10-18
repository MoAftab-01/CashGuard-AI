from datetime import date, timedelta

import pandas as pd
import pytest

from src.model_monitoring import DriftConfig, compare_forecast_residuals, monitor_distributions


def history(start=date(2025, 1, 1), rows=120):
    return pd.DataFrame([dict(date=start + timedelta(days=i // 3), description="Fictional activity",
                             category="Income" if i % 3 == 0 else "Other",
                             amount_cents=10000 if i % 3 == 0 else -2000) for i in range(rows)],
                        columns=["date", "description", "category", "amount_cents"])


def signals(report):
    return {item.name: item for item in report.signals}


def test_identical_later_distribution_has_zero_effect_and_unassessed_alerts():
    report = monitor_distributions(history(), history(date(2025, 4, 1)))
    assert report.status == "no_material_shift_observed"
    items = signals(report)
    for key in ("absolute_amount_distribution", "category_distribution", "expense_to_income_ratio"):
        assert items[key].statistic == pytest.approx(0) and not items[key].flagged
    assert items["alert_rate"].statistic is None and items["alert_rate"].flagged is None
    assert len(report.reference_fingerprint) == 64
    assert report.reference_end < report.current_start


def test_large_synthetic_amount_category_ratio_and_alert_shifts_are_detected():
    current = history(date(2025, 4, 1))
    current["amount_cents"] *= 10
    current.loc[current.amount_cents < 0, "amount_cents"] *= 4
    current["category"] = "New synthetic category"
    report = monitor_distributions(history(), current, reference_flags=[False] * 120,
                                   current_flags=[True] * 60 + [None] * 60)
    assert report.status == "review_required"
    assert all(item.flagged for item in report.signals)
    assert signals(report)["alert_rate"].current_value == 1
    assert signals(report)["category_distribution"].statistic == pytest.approx(1)


@pytest.mark.parametrize("rows", [0, 15, 99])
def test_tiny_or_empty_windows_do_not_emit_numeric_drift(rows):
    report = monitor_distributions(history(rows=rows), history(date(2025, 4, 1), rows=rows))
    assert report.status == "insufficient_data"
    assert all(not item.sufficient and item.statistic is None and item.flagged is None for item in report.signals)


def test_short_span_no_income_and_zero_amounts_are_handled():
    reference, current = history(), history(date(2025, 4, 1))
    reference["date"] = date(2025, 1, 1)
    assert monitor_distributions(reference, current).status == "insufficient_data"
    reference = history()
    reference["amount_cents"] = current["amount_cents"] = 0
    report = monitor_distributions(reference, current)
    assert signals(report)["expense_to_income_ratio"].statistic is None
    assert signals(report)["absolute_amount_distribution"].statistic == 0


def test_overlap_and_nonvalidated_data_are_rejected():
    with pytest.raises(ValueError, match="strictly before"):
        monitor_distributions(history(), history())
    malformed = history(date(2025, 4, 1))
    malformed["amount_cents"] = 1.25
    with pytest.raises(ValueError, match="integer cents"):
        monitor_distributions(history(), malformed)
    with pytest.raises(ValueError):
        DriftConfig(min_rows=2)


def test_unscored_flags_excluded_and_series_alignment_required():
    old, new = history(), history(date(2025, 4, 1))
    report = monitor_distributions(old, new, reference_flags=[False] * 49 + [None] * 71,
                                   current_flags=[True] * 120)
    assert not signals(report)["alert_rate"].sufficient
    with pytest.raises(ValueError, match="align"):
        monitor_distributions(old, new, current_flags=pd.Series([True] * 120, index=range(1, 121)))
    with pytest.raises(ValueError, match="boolean"):
        monitor_distributions(old, new, current_flags=[1] * 120)
    with pytest.raises(ValueError, match="align"):
        monitor_distributions(old, new, current_flags=[False])
    # Sorting transaction dates must retain their original alert associations.
    flags = pd.Series([True] * 60 + [False] * 60, index=new.index)
    shuffled = new.iloc[::-1]
    result = monitor_distributions(old, shuffled, reference_flags=[False] * 120,
                                   current_flags=flags.loc[shuffled.index])
    assert signals(result)["alert_rate"].current_value == .5


def residuals(start, error=0):
    return pd.DataFrame([dict(cutoff=start + timedelta(days=40 * origin),
                             date=start + timedelta(days=40 * origin + lead),
                             predicted_balance_cents=10000 + error, actual_balance_cents=10000)
                         for origin in range(2) for lead in range(1, 31)])


def test_realized_residual_drift_requires_matching_leads_and_observed_outcomes():
    result = compare_forecast_residuals(residuals(date(2025, 1, 1)), residuals(date(2025, 5, 1), 5000),
                                        observed_as_of=date(2025, 12, 31))
    assert result["signal"].flagged and result["signal"].statistic == 1
    assert result["reference_mae"] == 0 and result["current_mae"] == result["current_bias"] == 50
    few = residuals(date(2025, 5, 1)).head(30)
    result = compare_forecast_residuals(residuals(date(2025, 1, 1)), few, observed_as_of=date(2025, 12, 31))
    assert not result["signal"].sufficient and result["current_mae"] is None


@pytest.mark.parametrize("malformation", ["future", "in_sample", "duplicate", "lead_mix", "bool", "nan", "huge", "overlap"])
def test_residual_leakage_and_malformed_inputs_are_rejected(malformation):
    old, new = residuals(date(2025, 1, 1)), residuals(date(2025, 5, 1))
    if malformation == "future":
        new.loc[0, "date"] = date(2027, 1, 1)
    elif malformation == "in_sample":
        new.loc[0, "date"] = new.loc[0, "cutoff"]
    elif malformation == "duplicate":
        new = pd.concat([new, new.iloc[:1]], ignore_index=True)
    elif malformation == "lead_mix":
        new.loc[0, "date"] += timedelta(days=30)
    elif malformation == "overlap":
        new = old.copy()
    else:
        new["actual_balance_cents"] = {"bool": True, "nan": float("nan"), "huge": 10**99}[malformation]
    with pytest.raises(ValueError):
        compare_forecast_residuals(old, new, observed_as_of=date(2025, 12, 31))
