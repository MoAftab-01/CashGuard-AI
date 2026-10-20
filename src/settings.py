"""Validated operational settings, independent of Streamlit and optional MLflow."""

import ipaddress
import os
import re
from urllib.parse import urlsplit
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


def loopback_url(value: str) -> str:
    """Do not resolve arbitrary DNS, honor proxies, follow credentials or accept paths."""
    parsed = urlsplit(value)
    host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
    try:
        address = ipaddress.ip_address(host)
        if (parsed.scheme != "http" or not address.is_loopback or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError
        port = parsed.port or 8000
        if not 1 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Use an HTTP loopback endpoint without credentials or a path") from None
    return f"http://{'[' + host + ']' if address.version == 6 else host}:{port}"


def configured_api_url(value, allowed_hosts=(), *, allow_private_http=False):
    try:
        return loopback_url(value)
    except ValueError:
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.hostname not in allowed_hosts or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.scheme not in ({"http", "https"} if allow_private_http else {"https"})):
            raise ValueError("Use an explicitly allowed HTTPS API endpoint or a configured private-network endpoint") from None
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("Invalid API port")
        return value.rstrip("/")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, hide_input_in_errors=True)
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1024, le=65535)
    container_bind: bool = False
    max_request_bytes: int = Field(default=1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    body_timeout_seconds: float = Field(default=10, ge=0.1, le=30)
    max_concurrent_analytics: int = Field(default=2, ge=1, le=8)
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "[::1]")
    metrics_enabled: bool = True
    log_level: str = "INFO"
    api_url: str = "http://127.0.0.1:8000"
    client_timeout_seconds: float = Field(default=30, ge=1, le=180)
    execution_mode: Literal["direct", "api"] = "direct"
    client_max_retries: int = Field(default=0, ge=0, le=2, strict=True)
    public_demo: bool = False
    deployment_profile: Literal["local", "staging", "public"] = "local"
    api_allowed_hosts: tuple[str, ...] = ()
    private_api_http: bool = False
    api_token: SecretStr | None = None
    ops_token: SecretStr | None = None
    cors_origins: tuple[str, ...] = ()
    rate_limit_per_minute: int = Field(default=0, ge=0, le=600)
    global_rate_limit_per_minute: int = Field(default=240, ge=1, le=2000)
    max_rate_clients: int = Field(default=512, ge=16, le=4096)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.api_host not in {"127.0.0.1", "::1", "0.0.0.0"}:
            raise ValueError("Bind only to loopback, or explicitly configure container binding")
        if self.api_host == "0.0.0.0" and not self.container_bind:
            raise ValueError("Wildcard binding requires CASHGUARD_CONTAINER_BIND=true")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported log level")
        configured_api_url(self.api_url, self.api_allowed_hosts, allow_private_http=self.private_api_http)
        if not self.allowed_hosts or any("*" in host or not host for host in self.allowed_hosts):
            raise ValueError("Explicit allowed hosts are required")
        if any(not host or "*" in host for host in self.api_allowed_hosts):
            raise ValueError("API destinations must be exact hostnames")
        for token in (self.api_token, self.ops_token):
            if token is not None and not re.fullmatch(r"[A-Za-z0-9._~+/-]{32,256}", token.get_secret_value()):
                raise ValueError("Configured API and operations tokens require 32–256 safe characters")
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                    or parsed.password or parsed.path or parsed.query or parsed.fragment or "*" in origin):
                raise ValueError("CORS requires exact origins without paths or credentials")
        if self.deployment_profile != "local" and not self.public_demo:
            raise ValueError("Hosted profiles require synthetic-only public demo mode")
        if self.public_demo:
            if self.execution_mode != "api" or self.api_token is None or self.rate_limit_per_minute < 1:
                raise ValueError("Public demo requires API mode, a strong API token and positive rate limits")
            if self.ops_token is not None and self.ops_token == self.api_token:
                raise ValueError("Use a separate operations credential")
        return self

    @classmethod
    def from_environment(cls):
        values = {}
        for name in cls.model_fields:
            raw = os.getenv("CASHGUARD_" + name.upper())
            if raw is not None:
                values[name] = (tuple(part.strip() for part in raw.split(",") if part.strip())
                                if name in {"allowed_hosts", "api_allowed_hosts", "cors_origins"} else
                                int(raw) if name == "client_max_retries" else raw)
        return cls(**values)
