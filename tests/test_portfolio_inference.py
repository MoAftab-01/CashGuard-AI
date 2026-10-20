import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
import requests

from src.inference import (DeterministicProvider, HostedGemmaProvider, InferenceBudget,
                           ProviderSettings, create_provider)
from src.llm_service import LocalLLMError


class Transport(requests.Session):
    def __init__(self, body=None, *, status=200, error=None):
        super().__init__()
        self.body, self.status, self.error, self.calls = body, status, error, []
    def request(self, method, url, **options):
        self.calls.append((method, url, options))
        if self.error:
            raise self.error
        response=requests.Response()
        response.status_code=self.status
        response._content=json.dumps(self.body).encode()
        response._content_consumed=True
        return response


def configuration(**updates):
    return ProviderSettings(**dict(provider="huggingface",hosted_enabled=True,
                                   hosted_api_key="test-key",**updates))


def envelope(payload):
    return {"model":"google/gemma-3-4b-it", "choices":[{
        "finish_reason":"stop","message":{"role":"assistant","content":json.dumps(payload)}}]}


def test_public_defaults_to_deterministic_and_never_initializes_a_model(monkeypatch, financial_context):
    monkeypatch.delenv("CASHGUARD_INFERENCE_PROVIDER",raising=False)
    config=ProviderSettings.from_environment(public_demo=True)
    assert config.provider=="deterministic"
    provider=create_provider(config,InferenceBudget(config),"visitor")
    assert isinstance(provider,DeterministicProvider)
    assert not provider.check_availability().ready
    with pytest.raises(LocalLLMError,match="disabled"):
        provider.generate(financial_context)


def test_hosted_requires_explicit_enable_before_network_or_quota(financial_context):
    config=ProviderSettings(provider="huggingface")
    session=Transport()
    budget=InferenceBudget(config)
    provider=HostedGemmaProvider(config,budget,"visitor",session=session)
    with pytest.raises(LocalLLMError,match="disabled"):
        provider.generate(financial_context)
    assert not session.calls and budget.requests==0


def test_mocked_hosted_generation_is_grounded_private_bounded_and_not_claimed_available(financial_context,valid_ai_payload,caplog):
    config=configuration()
    session=Transport(envelope(valid_ai_payload))
    budget=InferenceBudget(config)
    provider=HostedGemmaProvider(config,budget,"a",session=session)
    assert provider.check_availability().code=="hosted_unverified"
    output=provider.generate(financial_context)
    assert output.financial_health.explanation==valid_ai_payload["financial_health"]["explanation"]
    method,url,options=session.calls[0]
    sent=json.loads(options["data"])
    assert method=="POST" and url==HostedGemmaProvider.ENDPOINT
    assert not options["allow_redirects"] and not session.trust_env and not session.proxies
    assert sent["max_tokens"]==1024 and sent["response_format"]["type"]=="json_schema"
    assert b'transaction_id' not in options["data"] and b'merchant' not in json.dumps(sent["messages"][-1]).encode()
    assert budget.requests==1 and budget.cost>0
    assert "test-key" not in caplog.text


@pytest.mark.parametrize("status",[302,401,429,500])
def test_hosted_http_failures_never_echo_provider_response(status,financial_context):
    config=configuration()
    session=Transport({"error":"PRIVATE_PROVIDER_CANARY"},status=status)
    provider=HostedGemmaProvider(config,InferenceBudget(config),"a",session=session)
    with pytest.raises(LocalLLMError) as error:
        provider.generate(financial_context)
    assert error.value.code=="http_error" and "CANARY" not in str(error.value)
    assert len(session.calls)==1


def test_ambiguous_timeout_consumes_reservation_and_is_not_automatically_retried(financial_context):
    config=configuration(requests_per_hour=1)
    session=Transport(error=requests.Timeout())
    provider=HostedGemmaProvider(config,InferenceBudget(config),"a",session=session)
    with pytest.raises(LocalLLMError) as error:
        provider.generate(financial_context)
    assert error.value.code=="timeout"
    with pytest.raises(LocalLLMError) as error:
        provider.generate(financial_context)
    assert error.value.code=="quota_exceeded" and len(session.calls)==1


def test_invalid_numerical_prose_is_rejected(financial_context,valid_ai_payload):
    valid_ai_payload["financial_health"]["explanation"]="Your cash is 999999 dollars."
    config=configuration()
    provider=HostedGemmaProvider(config,InferenceBudget(config),"a",session=Transport(envelope(valid_ai_payload)))
    with pytest.raises(LocalLLMError) as error:
        provider.generate(financial_context)
    assert error.value.code=="invalid_response" and "999999" not in str(error.value)


def test_input_and_response_size_limits_reject_without_unbounded_work(financial_context,valid_ai_payload):
    config=configuration(max_input_bytes=4096)
    session=Transport(envelope(valid_ai_payload))
    provider=HostedGemmaProvider(config,InferenceBudget(config),"a",session=session)
    with pytest.raises(LocalLLMError):
        provider.generate(financial_context)
    assert not session.calls
    config=configuration(max_response_bytes=4096)
    provider=HostedGemmaProvider(config,InferenceBudget(config),"a",session=Transport({"oversized":"x"*5000}))
    with pytest.raises(LocalLLMError) as error:
        provider.generate(financial_context)
    assert error.value.code=="invalid_response"


def test_budget_enforces_per_session_global_cost_and_atomic_reservation():
    config=configuration(requests_per_hour=1,global_requests_per_hour=2,max_cost_usd_per_day="0.01")
    budget=InferenceBudget(config)
    budget.reserve("a",Decimal("0.004"))
    budget.reserve("b",Decimal("0.004"))
    with pytest.raises(LocalLLMError):
        budget.reserve("c",Decimal("0.004"))
    assert budget.cost==Decimal("0.008")
    config=configuration(requests_per_hour=5,global_requests_per_hour=5)
    budget=InferenceBudget(config)
    def attempt(_):
        try:
            budget.reserve("same-visitor")
            return True
        except LocalLLMError:
            return False
    with ThreadPoolExecutor(max_workers=10) as executor:
        assert sum(executor.map(attempt,range(20)))==5
