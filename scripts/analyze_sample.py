"""Run Phase 2 core analytics locally without advancing the Streamlit interface."""

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import SAMPLE_DATA_PATH
from src.anomaly_detection import detect_anomalies
from src.data_processing import validate_csv
from src.forecasting import forecast_cash_flow, rolling_backtest
from src.risk_engine import assess_risk
from src.scenario_simulator import ScenarioConfig, simulate_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opening-balance", required=True, help="Balance before the earliest imported sample transaction")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    imported = validate_csv(SAMPLE_DATA_PATH)
    if imported.has_errors:
        parser.error("Sample data is missing or invalid; run scripts/generate_sample_data.py")
    try:
        baseline = forecast_cash_flow(imported.data, args.opening_balance, as_of=args.as_of, cash_threshold=500)
        anomalies = detect_anomalies(imported.data, as_of=baseline.as_of)
        risk = assess_risk(imported.data, baseline, anomalies=anomalies)
        scenario = simulate_scenario(baseline, ScenarioConfig(
            income_decrease_pct=20, expense_increase_pct=10, emergency_expense=500,
            emergency_date=baseline.as_of + timedelta(days=1)))
        backtest = rolling_backtest(imported.data, args.opening_balance, as_of=baseline.as_of)
    except ValueError as exc:
        parser.error(str(exc))
    report = {
        "as_of": baseline.as_of.isoformat(),
        "opening_balance": args.opening_balance,
        "estimated_current_balance": str(Decimal(baseline.current_balance_cents) / 100),
        "projected_closing_balance": str(Decimal(int(baseline.daily.iloc[-1]["balance_cents"])) / 100),
        "recurring_patterns": len(baseline.recurring_patterns),
        "threshold_breach_dates": [day.isoformat() for day in baseline.shortage_dates],
        "anomaly_scored_rows": anomalies.scored_count,
        "unusual_rows": anomalies.anomaly_count,
        "heuristic_risk": {"score": risk.score, "level": risk.level, "data_sufficiency": risk.data_sufficiency,
                           "contributions": {factor.name: factor.points for factor in risk.factors}},
        "scenario": {"income_decrease_pct": 20, "expense_increase_pct": 10, "emergency_expense": 500,
                     "closing_balance_change": str(Decimal(scenario.closing_balance_change_cents) / 100)},
        "rolling_backtest": {"folds": len(backtest.folds), "origin_day_pairs": len(backtest.predictions),
                             "currency_unit_errors": backtest.metrics},
        "warnings": {"forecast": baseline.warnings, "anomalies": anomalies.warnings,
                     "risk": risk.warnings, "backtest": backtest.warnings},
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
