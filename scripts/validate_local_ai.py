"""Explicit real Gemma checks on fictional data; never downloads a model."""

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import SAMPLE_DATA_PATH
from src.dashboard_service import build_dashboard, dashboard_anomalies
from src.data_processing import validate_csv
from src.financial_context import build_financial_context
from src.insight_workflow import generate_report
from src.llm_service import OllamaService, OllamaSettings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/phase6/local_gemma.json"))
    args = parser.parse_args()
    results = {"model": "gemma3:4b", "mocked": False, "cases": []}
    with OllamaService(OllamaSettings(model="gemma3:4b")) as service:
        status = service.check_availability()
        results.update(ready=status.ready, code=status.code)
    if status.ready:
        demo_import = validate_csv(SAMPLE_DATA_PATH)
        sparse_import = validate_csv("date,description,amount,category\n2026-01-01,Fictional receipt,100.25,Income\n")
        demo = build_dashboard(demo_import, "2500.00", anomalies=dashboard_anomalies(demo_import.data))
        sparse = build_dashboard(sparse_import, "0", anomalies=dashboard_anomalies(sparse_import.data))
        results["anomaly_engine"] = "Calibrated amount review"
        for name, bundle, timeout in (("full_evidence", demo, 90.0), ("insufficient_history", sparse, 90.0), ("short_timeout_probe", demo, 1.0)):
            with OllamaService(OllamaSettings(model="gemma3:4b", timeout_seconds=timeout)) as service:
                context = build_financial_context(bundle)
                start = perf_counter()
                report = generate_report(bundle, service)
                elapsed = perf_counter() - start
                results["cases"].append(dict(case=name, wall_seconds=elapsed, timeout_seconds=timeout,
                                             source=report.source, error_code=report.error_code,
                                             context_fingerprint=context.fingerprint(),
                                             data_sufficiency=context.data_sufficiency,
                                             validated_sections=list(type(report.insights).model_fields) if report.insights else [],
                                             # Only validated qualitative explanations, never raw rejected responses.
                                             validated_explanations=report.insights.model_dump() if report.insights else None,
                                             numeric_claim_policy="Model prose rejects numerical claims; amounts are rendered separately from trusted evidence"))
            print(f"{name}: source={report.source}, code={report.error_code}, wall={elapsed:.2f}s", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"ready": results["ready"], "code": results["code"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
