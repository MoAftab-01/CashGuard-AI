"""Bounded, loopback-only Ollama HTTP integration with validated local models."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import DEFAULT_OLLAMA_MODEL, DEFAULT_OLLAMA_URL
from src.financial_context import FinancialContext
from src.insight_prompts import (OutputValidationError, StructuredInsights, build_messages,
                                 response_schema, validate_insights)

logger = logging.getLogger(__name__)
MAX_HTTP_BYTES = 1024 * 1024
MESSAGES = {
    "disabled": "Model inference is disabled. Calculated financial summaries remain available.",
    "quota_exceeded": "The model request or cost budget is exhausted. Calculated summaries remain available; try later.",
    "connection_error": "Cannot connect to local Ollama. Install or start Ollama, then check the connection again.",
    "timeout": "Local Ollama timed out. The model may still be loading; try again or increase the inference timeout.",
    "model_missing": "Ollama is running, but the selected model is not installed. Follow the model setup instructions below.",
    "remote_model": "This model routes to a cloud service. Select a locally installed model; financial data was not sent for inference.",
    "unsupported_model": "The selected model does not expose local text-generation weights. Choose a local chat/completion model.",
    "invalid_response": "The local model response failed structure, evidence or safety validation. Calculated summaries remain available.",
    "http_error": "Local Ollama could not complete the request. Check that the service and model have enough resources.",
    "invalid_metadata": "Local Ollama returned invalid model metadata. Update or restart Ollama and check again.",
    "configuration": "Use a valid locally installed model name and an HTTP loopback Ollama endpoint.",
}


class LocalLLMError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(MESSAGES[code])


class OllamaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    base_url: str = DEFAULT_OLLAMA_URL
    model: str = DEFAULT_OLLAMA_MODEL
    connect_timeout_seconds: float = Field(default=2.0, ge=0.1, le=10, strict=True)
    timeout_seconds: float = Field(default=90.0, ge=1, le=180, strict=True)
    max_attempts: int = Field(default=2, ge=1, le=2, strict=True)

    @field_validator("model")
    @classmethod
    def local_model_name(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value) or value.lower().endswith("cloud"):
            raise ValueError("Select a local model name")
        return value if ":" in value.rsplit("/", 1)[-1] else value + ":latest"

    @field_validator("base_url")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            host = parsed.hostname
            if host == "localhost":
                host = "127.0.0.1"  # No DNS resolution or proxy routing.
            address = ipaddress.ip_address(host)
            if (parsed.scheme != "http" or not address.is_loopback or parsed.username or parsed.password
                    or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
                raise ValueError
            port = parsed.port or 11434
            if not 1 <= port <= 65535:
                raise ValueError
            return f"http://{'[' + host + ']' if address.version == 6 else host}:{port}"
        except (ValueError, TypeError):
            raise ValueError("Only an HTTP loopback endpoint is permitted") from None

    @classmethod
    def from_environment(cls, *, model: str | None = None, timeout_seconds: float | None = None) -> OllamaSettings:
        return cls(base_url=os.getenv("CASHGUARD_OLLAMA_URL", DEFAULT_OLLAMA_URL),
                   model=model if model is not None else os.getenv("CASHGUARD_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
                   timeout_seconds=timeout_seconds if timeout_seconds is not None else float(os.getenv("CASHGUARD_OLLAMA_TIMEOUT", "90")))


@dataclass(frozen=True)
class OllamaStatus:
    ready: bool
    code: str
    message: str
    model: str


def _cloud_metadata(value: object) -> bool:
    if isinstance(value, dict):
        return any((key in {"remote_host", "remote_model"} and bool(item)) or _cloud_metadata(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_cloud_metadata(item) for item in value)
    return False


class OllamaService:
    def __init__(self, settings: OllamaSettings | None = None, *, session: requests.Session | None = None):
        self.settings = settings or OllamaSettings.from_environment()
        self.session = session if session is not None else requests.Session()
        self.session.trust_env = False
        self.session.proxies.clear()

    def __enter__(self) -> OllamaService:
        return self

    def __exit__(self, *args: object) -> None:
        self.session.close()

    def _request(self, method: str, path: str, payload: dict | None = None, *, inference: bool = False) -> dict:
        # No pull/delete/tool endpoints, redirects, external URLs or environment proxies.
        if (method, path) not in {("GET", "/api/tags"), ("POST", "/api/show"), ("POST", "/api/chat")}:
            raise LocalLLMError("configuration")
        response = None
        try:
            response = self.session.request(method, self.settings.base_url + path, json=payload,
                                             timeout=(self.settings.connect_timeout_seconds,
                                                      self.settings.timeout_seconds if inference else 5),
                                             allow_redirects=False, stream=True)
            if response.status_code == 404 and path == "/api/show":
                raise LocalLLMError("model_missing")
            if not 200 <= response.status_code < 300:
                raise LocalLLMError("http_error")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                content.extend(chunk)
                if len(content) > MAX_HTTP_BYTES:
                    raise LocalLLMError("invalid_response" if inference else "invalid_metadata")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError
            if result.get("error"):
                raise LocalLLMError("http_error")
            return result
        except requests.Timeout:
            raise LocalLLMError("timeout") from None
        except requests.RequestException:
            raise LocalLLMError("connection_error") from None
        except (ValueError, UnicodeError):
            raise LocalLLMError("invalid_response" if inference else "invalid_metadata") from None
        finally:
            if response is not None:
                response.close()

    def _verify_model(self) -> None:
        models = self._request("GET", "/api/tags").get("models")
        if not isinstance(models, list) or any(not isinstance(item, dict) for item in models):
            raise LocalLLMError("invalid_metadata")
        selected = next((item for item in models if item.get("name") == self.settings.model or item.get("model") == self.settings.model), None)
        if selected is None:
            raise LocalLLMError("model_missing")
        if _cloud_metadata(selected):
            raise LocalLLMError("remote_model")
        info = self._request("POST", "/api/show", {"model": self.settings.model})
        if _cloud_metadata(info):
            raise LocalLLMError("remote_model")
        capabilities = info.get("capabilities")
        if not info.get("model_info") or (capabilities is not None and "completion" not in capabilities):
            raise LocalLLMError("unsupported_model")

    def check_availability(self) -> OllamaStatus:
        try:
            self._verify_model()
            return OllamaStatus(True, "ready", "Local Ollama is connected and the selected model is available.", self.settings.model)
        except LocalLLMError as exc:
            return OllamaStatus(False, exc.code, str(exc), self.settings.model)

    def generate(self, context: FinancialContext) -> StructuredInsights:
        # Revalidate even model_copy/model_construct instances at the network boundary.
        try:
            context = FinancialContext.model_validate(context.model_dump())
        except (ValueError, TypeError, AttributeError):
            raise LocalLLMError("invalid_response") from None
        self._verify_model()  # Always recheck immediately before sending any financial context.
        for attempt in range(self.settings.max_attempts):
            payload = {"model": self.settings.model, "messages": build_messages(context, retry=attempt > 0),
                       "format": response_schema(context), "stream": False, "keep_alive": 0,
                       "options": {"temperature": 0.1, "seed": 42, "num_predict": 2048, "num_ctx": 8192}}
            response = self._request("POST", "/api/chat", payload, inference=True)
            message = response.get("message")
            try:
                if (response.get("done") is not True or response.get("done_reason") not in (None, "stop")
                        or not isinstance(message, dict) or message.get("role") != "assistant"
                        or message.get("tool_calls") or response.get("model") != self.settings.model):
                    raise OutputValidationError("invalid_chat_envelope")
                return validate_insights(message.get("content"), context)
            except OutputValidationError as exc:
                logger.warning("local_insights_rejected attempt=%d reason=%s", attempt + 1, str(exc))
        raise LocalLLMError("invalid_response")
