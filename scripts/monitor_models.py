"""Explicit offline distribution review; no raw transaction rows enter reports."""

import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from src.anomaly_experiments import anomaly_partition
from src.dashboard_service import require_ready_import
from src.data_processing import validate_csv
from src.model_monitoring import monitor_distributions


def synthetic_reports():
    reference = anomaly_partition("train").data
    partition = anomaly_partition("calibration")
    # Ground-truth labels select background only, not model predictions. No final
    # holdout is opened to tune drift thresholds or detector configuration.
    current = partition.data.loc[~partition.labels.is_injected.to_numpy()].copy()
    shifted = current.copy()
    mask = shifted.amount_cents < 0
    shifted.loc[mask, "amount_cents"] *= 10
    shifted.loc[mask, "amount"] = shifted.loc[mask, "amount_cents"].map(lambda value: Decimal(int(value)) / 100)
    shifted.loc[mask, "category"] = "Synthetic shifted spending"
    return {"data_origin": "synthetic", "policy": "phase8-heuristic-v1",
            "background": asdict(monitor_distributions(reference, current)),
            "deliberate_shift": asdict(monitor_distributions(reference, shifted)),
            "residual_status": "Not assessed: this command has no realized forecast outcome ledger.",
            "alert_status": "Not assessed: no comparable scored-alert vectors supplied."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", help="Only bundled fictional chronological partitions")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/phase8/drift"))
    args = parser.parse_args()
    if args.synthetic and not args.reference and not args.current:
        report = synthetic_reports()
    elif not args.synthetic and args.reference and args.current:
        try:
            frames = []
            for path in (args.reference, args.current):
                imported = validate_csv(path)
                require_ready_import(imported)
                frames.append(imported.data)
            report = {"data_origin": "user_supplied_local", "policy": "phase8-heuristic-v1",
                      "comparison": asdict(monitor_distributions(*frames))}
        except (OSError, ValueError):
            parser.error("Use valid, duplicate-reviewed CSVs in strictly separated chronological windows.")
    else:
        parser.error("Choose --synthetic OR both --reference and --current CSV paths.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "monitoring.json").write_text(json.dumps(report, indent=2, default=str, allow_nan=False), encoding="utf-8")
    lines = ["# Offline model monitoring", "", "Origin: " + report["data_origin"], "",
             "Local aggregate report; no raw descriptions, account IDs or transaction rows.",
             "Distribution shifts request review; they do not prove model failure or trigger retraining.", "",
             "Defaults: 100 transactions spanning 30 days per window; 50 scored rows for alert rates.",
             "KS distance >= 0.20; category JS divergence >= 0.10 bits; ratio delta >= 0.20; alert-rate delta >= 0.10.", ""]
    for name, comparison in report.items():
        if not isinstance(comparison, dict) or "signals" not in comparison:
            continue
        lines += ["## " + name.replace("_", " ").title(), "", "Status: " + comparison["status"], "",
                  f"Rows: {comparison['reference_rows']} reference / {comparison['current_rows']} current.", "",
                  "| Signal | Sufficient | Effect | Threshold | Review flag |", "|---|---|---|---|---|"]
        for item in comparison["signals"]:
            lines.append(f"| {item['name']} | {item['sufficient']} | {item['statistic']} | {item['threshold']} | {item['flagged']} |")
        lines += ["", *comparison["warnings"], ""]
    lines += [report.get("residual_status", "Residuals not supplied."), report.get("alert_status", "Alert vectors not supplied."), "",
              "Reports contain aggregate financial evidence and fingerprints; keep user-supplied reports private."]
    (args.output_dir / "monitoring.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({name: value["status"] for name, value in report.items() if isinstance(value, dict) and "status" in value}))


if __name__ == "__main__":
    main()
