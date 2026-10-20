"""Bounded ASGI ingress and correlation; no global user cache or permissive CORS."""

import asyncio
import hmac
import json
import logging
import re
from time import perf_counter
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.responses import JSONResponse

from src.observability import request_id

logger = logging.getLogger(__name__)


class RequestBudget:
    """Single-process fixed-window limits with bounded memory; no user payloads."""
    def __init__(self, per_client, total, max_clients, *, clock=monotonic):
        self.per_client, self.total, self.max_clients, self.clock = per_client, total, max_clients, clock
        self.window, self.count, self.clients = clock(), 0, {}

    def accept(self, key):
        now = self.clock()
        if now - self.window >= 60:
            self.window, self.count, self.clients = now, 0, {}
        if (self.count >= self.total or self.clients.get(key, 0) >= self.per_client
                or key not in self.clients and len(self.clients) >= self.max_clients):
            return False
        self.count += 1
        self.clients[key] = self.clients.get(key, 0) + 1
        return True


def error_response(identity, code, message, status=422, issues=()):
    return JSONResponse({"request_id": identity,
                         "error": {"code": code, "message": message, "issues": list(issues)}},
                        status_code=status)


class LocalPolicy:
    def __init__(self, app, settings, metrics=None):
        self.app, self.settings = app, settings
        self.metrics = metrics
        self.capacity = asyncio.Semaphore(settings.max_concurrent_analytics)
        self.budget = RequestBudget(settings.rate_limit_per_minute,
                                    settings.global_rate_limit_per_minute, settings.max_rate_clients)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"x-request-id", b"").decode("latin1")
        pattern = r"[a-f0-9]{32}" if self.settings.public_demo else r"[A-Za-z0-9_-]{1,64}"
        identity = supplied if re.fullmatch(pattern, supplied) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = identity
        token = request_id.set(identity)
        started, status, acquired = False, 500, False
        beginning = perf_counter()

        async def respond(message):
            nonlocal started, status
            if message["type"] == "http.response.start":
                started, status = True, message["status"]
                message["headers"] = [*message.get("headers", []),
                    (b"x-request-id", identity.encode("ascii")), (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff")]
                origin = headers.get(b"origin", b"").decode("latin1")
                if origin in self.settings.cors_origins:
                    message["headers"] += [(b"access-control-allow-origin", origin.encode("latin1")),
                                           (b"vary", b"Origin"),
                                           (b"access-control-expose-headers", b"X-Request-ID, Retry-After")]
                if status == 429:
                    message["headers"].append((b"retry-after", b"60"))
            await send(message)

        async def reject(code, message, http_status):
            await error_response(identity, code, message, http_status)(scope, receive, respond)

        try:
            try:
                host = urlsplit("http://" + headers.get(b"host", b"").decode("latin1")).hostname
                allowed = {value.strip("[]") for value in self.settings.allowed_hosts}
                if host not in allowed:
                    return await reject("invalid_host", "Use the configured local API host.", 400)
            except ValueError:
                return await reject("invalid_host", "Invalid Host header.", 400)
            origin = headers.get(b"origin")
            if origin:
                try:
                    from src.settings import loopback_url
                    if origin.decode("latin1") not in self.settings.cors_origins:
                        if self.settings.public_demo:
                            raise ValueError
                        loopback_url(origin.decode("latin1"))
                except ValueError:
                    return await reject("invalid_origin", "Cross-origin financial requests are not permitted.", 403)
            path = scope.get("path", "")
            if scope["method"] == "OPTIONS" and origin and origin.decode("latin1") in self.settings.cors_origins:
                from starlette.responses import Response
                return await Response(status_code=204, headers={
                    "access-control-allow-methods": "GET, POST, OPTIONS",
                    "access-control-allow-headers": "Authorization, Content-Type, X-Request-ID, X-CashGuard-Session",
                    "access-control-max-age": "300"})(scope, receive, respond)
            public_health = path in {"/health", "/ready"}
            operational = path in {"/metrics", "/docs", "/openapi.json"}
            credential = self.settings.ops_token if operational else self.settings.api_token
            protected = not public_health and (self.settings.public_demo or credential is not None)
            expected = ("Bearer " + credential.get_secret_value()).encode() if credential is not None else b""
            authorized = bool(expected) and hmac.compare_digest(headers.get(b"authorization", b""), expected)
            if sum(key.lower() == b"authorization" for key, _ in scope.get("headers", [])) > 1:
                authorized = False
            supplied_session = headers.get(b"x-cashguard-session", b"").decode("latin1")
            trusted_session = authorized and re.fullmatch(r"[a-f0-9]{32}", supplied_session)
            scope["state"]["session_id"] = supplied_session if trusted_session else "local"
            if self.settings.rate_limit_per_minute and not public_health:
                client = (scope.get("client") or ("unknown", 0))[0]
                key = "session:" + supplied_session if trusted_session else "ip:" + str(client)
                if not self.budget.accept(key):
                    return await reject("rate_limited", "Request budget reached. Wait before retrying.", 429)
            if protected and not authorized:
                return await reject("unauthorized", "A valid service credential is required.", 401)
            if scope["method"] == "POST":
                if headers.get(b"content-type", b"").split(b";")[0].strip().lower() != b"application/json":
                    return await reject("content_type", "Send application/json.", 415)
                if headers.get(b"content-encoding", b"identity") != b"identity":
                    return await reject("content_encoding", "Compressed request bodies are not accepted.", 415)
                try:
                    length = int(headers.get(b"content-length", b"0"))
                except ValueError:
                    return await reject("content_length", "Invalid Content-Length.", 400)
                if length < 0 or length > self.settings.max_request_bytes:
                    return await reject("request_too_large", "Request exceeds the configured byte limit.", 413)
                if self.capacity.locked():
                    return await reject("busy", "Analytics capacity is busy. Retry later.", 503)
                await self.capacity.acquire()
                acquired = True
                if self.metrics is not None and self.metrics.enabled:
                    self.metrics.active.inc()
                body = bytearray()
                deadline = asyncio.get_running_loop().time() + self.settings.body_timeout_seconds
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    try:
                        message = await asyncio.wait_for(receive(), timeout=max(remaining, 0))
                    except TimeoutError:
                        return await reject("request_timeout", "Request body timed out.", 408)
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > self.settings.max_request_bytes:
                        return await reject("request_too_large", "Request exceeds the configured byte limit.", 413)
                    if not message.get("more_body", False):
                        break
                if self.settings.public_demo:
                    from src.demo_policy import accepts_public_payload
                    try:
                        payload = json.loads(body)
                    except (ValueError, UnicodeError):
                        return await reject("invalid_request", "Send a valid JSON request.", 422)
                    if not accepts_public_payload(path, payload):
                        return await reject("synthetic_only", "This public demo accepts only its bundled synthetic history. Private uploads are disabled.", 403)
                delivered = False

                async def buffered_receive():
                    nonlocal delivered
                    if delivered:
                        return await receive()
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}

                await self.app(scope, buffered_receive, respond)
            else:
                await self.app(scope, receive, respond)
        except Exception:
            if not started:
                await reject("internal_error", "Request could not be completed.", 500)
            logger.error("", extra={"event_type": "request_failed", "code": "internal_error"})
        finally:
            if acquired:
                self.capacity.release()
                if self.metrics is not None and self.metrics.enabled:
                    self.metrics.active.dec()
            route = getattr(scope.get("route"), "path", "unmatched")
            if self.metrics is not None:
                self.metrics.observe_http(route, scope["method"], status, perf_counter() - beginning)
            logger.info("", extra={"event_type": "http_request", "method": scope["method"] if scope["method"] in {"GET", "POST", "HEAD", "OPTIONS"} else "OTHER",
                                  "route": route, "status": status,
                                  "duration_seconds": perf_counter() - beginning})
            request_id.reset(token)
