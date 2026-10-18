import asyncio
import json

from fastapi.testclient import TestClient

from api.main import create_app
from api.policy import LocalPolicy
from src.settings import Settings


def test_chunked_body_limit_is_enforced_without_content_length():
    async def scenario():
        calls = []
        async def application(*args):
            raise AssertionError("An oversized body reached the analytics application")
        messages = iter([{"type": "http.request", "body": b"x" * 700, "more_body": True},
                         {"type": "http.request", "body": b"x" * 700, "more_body": False}])
        async def receive():
            return next(messages)
        async def send(message):
            calls.append(message)
        app = LocalPolicy(application, Settings(allowed_hosts=("testserver",), max_request_bytes=1024))
        await app({"type": "http", "method": "POST", "path": "/api/v1/forecast", "headers": [
            (b"host", b"testserver"), (b"content-type", b"application/json")]}, receive, send)
        assert calls[0]["status"] == 413
    asyncio.run(scenario())


def test_body_timeout_and_capacity_reject_without_blocking_health():
    async def scenario():
        calls = []
        async def application(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        async def receive():
            await asyncio.sleep(.3)
            return {"type": "http.request", "body": b"{}", "more_body": False}
        async def send(message):
            calls.append(message)
        app = LocalPolicy(application, Settings(allowed_hosts=("testserver",),
                          body_timeout_seconds=.1, max_concurrent_analytics=1))
        scope = {"type": "http", "method": "POST", "path": "/api/v1/forecast", "headers": [
            (b"host", b"testserver"), (b"content-type", b"application/json")]}
        first = asyncio.create_task(app(dict(scope), receive, send))
        await asyncio.sleep(.02)
        await app(dict(scope), receive, send)
        await app({**scope, "method": "GET", "path": "/health"}, receive, send)
        await first
        statuses = [item["status"] for item in calls if item["type"] == "http.response.start"]
        assert statuses == [503, 200, 408]
        assert not app.capacity.locked()
    asyncio.run(scenario())


def test_unknown_keys_and_nonfinite_json_numbers_are_not_echoed():
    payload = {"transactions": [{"date": "2026-01-01", "description": "Sensitive description", "amount": "1.00", "category": "Other"}],
               "opening_balance": "0", "PRIVATE-ACCOUNT-1234": "PRIVATE-VALUE"}
    with TestClient(create_app(Settings(allowed_hosts=("testserver",)))) as client:
        response = client.post("/api/v1/forecast", json=payload)
        assert response.status_code == 422
        assert "PRIVATE" not in response.text and "Sensitive description" not in response.text
        payload.pop("PRIVATE-ACCOUNT-1234")
        for number in (float("nan"), float("inf"), float("-inf")):
            payload["opening_balance"] = number
            response = client.post("/api/v1/forecast", content=json.dumps(payload), headers={"content-type": "application/json"})
            assert response.status_code == 422 and "metrics" not in response.json()


def test_transaction_count_limit_prevents_excessive_ml_work():
    row = {"date": "2026-01-01", "description": "Fictional", "amount": "1.00", "category": "Other"}
    with TestClient(create_app(Settings(allowed_hosts=("testserver",)))) as client:
        response = client.post("/api/v1/forecast", json={"transactions": [row] * 2001, "opening_balance": "0"})
        assert response.status_code == 422
