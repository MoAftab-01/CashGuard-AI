"""Explicit local HTTP smoke tests using fictional transactions; no model inference."""

import argparse
import json
from pathlib import Path

import requests

from src.settings import loopback_url


def check(api_url, dashboard_url=None, tracking_url=None):
    session = requests.Session()
    session.trust_env = False
    api_url = loopback_url(api_url)
    result = {"api_url": api_url, "fictional_data_only": True, "checks": []}
    payload = dict(transactions=[
        dict(date="2026-01-01", description="Fictional receipt", amount="100.25", category="Income", transaction_id="QA-1"),
        dict(date="2026-01-02", description="Fictional expense", amount="-25.10", category="Other", transaction_id="QA-2")],
        opening_balance="10.00", horizon_days=7)
    for route in ("/health", "/ready", "/openapi.json", "/docs"):
        response = session.get(api_url + route, timeout=10, allow_redirects=False)
        assert response.status_code == 200, (route, response.status_code)
        result["checks"].append(route)

    def post(route, data):
        response = session.post(api_url + "/api/v1/" + route, json=data, timeout=30, allow_redirects=False)
        assert response.status_code == 200, (route, response.status_code, response.text[:200])
        assert response.headers.get("x-request-id") and response.headers.get("cache-control") == "no-store"
        result["checks"].append(route)
        return response.json()

    summary = post("analytics/summary", payload)
    from decimal import Decimal
    assert Decimal(summary["metrics"]["estimated_balance"]) == Decimal("85.15")
    post("transactions/validate", {"transactions": payload["transactions"]})
    forecast = post("forecast", payload)
    assert len(forecast["daily"]) == 7 and forecast["current_balance_cents"] == 8515
    anomaly = post("anomalies/detect", {"transactions": payload["transactions"]})
    assert anomaly["scored_count"] == 0 and anomaly["unscored_count"] == 2
    post("risk/analyze", payload)
    scenario = post("scenarios/simulate", {**payload, "scenario": {
        "emergency_expense": "10.00", "emergency_date": forecast["daily"][0]["date"]}})
    assert scenario["comparison"]["closing_change_cents"] == -1000
    # This smoke does not request inference; unavailable-model generation is covered
    # with injected services in pytest and explicit local Gemma checks separately.
    bad = session.post(api_url + "/api/v1/forecast", json={**payload, "opening_balance": True}, timeout=10)
    assert bad.status_code == 422
    result["checks"].append("invalid_number_rejected")
    result["estimated_balance"] = summary["metrics"]["estimated_balance"]
    if dashboard_url:
        dashboard_url = loopback_url(dashboard_url)
        assert session.get(dashboard_url + "/_stcore/health", timeout=10).status_code == 200
        result["checks"].append("dashboard_health")
    if tracking_url:
        tracking_url = loopback_url(tracking_url)
        assert session.get(tracking_url + "/health", timeout=10).status_code == 200
        result["checks"].append("mlflow_health")
    session.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dashboard-url")
    parser.add_argument("--tracking-url")
    parser.add_argument("--output", type=Path, default=Path("reports/phase8/services.json"))
    args = parser.parse_args()
    result = check(args.api_url, args.dashboard_url, args.tracking_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"PASS: {len(result['checks'])} local service checks; no model inference")


if __name__ == "__main__":
    main()
