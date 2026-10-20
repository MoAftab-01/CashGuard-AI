"""Explicit inference providers and process-scoped budgets; no paid call by default.

Hugging Face compatibility/prices are documented separately. This optional HTTP
adapter uses the existing requests dependency and never downloads weights.
"""

import json
import os
from decimal import Decimal
from threading import Lock
from time import monotonic
from typing import Literal, Protocol

import requests
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.financial_context import FinancialContext
from src.insight_prompts import StructuredInsights, build_messages, response_schema, validate_insights, OutputValidationError
from src.llm_service import LocalLLMError, OllamaService, OllamaSettings, OllamaStatus


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, hide_input_in_errors=True)
    provider: Literal["ollama", "huggingface", "deterministic"] = "ollama"
    hosted_enabled: bool = False
    hosted_api_key: SecretStr | None = None
    hosted_model: Literal["google/gemma-3-4b-it:deepinfra"] = "google/gemma-3-4b-it:deepinfra"
    timeout_seconds: float = Field(default=30, ge=1, le=90)
    max_output_tokens: int = Field(default=1024, ge=128, le=2048)
    max_input_bytes: int = Field(default=32768, ge=4096, le=65536)
    max_response_bytes: int = Field(default=65536, ge=4096, le=131072)
    requests_per_hour: int = Field(default=10, ge=1, le=100)
    global_requests_per_hour: int = Field(default=100, ge=1, le=1000)
    max_cost_usd_per_day: Decimal = Field(default=Decimal("1.00"), gt=0, le=100)
    input_usd_per_million: Decimal = Field(default=Decimal("0.05"), ge=0, le=100)
    output_usd_per_million: Decimal = Field(default=Decimal("0.10"), ge=0, le=100)

    @property
    def model(self):
        return self.hosted_model if self.provider == "huggingface" else "deterministic"

    @classmethod
    def from_environment(cls, *, public_demo=False):
        values = {name: os.environ["CASHGUARD_INFERENCE_" + name.upper()]
                  for name in cls.model_fields if "CASHGUARD_INFERENCE_" + name.upper() in os.environ}
        values.setdefault("provider", "deterministic" if public_demo else "ollama")
        return cls(**values)


class InferenceProvider(Protocol):
    settings: object
    def check_availability(self) -> OllamaStatus: ...
    def generate(self, context: FinancialContext) -> StructuredInsights: ...


class InferenceBudget:
    """Atomic conservative reservations; no financial payload or model output storage.

    Limits reset on process restart. Production account-level billing limits are
    still required. Failed/ambiguous requests are not refunded.
    """
    def __init__(self, settings, *, clock=monotonic):
        self.settings, self.clock, self.lock = settings, clock, Lock()
        self.hour, self.day = clock(), clock()
        self.requests, self.clients, self.cost = 0, {}, Decimal(0)

    def reserve(self, session_id, cost=Decimal(0)):
        with self.lock:
            now = self.clock()
            if now - self.hour >= 3600:
                self.hour, self.requests, self.clients = now, 0, {}
            if now - self.day >= 86400:
                self.day, self.cost = now, Decimal(0)
            if (self.requests >= self.settings.global_requests_per_hour
                    or self.clients.get(session_id, 0) >= self.settings.requests_per_hour
                    or session_id not in self.clients and len(self.clients) >= 512
                    or self.cost + cost > self.settings.max_cost_usd_per_day):
                raise LocalLLMError("quota_exceeded")
            self.requests += 1
            self.clients[session_id] = self.clients.get(session_id, 0) + 1
            self.cost += cost


class DeterministicProvider:
    def __init__(self, settings=None):
        self.settings = settings or ProviderSettings(provider="deterministic")
    def check_availability(self):
        return OllamaStatus(False, "disabled", "Deterministic mode: no model is called. Calculated summaries remain available.", self.settings.model)
    def generate(self, context):
        raise LocalLLMError("disabled")
    def close(self):
        pass


