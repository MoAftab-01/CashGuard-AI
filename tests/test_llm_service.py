import json

import pytest
import requests

from src.llm_service import LocalLLMError, OllamaService, OllamaSettings


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.trust_env = True
        self.proxies = {"http": "http://external.invalid"}
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


def metadata(model="gemma3:4b"):
    return [FakeResponse({"models": [{"name": model, "size": 100}]}),
            FakeResponse({"model_info": {"general.architecture": "gemma3"}, "capabilities": ["completion"]})]


def chat(payload, **overrides):
    return FakeResponse({"model": "gemma3:4b", "done": True, "done_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps(payload)}, **overrides})


def test_installed_model_is_verified_before_generation(financial_context, valid_ai_payload):
    session = FakeSession([*metadata(), chat(valid_ai_payload)])
    with OllamaService(session=session) as service:
        result = service.generate(financial_context)
    assert result.financial_health.status == "supported"
    assert [call[1].rsplit("/", 1)[-1] for call in session.calls] == ["tags", "show", "chat"]
    assert session.trust_env is False and session.proxies == {} and session.closed
    body = session.calls[-1][2]["json"]
    assert body["model"] == "gemma3:4b" and body["stream"] is False
    assert body["format"]["additionalProperties"] is False
    assert body["options"]["temperature"] == 0.1
    assert body["keep_alive"] == 0
    assert session.calls[-1][2]["allow_redirects"] is False
    assert session.calls[-1][2]["timeout"] == (2.0, 90.0)


def test_missing_model_never_sends_context(financial_context):
    session = FakeSession([FakeResponse({"models": []})])
    service = OllamaService(session=session)
    status = service.check_availability()
    assert not status.ready and status.code == "model_missing"
    assert len(session.calls) == 1 and session.calls[0][2]["json"] is None
    session.responses.append(FakeResponse({"models": []}))
    with pytest.raises(LocalLLMError, match="not installed"):
        service.generate(financial_context)
    assert not any(call[1].endswith("chat") for call in session.calls)


@pytest.mark.parametrize("failure,code", [(requests.ConnectionError("SECRET_PRIVATE_BODY"), "connection_error"),
                                         (requests.Timeout("SECRET_PRIVATE_BODY"), "timeout")])
def test_connection_errors_and_timeouts_are_sanitized(failure, code):
    service = OllamaService(session=FakeSession([failure]))
    status = service.check_availability()
    assert status.code == code and "SECRET_PRIVATE_BODY" not in status.message


def test_inference_timeout_is_sanitized_and_not_retried(financial_context):
    session = FakeSession([*metadata(), requests.ReadTimeout("SENSITIVE PROMPT")])
    with pytest.raises(LocalLLMError) as error:
        OllamaService(session=session).generate(financial_context)
    assert error.value.code == "timeout" and "SENSITIVE" not in str(error.value)
    assert len(session.calls) == 3


def test_invalid_numeric_response_gets_a_single_regeneration_then_validates(financial_context, valid_ai_payload):
    invalid = json.loads(json.dumps(valid_ai_payload))
    invalid["financial_health"]["explanation"] = "The balance is 123456 and guaranteed."
    session = FakeSession([*metadata(), chat(invalid), chat(valid_ai_payload)])
    result = OllamaService(session=session).generate(financial_context)
    assert result.financial_health.explanation == valid_ai_payload["financial_health"]["explanation"]
    assert len(session.calls) == 4
    assert "123456" not in session.calls[-1][2]["json"]["messages"][-1]["content"]


def test_repeated_invalid_responses_are_rejected_without_logging_private_content(financial_context, valid_ai_payload, caplog):
    valid_ai_payload["financial_health"]["explanation"] = "PRIVATE_CANARY balance 123456789."
    session = FakeSession([*metadata(), chat(valid_ai_payload), chat(valid_ai_payload)])
    with pytest.raises(LocalLLMError) as error:
        OllamaService(session=session).generate(financial_context)
    assert error.value.code == "invalid_response"
    assert "PRIVATE_CANARY" not in caplog.text and "123456789" not in caplog.text


@pytest.mark.parametrize("base_url", ["https://external.invalid", "http://192.168.1.1:11434", "http://localhost.evil:11434",
                                      "http://user:secret@127.0.0.1:11434", "http://127.0.0.1:11434/api", "http://127.0.0.1:11434?x=1"])
def test_external_or_ambiguous_endpoints_are_rejected(base_url):
    with pytest.raises(ValueError):
        OllamaSettings(base_url=base_url)


def test_loopback_aliases_and_model_configuration():
    assert OllamaSettings(base_url="http://localhost:11434").base_url == "http://127.0.0.1:11434"
    assert OllamaSettings(base_url="http://[::1]:11434").base_url == "http://[::1]:11434"
    assert OllamaSettings(model="llama3").model == "llama3:latest"
    for name in ("gpt:cloud", "gpt:120b-cloud", "model\nignore instructions"):
        with pytest.raises(ValueError):
            OllamaSettings(model=name)


@pytest.mark.parametrize("where", ["tags", "show"])
def test_cloud_routing_metadata_blocks_inference_even_with_local_alias(financial_context, where):
    responses = metadata()
    if where == "tags":
        responses[0] = FakeResponse({"models": [{"name": "gemma3:4b", "remote_host": "https://cloud.invalid"}]})
    else:
        responses[1] = FakeResponse({"model_info": {"family": "gemma"}, "remote_model": "secret-remote"})
    session = FakeSession(responses)
    with pytest.raises(LocalLLMError) as error:
        OllamaService(session=session).generate(financial_context)
    assert error.value.code == "remote_model"
    assert not any(call[1].endswith("/chat") for call in session.calls)


def test_redirects_and_private_error_bodies_are_not_followed():
    response = FakeResponse({"error": "SENSITIVE PRIVATE ERROR"}, status=302)
    session = FakeSession([response])
    status = OllamaService(session=session).check_availability()
    assert not status.ready and status.code == "http_error"
    assert "SENSITIVE" not in status.message
    assert len(session.calls) == 1 and response.closed


def test_malformed_metadata_and_embedding_only_models_are_unavailable():
    for responses, code in [([FakeResponse(b"not json")], "invalid_metadata"),
                             ([FakeResponse({"models": "bad"})], "invalid_metadata"),
                             ([metadata()[0], FakeResponse({"model_info": {"x": 1}, "capabilities": ["embedding"]})], "unsupported_model")]:
        assert OllamaService(session=FakeSession(responses)).check_availability().code == code


def test_unvalidated_context_cannot_reach_http(financial_context):
    broken = financial_context.model_copy(update={"unusual_count": 99999999})
    session = FakeSession([])
    with pytest.raises(LocalLLMError):
        OllamaService(session=session).generate(broken)
    assert not session.calls


def test_truncated_or_wrong_model_chat_is_rejected(financial_context, valid_ai_payload):
    session = FakeSession([*metadata(), chat(valid_ai_payload, done_reason="length"),
                           chat(valid_ai_payload, model="other-model")])
    with pytest.raises(LocalLLMError) as error:
        OllamaService(session=session).generate(financial_context)
    assert error.value.code == "invalid_response"


def test_http_response_size_is_bounded_and_closed(monkeypatch):
    monkeypatch.setattr("src.llm_service.MAX_HTTP_BYTES", 10)
    response = FakeResponse(b"x" * 11)
    status = OllamaService(session=FakeSession([response])).check_availability()
    assert status.code == "invalid_metadata" and response.closed
