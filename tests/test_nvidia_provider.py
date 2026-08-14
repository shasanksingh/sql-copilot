from __future__ import annotations

import os
from pathlib import Path

from backend.llm_providers import (
    NvidiaHttpChatCompletionsProvider,
    OpenAIChatCompletionsProvider,
    OpenAICompatibleLLMProvider,
    ProviderConfig,
    categorize_provider_error,
    create_llm_provider,
    extract_json_object,
    load_provider_config,
)
from backend.runtime_config import load_dotenv_file
from agentic.enterprise_copilot import CopilotResult, QueryCacheLayer


def test_nvidia_provider_env_aliases(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://integrate.api.nvidia.com/v1")

    config = load_provider_config(tmp_path)

    assert config.provider == "nvidia"
    assert config.adapter == "openai-compatible"
    assert config.chat_model == "openai/gpt-oss-20b"
    assert config.base_url == "https://integrate.api.nvidia.com/v1"
    assert config.chat_enabled is True


def test_generic_llm_provider_overrides_local_template_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SQL_COPILOT_LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://integrate.api.nvidia.com/v1")

    config = load_provider_config(tmp_path)

    assert config.provider == "nvidia"
    assert config.chat_enabled is True


def test_nvidia_api_key_selects_provider_when_unset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SQL_COPILOT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    config = load_provider_config(tmp_path)

    assert config.provider == "nvidia"
    assert config.chat_model == "openai/gpt-oss-20b"


def test_nvidia_api_key_wins_over_stale_generic_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-key")
    monkeypatch.setenv("LLM_API_KEY", "stale-generic-key")

    config = load_provider_config(tmp_path)

    assert config.provider == "nvidia"
    assert config.api_key == "nvidia-key"
    assert config.chat_model == "openai/gpt-oss-20b"


def test_missing_nvidia_key_disables_chat(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    config = load_provider_config(tmp_path)

    assert config.provider == "nvidia"
    assert config.chat_enabled is False


def test_custom_provider_defaults_do_not_use_removed_genai_lab_model(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    config = load_provider_config(tmp_path)

    assert config.provider == "openai"
    assert config.base_url == "https://api.openai.com/v1"
    assert config.chat_model == ""


def test_extract_json_object_from_fenced_response() -> None:
    parsed = extract_json_object('```json\n{"sql": "SELECT 1;", "model_confidence": 0.9}\n```')

    assert parsed["sql"] == "SELECT 1;"
    assert parsed["model_confidence"] == 0.9


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.response_metadata = {"token_usage": {"total_tokens": 12}}


class _FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return _FakeResponse("not json")
        return _FakeResponse('{"sql": "SELECT 1;", "model_confidence": 90}')


def test_structured_generation_repairs_malformed_json(tmp_path: Path) -> None:
    fake = _FakeClient()
    config = ProviderConfig(
        provider="nvidia",
        adapter="openai-compatible",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        chat_model="openai/gpt-oss-20b",
        embedding_model="",
        local_model="",
        model_root=tmp_path,
        remote_requested=True,
        timeout_seconds=30,
        max_retries=0,
        temperature=0,
        max_generation_retries=3,
    )
    provider = OpenAICompatibleLLMProvider(config, chat_client_factory=lambda **_: fake)

    result = provider.generate_structured("Return JSON.", {"query": "select one"})

    assert result.success is True
    assert result.data == {"sql": "SELECT 1;", "model_confidence": 90}
    assert result.retry_count == 1
    assert provider.repair_attempts == 1
    assert provider.metrics()["success_count"] == 2


class _FakeOpenAIMessage:
    content = '{"sql": "SELECT 1;", "model_confidence": 91}'


class _FakeOpenAIChoice:
    message = _FakeOpenAIMessage()


class _FakeUsage:
    def model_dump(self):
        return {"total_tokens": 9}


class _FakeCompletions:
    def __init__(self, parent) -> None:
        self.parent = parent

    def create(self, **kwargs):
        self.parent.kwargs = kwargs
        return type("Completion", (), {"choices": [_FakeOpenAIChoice()], "usage": _FakeUsage()})()


class _FakeChat:
    def __init__(self, parent) -> None:
        self.completions = _FakeCompletions(parent)


class _FakeOpenAIClient:
    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs
        self.kwargs = {}
        self.chat = _FakeChat(self)


def test_nvidia_direct_openai_sdk_adapter_uses_chat_completions(tmp_path: Path) -> None:
    holder: dict[str, _FakeOpenAIClient] = {}

    def factory(**kwargs):
        client = _FakeOpenAIClient(**kwargs)
        holder["client"] = client
        return client

    config = ProviderConfig(
        provider="nvidia",
        adapter="openai-compatible",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        chat_model="openai/gpt-oss-20b",
        embedding_model="",
        local_model="",
        model_root=tmp_path,
        remote_requested=True,
        timeout_seconds=30,
        max_retries=2,
        temperature=1,
        max_generation_retries=3,
        max_tokens=4096,
        top_p=1,
    )
    provider = OpenAIChatCompletionsProvider(config, client_factory=factory)

    result = provider.generate_structured("Return JSON.", {"query": "select one"})

    assert result.success is True
    assert result.data["sql"] == "SELECT 1;"
    assert holder["client"].init_kwargs["base_url"] == "https://integrate.api.nvidia.com/v1"
    assert holder["client"].kwargs["model"] == "openai/gpt-oss-20b"
    assert holder["client"].kwargs["max_tokens"] == 4096


class _FakeHttpResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return (
            b'{"choices":[{"message":{"content":"{\\"sql\\": \\"SELECT 1;\\", '
            b'\\"model_confidence\\": 92}"}}],"usage":{"total_tokens":11}}'
        )


def test_nvidia_provider_uses_direct_http_chat_completions(tmp_path: Path) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return _FakeHttpResponse()

    config = ProviderConfig(
        provider="nvidia",
        adapter="openai-compatible",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        chat_model="openai/gpt-oss-20b",
        embedding_model="",
        local_model="",
        model_root=tmp_path,
        remote_requested=True,
        timeout_seconds=30,
        max_retries=0,
        temperature=1,
        max_generation_retries=3,
        max_tokens=4096,
        top_p=1,
    )
    provider = NvidiaHttpChatCompletionsProvider(config, urlopen=fake_urlopen)

    result = provider.generate_structured("Return JSON.", {"query": "select one"})

    assert result.success is True
    assert result.data == {"sql": "SELECT 1;", "model_confidence": 92}
    assert requests[0][0].full_url == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert requests[0][1] == 30
    assert provider.health_check()["adapter"] == "nvidia-http-chat-completions"
    assert isinstance(create_llm_provider(config), NvidiaHttpChatCompletionsProvider)


def test_windows_socket_denial_is_reported_as_network_blocked() -> None:
    message = (
        "<urlopen error [WinError 10013] An attempt was made to access a socket "
        "in a way forbidden by its access permissions>"
    )

    assert categorize_provider_error(message) == "network_blocked"


class _FailingCompletions:
    def create(self, **_kwargs):
        raise RuntimeError("Connection error.")


class _FailingChat:
    completions = _FailingCompletions()


class _FailingOpenAIClient:
    chat = _FailingChat()


def test_nvidia_provider_connection_failure_enters_fallback_cooldown(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_PROVIDER_FAILURE_COOLDOWN_SECONDS", "300")
    config = ProviderConfig(
        provider="nvidia",
        adapter="openai-compatible",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        chat_model="openai/gpt-oss-20b",
        embedding_model="",
        local_model="",
        model_root=tmp_path,
        remote_requested=True,
        timeout_seconds=30,
        max_retries=0,
        temperature=1,
        max_generation_retries=3,
        max_tokens=4096,
        top_p=1,
    )
    provider = OpenAIChatCompletionsProvider(config, client_factory=lambda **_: _FailingOpenAIClient())

    first = provider.generate_structured("Return JSON.", {"query": "select one"})
    status = provider.health_check(deep=False)
    second = provider.generate_structured("Return JSON.", {"query": "select two"})

    assert first.success is False
    assert first.error_category == "provider_error"
    assert provider.available is False
    assert status["available"] is False
    assert status["status"] == "fallback"
    assert status["error_category"] == "provider_error"
    assert "deterministic fallback is active" in status["reason"]
    assert second.error_message == "Remote LLM is unavailable; deterministic fallback is active."


def test_dotenv_loader_keeps_existing_environment(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_PROVIDER=nvidia\n"
        "NVIDIA_MODEL=openai/gpt-oss-20b\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)

    load_dotenv_file(env_file)

    assert load_provider_config(tmp_path).provider == "local"
    assert os.environ["NVIDIA_MODEL"] == "openai/gpt-oss-20b"


def test_runtime_dotenv_loader_can_override_template_default(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".runtime-provider.env"
    env_file.write_text(
        "LLM_PROVIDER=nvidia\n"
        "LLM_API_KEY=test-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    load_dotenv_file(env_file, override=True)

    config = load_provider_config(tmp_path)
    assert config.provider == "nvidia"
    assert config.chat_enabled is True


def test_query_cache_is_namespaced_by_provider(tmp_path: Path) -> None:
    local_cache = QueryCacheLayer(tmp_path / "state.db", namespace="local:deterministic:unavailable")
    nvidia_cache = QueryCacheLayer(
        tmp_path / "state.db",
        namespace="nvidia:openai-chat-completions:openai_gpt-oss-20b:available",
    )
    result = CopilotResult(
        sql="SELECT 1;",
        confidence=100,
        valid=True,
        validation="Valid",
        clarification_required=False,
        clarification_options=[],
        intent={},
        entities={},
        selected_tables=[],
        selected_columns=[],
        join_path=[],
        plan=None,
        optimizations=[],
        llm_trace={"provider": "local"},
        provider_status={"provider": "local"},
    )

    local_cache.put("Count bugs by severity", result)

    assert local_cache.get("Count bugs by severity") is not None
    assert nvidia_cache.get("Count bugs by severity") is None

    failed_nvidia = CopilotResult(
        sql="SELECT 1;",
        confidence=100,
        valid=True,
        validation="Valid",
        clarification_required=False,
        clarification_options=[],
        intent={},
        entities={},
        selected_tables=[],
        selected_columns=[],
        join_path=[],
        plan=None,
        optimizations=[],
        llm_trace={"provider": "nvidia", "active": True, "fallback_used": True},
        provider_status={"provider": "nvidia"},
    )

    nvidia_cache.put("Count bugs by status", failed_nvidia)

    assert nvidia_cache.get("Count bugs by status") is None
