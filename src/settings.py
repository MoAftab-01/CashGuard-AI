"""Validated operational settings, independent of Streamlit and optional MLflow."""

import ipaddress
import os
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
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

    @model_validator(mode="after")
    def validate_policy(self):
        if self.api_host not in {"127.0.0.1", "::1", "0.0.0.0"}:
            raise ValueError("Bind only to loopback, or explicitly configure container binding")
        if self.api_host == "0.0.0.0" and not self.container_bind:
            raise ValueError("Wildcard binding requires CASHGUARD_CONTAINER_BIND=true")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported log level")
        loopback_url(self.api_url)
        if not self.allowed_hosts or any("*" in host or not host for host in self.allowed_hosts):
            raise ValueError("Explicit allowed hosts are required")
        return self

    @classmethod
    def from_environment(cls):
        values = {}
        for name in cls.model_fields:
            raw = os.getenv("CASHGUARD_" + name.upper())
            if raw is not None:
                values[name] = tuple(raw.split(",")) if name == "allowed_hosts" else raw
        return cls(**values)
