"""Check local Ollama or explicitly generate insights on the fictional sample."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import SAMPLE_DATA_PATH
from src.dashboard_service import build_dashboard
from src.data_processing import validate_csv
from src.insight_workflow import generate_report
from src.llm_service import OllamaService, OllamaSettings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="Installed local model; defaults to gemma3:4b or the environment override")
    parser.add_argument("--generate", action="store_true", help="Explicitly request inference using the bundled fictional history")
    parser.add_argument("--opening-balance", default=None, help="Required with --generate; opening balance for synthetic history")
    args = parser.parse_args()
    if args.generate and args.opening_balance is None:
        parser.error("--opening-balance is required with --generate")
    try:
        settings = OllamaSettings.from_environment(model=args.model)
    except ValueError:
        parser.error("Invalid local Ollama configuration; check model name, loopback endpoint and timeout")
    with OllamaService(settings) as service:
        status = service.check_availability()
        if not status.ready or not args.generate:
            print(json.dumps({"ready": status.ready, "model": status.model, "code": status.code,
                              "message": status.message, "inference_requested": False}, indent=2))
            return 0 if status.ready else 1
        imported = validate_csv(SAMPLE_DATA_PATH)
        try:
            bundle = build_dashboard(imported, args.opening_balance)
        except ValueError:
            parser.error("Sample data or opening balance is invalid; correct it before requesting inference")
        report = generate_report(bundle, service)
    print(json.dumps({"model": settings.model, "source": report.source, "error_code": report.error_code,
                      "validated_sections": list(type(report.insights).model_fields) if report.insights else [],
                      "message": report.message}, indent=2))
    return 0 if report.source == "ai" else 1


if __name__ == "__main__":
    raise SystemExit(main())
