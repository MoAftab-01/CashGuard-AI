"""Bounded ASGI ingress and correlation; no global user cache or permissive CORS."""

import asyncio
import logging
import re
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.responses import JSONResponse

from src.observability import request_id

logger = logging.getLogger(__name__)


def error_response(identity, code, message, status=422, issues=()):
    return JSONResponse({"request_id": identity,
                         "error": {"code": code, "message": message, "issues": list(issues)}},
                        status_code=status)


class LocalPolicy:
    def __init__(self, app, settings, metrics=None):
        self.app, self.settings = app, settings
        self.metrics = metrics
        self.capacity = asyncio.Semaphore(settings.max_concurrent_analytics)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"x-request-id", b"").decode("latin1")
        identity = supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else uuid4().hex
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
                    loopback_url(origin.decode("latin1"))
                except ValueError:
                    return await reject("invalid_origin", "Cross-origin financial requests are not permitted.", 403)
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
            route = getattr(scope.get("route"), "path", "unmatched")
            if self.metrics is not None:
                self.metrics.observe_http(route, scope["method"], status, perf_counter() - beginning)
            logger.info("", extra={"event_type": "http_request", "method": scope["method"] if scope["method"] in {"GET", "POST", "HEAD", "OPTIONS"} else "OTHER",
                                  "route": route, "status": status,
                                  "duration_seconds": perf_counter() - beginning})
            request_id.reset(token)