class HostedGemmaProvider:
    ENDPOINT = "https://router.huggingface.co/v1/chat/completions"

    def __init__(self, settings, budget, session_id, *, session=None):
        self.settings, self.budget, self.session_id = settings, budget, session_id
        self.session = session if session is not None else requests.Session()
        self.session.trust_env = False
        self.session.proxies.clear()

    def close(self):
        self.session.close()

    def check_availability(self):
        if not self.settings.hosted_enabled or not (self.settings.hosted_api_key and self.settings.hosted_api_key.get_secret_value().strip()):
            return OllamaStatus(False, "disabled", "Hosted inference is disabled. It requires explicit approval, credentials and budgets.", self.settings.model)
        return OllamaStatus(False, "hosted_unverified", "Hosted Gemma is configured. Remote availability has not been tested; generation sends minimized aggregates to Hugging Face and DeepInfra.", self.settings.model)

    def generate(self, context):
        if not self.settings.hosted_enabled or not (self.settings.hosted_api_key and self.settings.hosted_api_key.get_secret_value().strip()):
            raise LocalLLMError("disabled")
        try:
            context = FinancialContext.model_validate(context.model_dump())
            payload = {"model": self.settings.model, "messages": build_messages(context),
                       "response_format": {"type": "json_schema", "json_schema": {
                           "name": "cashguard_insights", "schema": response_schema(context), "strict": True}},
                       "max_tokens": self.settings.max_output_tokens, "temperature": .1, "stream": False}
            encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
        except (ValueError, TypeError, AttributeError):
            raise LocalLLMError("invalid_response") from None
        if len(encoded) > self.settings.max_input_bytes:
            raise LocalLLMError("invalid_response")
        reservation = ((len(encoded) + 1024) * self.settings.input_usd_per_million
                       + self.settings.max_output_tokens * self.settings.output_usd_per_million) / Decimal(1000000)
        self.budget.reserve(self.session_id, reservation)
        response = None
        try:
            response = self.session.request("POST", self.ENDPOINT, data=encoded,
                headers={"authorization": "Bearer " + self.settings.hosted_api_key.get_secret_value(),
                         "content-type": "application/json", "accept": "application/json"},
                timeout=(min(3, self.settings.timeout_seconds), self.settings.timeout_seconds),
                stream=True, allow_redirects=False)
            if response.status_code != 200:
                raise LocalLLMError("http_error")
            deadline = monotonic() + self.settings.timeout_seconds
            content = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if monotonic() > deadline:
                    raise LocalLLMError("timeout")
                content.extend(chunk)
                if len(content) > self.settings.max_response_bytes:
                    raise LocalLLMError("invalid_response")
            result = json.loads(content)
            choices = result.get("choices")
            if (result.get("model") not in {self.settings.model, self.settings.model.split(":")[0]}
                    or not isinstance(choices, list) or len(choices) != 1 or choices[0].get("finish_reason") != "stop"):
                raise LocalLLMError("invalid_response")
            message = choices[0].get("message", {})
            if message.get("role") != "assistant" or message.get("tool_calls") or message.get("function_call"):
                raise LocalLLMError("invalid_response")
            return validate_insights(message.get("content"), context)
        except requests.Timeout:
            raise LocalLLMError("timeout") from None
        except requests.RequestException:
            raise LocalLLMError("connection_error") from None
        except (ValueError, TypeError, AttributeError, OutputValidationError):
            raise LocalLLMError("invalid_response") from None
        finally:
            if response is not None:
                response.close()


class BudgetedLocalProvider:
    def __init__(self, service, budget, session_id):
        self.service, self.settings, self.budget, self.session_id = service, service.settings, budget, session_id
    def generate(self, context):
        self.budget.reserve(self.session_id)
        return self.service.generate(context)
    def check_availability(self):
        return self.service.check_availability()
    def close(self):
        self.service.session.close()


def create_provider(settings, budget, session_id, *, model=None, timeout_seconds=None):
    if settings.provider == "deterministic":
        return DeterministicProvider(settings)
    if settings.provider == "huggingface":
        if timeout_seconds is not None:
            settings = settings.model_copy(update={"timeout_seconds": min(settings.timeout_seconds, timeout_seconds)})
        return HostedGemmaProvider(settings, budget, session_id)
    local = OllamaSettings.from_environment(model=model, timeout_seconds=float(timeout_seconds or settings.timeout_seconds))
    local = local.model_copy(update={"max_attempts": 1})
    return BudgetedLocalProvider(OllamaService(local), budget, session_id)
