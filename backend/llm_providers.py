from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


SUPPORTED_PROVIDERS = (
    "nvidia",
    "openai",
    "ollama",
    "local",
)
OPENAI_COMPATIBLE_PROVIDERS = {"nvidia", "openai", "ollama"}
PROVIDER_COOLDOWN_ERROR_CATEGORIES = {
    "configuration",
    "provider_error",
    "provider_failure",
    "rate_limit",
    "timeout",
}
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_CHAT_MODEL = "openai/gpt-oss-20b"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    adapter: str
    base_url: str
    api_key: str
    chat_model: str
    embedding_model: str
    local_model: str
    model_root: Path
    remote_requested: bool
    timeout_seconds: float
    max_retries: int
    temperature: float
    max_generation_retries: int
    max_tokens: int = 4096
    top_p: float = 1.0

    @property
    def chat_enabled(self) -> bool:
        if self.provider == "local":
            return False
        if self.provider == "ollama":
            return self.remote_requested and bool(self.base_url)
        return (
            self.remote_requested
            and bool(self.api_key)
            and bool(self.chat_model)
            and self.adapter == "openai-compatible"
        )

    @property
    def embeddings_enabled(self) -> bool:
        return self.chat_enabled and self.provider == "openai"

    @property
    def needs_sdk(self) -> bool:
        return False


@dataclass
class LLMGenerationResult:
    text: str = ""
    data: dict[str, Any] | None = None
    success: bool = False
    provider: str = "local"
    model: str = ""
    latency_ms: float = 0.0
    error_category: str = ""
    error_message: str = ""
    token_usage: dict[str, Any] | None = None
    retry_count: int = 0
    fallback_used: bool = False


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _provider_default_base_url(provider: str) -> str:
    if provider == "nvidia":
        return NVIDIA_BASE_URL
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "ollama":
        return "http://127.0.0.1:11434/v1"
    return ""


def _provider_default_chat_model(provider: str) -> str:
    if provider == "nvidia":
        return NVIDIA_CHAT_MODEL
    if provider == "ollama":
        return "llama3.1"
    if provider == "local":
        return "deterministic"
    return ""


def _provider_default_timeout(provider: str) -> float:
    if provider == "nvidia":
        return 60.0
    return 30.0


def load_provider_config(model_root: Path) -> ProviderConfig:
    requested = _first_env("LLM_PROVIDER", "SQL_COPILOT_LLM_PROVIDER").strip().lower()
    if not requested:
        if os.getenv("NVIDIA_API_KEY"):
            requested = "nvidia"
        else:
            requested = "local"
    if requested not in SUPPORTED_PROVIDERS:
        requested = "local"

    provider = requested
    api_key_names = {
        "nvidia": ("NVIDIA_API_KEY", "LLM_API_KEY", "SQL_COPILOT_LLM_API_KEY"),
        "openai": ("OPENAI_API_KEY", "LLM_API_KEY", "SQL_COPILOT_LLM_API_KEY"),
        "ollama": ("LLM_API_KEY", "SQL_COPILOT_LLM_API_KEY"),
    }.get(provider, ())
    api_key = _first_env(*api_key_names)
    remote_requested = provider != "local" and (
        _truthy(os.getenv("SQL_COPILOT_REMOTE_LLM"))
        or bool(api_key)
        or provider == "ollama"
    )
    base_url = _first_env(
        "SQL_COPILOT_LLM_BASE_URL",
        f"{provider.upper()}_BASE_URL",
        f"{provider.upper()}_API_BASE",
        "LLM_BASE_URL",
        "LLM_API_BASE",
        "OPENAI_BASE_URL",
        default=_provider_default_base_url(provider),
    )
    chat_model = _first_env(
        "SQL_COPILOT_CHAT_MODEL",
        f"{provider.upper()}_MODEL",
        f"{provider.upper()}_CHAT_MODEL",
        "LLM_MODEL",
        "OPENAI_MODEL",
        default=_provider_default_chat_model(provider),
    )
    if provider == "local":
        base_url = ""
        chat_model = _provider_default_chat_model(provider)
    elif provider == "nvidia" and chat_model in {"", "deterministic"}:
        chat_model = _provider_default_chat_model(provider)
    embedding_model = _first_env(
        "SQL_COPILOT_EMBEDDING_MODEL",
        f"{provider.upper()}_EMBEDDING_MODEL",
        "OPENAI_EMBEDDING_MODEL",
        default="text-embedding-3-large",
    )
    local_model = _first_env(
        "SQL_COPILOT_LOCAL_MODEL",
        "LOCAL_LLM_MODEL",
        default="qwen2.5-coder:1.5b",
    )
    adapter = "openai-compatible" if provider in OPENAI_COMPATIBLE_PROVIDERS else provider
    return ProviderConfig(
        provider=provider,
        adapter=adapter,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        chat_model=chat_model,
        embedding_model=embedding_model,
        local_model=local_model,
        model_root=model_root,
        remote_requested=remote_requested,
        timeout_seconds=_float_env("LLM_TIMEOUT_SECONDS", _provider_default_timeout(provider)),
        max_retries=_int_env("LLM_MAX_RETRIES", 2),
        temperature=_float_env("LLM_TEMPERATURE", 0.0),
        max_generation_retries=_int_env("MAX_GENERATION_RETRIES", 3),
        max_tokens=_int_env("LLM_MAX_TOKENS", 4096),
        top_p=_float_env("LLM_TOP_P", 1.0),
    )


def _safe_error_message(message: object, api_key: str = "") -> str:
    text = str(message or "")
    if api_key:
        text = text.replace(api_key, "[redacted]")
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"nvapi-[A-Za-z0-9._~+/=-]+", "nvapi-[redacted]", text)
    return text[:500]


def categorize_provider_error(exc: BaseException | str) -> str:
    text = str(exc).lower()
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    if "winerror 10013" in text or "access permissions" in text:
        return "network_blocked"
    if status_code in {401, 403} or "401" in text or "unauthorized" in text or "forbidden" in text:
        return "configuration"
    if status_code == 429 or "429" in text or "rate limit" in text or "too many requests" in text:
        return "rate_limit"
    if status_code and int(status_code) >= 500:
        return "provider_failure"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "json" in text or "parse" in text:
        return "invalid_json"
    if "api key" in text or "credential" in text:
        return "configuration"
    return "provider_error"


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(cleaned[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Structured model output must be a JSON object")
    return parsed


def _message_to_text(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            parts = [
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            ]
            return "".join(parts).strip()
        if content is not None:
            return str(content or "").strip()
        return str(message.get("reasoning_content") or message.get("reasoning") or "").strip()
    content = getattr(message, "content", None)
    if isinstance(content, list):
        parts = [
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        ]
        return "".join(parts).strip()
    if content is not None:
        return str(content or "").strip()
    return str(getattr(message, "reasoning_content", "") or getattr(message, "reasoning", "") or "").strip()


def _chat_completion_text_and_usage(completion: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(completion, dict):
        choices = completion.get("choices") or []
        message = (choices[0] or {}).get("message") if choices else {}
        usage = completion.get("usage") if isinstance(completion.get("usage"), dict) else {}
        return _message_to_text(message), dict(usage or {})
    choices = getattr(completion, "choices", []) or []
    choice = choices[0] if choices else None
    message = getattr(choice, "message", {}) if choice is not None else {}
    usage_obj = getattr(completion, "usage", None)
    token_usage: dict[str, Any] = {}
    if usage_obj is not None:
        if hasattr(usage_obj, "model_dump"):
            token_usage = usage_obj.model_dump()
        elif isinstance(usage_obj, dict):
            token_usage = dict(usage_obj)
    return _message_to_text(message), token_usage


class BaseLLMProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.request_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.fallback_count = 0
        self.repair_attempts = 0
        self.token_usage: dict[str, int] = {}
        self.error_counts: dict[str, int] = {}
        self._latencies: list[float] = []
        self._blocked_until = 0.0
        self._last_runtime_error_category = ""
        self._last_runtime_error_message = ""

    @property
    def available(self) -> bool:
        return False

    @property
    def chat_client(self) -> Any:
        return None

    def generate(self, messages: list[dict[str, str]] | str, **_: Any) -> LLMGenerationResult:
        category = "missing_api_key" if not self.config.api_key and self.config.provider != "ollama" else "not_configured"
        self.record_fallback(category)
        return LLMGenerationResult(
            success=False,
            provider=self.config.provider,
            model=self.config.chat_model,
            error_category=category,
            error_message="Provider is not configured; using deterministic fallback.",
            fallback_used=True,
        )

    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        *,
        repair: bool = True,
    ) -> LLMGenerationResult:
        return self.generate([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, indent=2, default=str)},
        ])

    def health_check(self, *, deep: bool = False) -> dict[str, Any]:
        if self.config.provider == "local":
            return {
                "provider": self.config.provider,
                "model": self.config.chat_model,
                "adapter": self.config.adapter,
                "configured": True,
                "available": False,
                "status": "fallback",
                "reason": "Deterministic local planner is active.",
                "base_url": self.config.base_url,
            }
        return {
            "provider": self.config.provider,
            "model": self.config.chat_model,
            "adapter": self.config.adapter,
            "configured": False,
            "available": False,
            "status": "fallback",
            "reason": "Provider is not configured.",
            "base_url": self.config.base_url,
        }

    def record_fallback(self, category: str = "deterministic_fallback") -> None:
        self.fallback_count += 1
        self.error_counts[category] = self.error_counts.get(category, 0) + 1

    def _runtime_blocked(self) -> bool:
        return self._blocked_until > time.monotonic()

    def _runtime_blocked_seconds(self) -> int:
        return max(0, int(round(self._blocked_until - time.monotonic())))

    def _provider_failure_cooldown_seconds(self) -> int:
        return max(0, _int_env("LLM_PROVIDER_FAILURE_COOLDOWN_SECONDS", 0))

    def _mark_runtime_failure(self, result: LLMGenerationResult) -> None:
        category = result.error_category or "provider_error"
        if category not in PROVIDER_COOLDOWN_ERROR_CATEGORIES:
            return
        cooldown = self._provider_failure_cooldown_seconds()
        if cooldown <= 0:
            return
        self._blocked_until = max(self._blocked_until, time.monotonic() + cooldown)
        self._last_runtime_error_category = category
        self._last_runtime_error_message = _safe_error_message(result.error_message, self.config.api_key)

    def _clear_runtime_failure(self) -> None:
        self._blocked_until = 0.0
        self._last_runtime_error_category = ""
        self._last_runtime_error_message = ""

    def _runtime_unavailable_message(self) -> str:
        category = self._last_runtime_error_category or "provider_unavailable"
        if category == "provider_error":
            reason = "Remote LLM is unavailable"
        elif category == "timeout":
            reason = "Remote LLM request timed out"
        elif category == "rate_limit":
            reason = "Remote LLM rate limit was reached"
        elif category == "configuration":
            reason = "Remote LLM configuration was rejected"
        elif category == "network_blocked":
            reason = "Remote LLM network access is blocked"
        else:
            reason = "Remote LLM is temporarily unavailable"
        return f"{reason}; deterministic fallback is active."

    def _blocked_generation_result(self) -> LLMGenerationResult:
        category = self._last_runtime_error_category or "provider_unavailable"
        self.record_fallback(category)
        return LLMGenerationResult(
            success=False,
            provider=self.config.provider,
            model=self.config.chat_model,
            error_category=category,
            error_message=self._runtime_unavailable_message(),
            fallback_used=True,
        )

    def _record_result(self, result: LLMGenerationResult) -> LLMGenerationResult:
        self.request_count += 1
        if result.success:
            self._clear_runtime_failure()
            self.success_count += 1
        else:
            self.failure_count += 1
            category = result.error_category or "provider_error"
            self.error_counts[category] = self.error_counts.get(category, 0) + 1
            self._mark_runtime_failure(result)
        if result.fallback_used:
            self.fallback_count += 1
        if result.latency_ms:
            self._latencies.append(float(result.latency_ms))
            self._latencies = self._latencies[-500:]
        for key, value in (result.token_usage or {}).items():
            if isinstance(value, (int, float)):
                self.token_usage[key] = self.token_usage.get(key, 0) + int(value)
        return result

    def metrics(self) -> dict[str, Any]:
        latencies = sorted(self._latencies)

        def percentile(p: float) -> float:
            if not latencies:
                return 0.0
            index = min(len(latencies) - 1, max(0, int(round((len(latencies) - 1) * p))))
            return round(latencies[index], 3)

        return {
            "provider": self.config.provider,
            "model": self.config.chat_model,
            "configured": self.config.provider == "local" or self.available,
            "request_count": self.request_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round((self.success_count / self.request_count) * 100, 2) if self.request_count else 0,
            "fallback_count": self.fallback_count,
            "fallback_rate": round((self.fallback_count / max(1, self.request_count + self.fallback_count)) * 100, 2),
            "average_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "p50_latency_ms": percentile(0.50),
            "p95_latency_ms": percentile(0.95),
            "token_usage": dict(self.token_usage),
            "repair_attempts": self.repair_attempts,
            "provider_errors": dict(sorted(self.error_counts.items())),
        }


class OpenAICompatibleLLMProvider(BaseLLMProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        chat_client_factory: Callable[..., Any] | None = None,
        http_client: Any = None,
    ) -> None:
        super().__init__(config)
        self._client = None
        self._initialization_error = ""
        if not config.chat_enabled:
            return
        if chat_client_factory is None:
            try:
                from langchain_openai import ChatOpenAI  # type: ignore
                chat_client_factory = ChatOpenAI
            except ImportError as exc:  # pragma: no cover - depends on optional install
                self._initialization_error = _safe_error_message(exc, config.api_key)
                return
        kwargs: dict[str, Any] = {
            "base_url": config.base_url,
            "model": config.chat_model,
            "api_key": config.api_key,
            "temperature": config.temperature,
            "max_retries": config.max_retries,
        }
        if http_client is not None:
            kwargs["http_client"] = http_client
        for timeout_key in ("timeout", "request_timeout"):
            try:
                self._client = chat_client_factory(**{**kwargs, timeout_key: config.timeout_seconds})
                break
            except TypeError:
                continue
            except Exception as exc:
                self._initialization_error = _safe_error_message(exc, config.api_key)
                break
        if self._client is None and not self._initialization_error:
            try:
                self._client = chat_client_factory(**kwargs)
            except Exception as exc:  # pragma: no cover - adapter-specific
                self._initialization_error = _safe_error_message(exc, config.api_key)

    @property
    def available(self) -> bool:
        return self._client is not None and not self._runtime_blocked()

    @property
    def chat_client(self) -> Any:
        return self._client

    def generate(self, messages: list[dict[str, str]] | str, **_: Any) -> LLMGenerationResult:
        if self._runtime_blocked():
            return self._blocked_generation_result()
        if not self.available:
            category = "missing_api_key" if not self.config.api_key else "adapter_unavailable"
            self.record_fallback(category)
            return LLMGenerationResult(
                success=False,
                provider=self.config.provider,
                model=self.config.chat_model,
                error_category=category,
                error_message=self._initialization_error or "Provider adapter is unavailable.",
                fallback_used=True,
            )
        started = time.perf_counter()
        try:
            response = self._client.invoke(messages)
            text = str(getattr(response, "content", response) or "").strip()
            response_metadata = getattr(response, "response_metadata", {}) or {}
            token_usage = (
                getattr(response, "usage_metadata", None)
                or response_metadata.get("token_usage")
                or response_metadata.get("usage")
                or {}
            )
            return self._record_result(LLMGenerationResult(
                text=text,
                success=True,
                provider=self.config.provider,
                model=self.config.chat_model,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                token_usage=dict(token_usage) if isinstance(token_usage, dict) else {},
            ))
        except Exception as exc:
            return self._record_result(LLMGenerationResult(
                success=False,
                provider=self.config.provider,
                model=self.config.chat_model,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error_category=categorize_provider_error(exc),
                error_message=_safe_error_message(exc, self.config.api_key),
                fallback_used=True,
            ))

    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        *,
        repair: bool = True,
    ) -> LLMGenerationResult:
        payload_text = json.dumps(user_payload, indent=2, default=str)
        result = self.generate([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload_text},
        ])
        if not result.success:
            return result
        try:
            result.data = extract_json_object(result.text)
            return result
        except Exception as exc:
            if not repair:
                result.success = False
                result.error_category = "invalid_json"
                result.error_message = _safe_error_message(exc, self.config.api_key)
                self.error_counts["invalid_json"] = self.error_counts.get("invalid_json", 0) + 1
                return result
            self.repair_attempts += 1
            repair_result = self.generate([
                {
                    "role": "system",
                    "content": (
                        "Return only a valid JSON object. Do not include markdown, commentary, "
                        "or keys that are not supported by the requested schema."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Repair this model response into valid JSON.\n\n"
                        f"EXPECTED_TASK:\n{system_prompt}\n\n"
                        f"ORIGINAL_PAYLOAD:\n{payload_text}\n\n"
                        f"MODEL_RESPONSE:\n{result.text}"
                    ),
                },
            ])
            repair_result.retry_count = result.retry_count + 1
            if not repair_result.success:
                return repair_result
            try:
                repair_result.data = extract_json_object(repair_result.text)
                return repair_result
            except Exception as repair_exc:
                repair_result.success = False
                repair_result.error_category = "invalid_json"
                repair_result.error_message = _safe_error_message(repair_exc, self.config.api_key)
                self.error_counts["invalid_json"] = self.error_counts.get("invalid_json", 0) + 1
                return repair_result

    def health_check(self, *, deep: bool = False) -> dict[str, Any]:
        blocked = self._runtime_blocked()
        status = {
            "provider": self.config.provider,
            "model": self.config.chat_model,
            "adapter": self.config.adapter,
            "configured": bool(self.config.api_key or self.config.provider == "ollama"),
            "available": self.available,
            "status": "ready" if self.available else "fallback",
            "base_url": self.config.base_url,
        }
        if blocked:
            status["reason"] = self._runtime_unavailable_message()
            status["error_category"] = self._last_runtime_error_category
            status["cooldown_seconds_remaining"] = self._runtime_blocked_seconds()
        elif not status["configured"]:
            status["reason"] = (
                f"{self.config.provider} API key is not configured. "
                "Set the provider-specific API key environment variable."
            )
        elif not self.config.chat_model and self.config.provider != "ollama":
            status["reason"] = f"{self.config.provider} model is required."
        elif self._initialization_error:
            status["reason"] = self._initialization_error
        if deep and self.available:
            result = self.generate([
                {"role": "system", "content": "Return only OK."},
                {"role": "user", "content": "health_check"},
            ])
            status.update({
                "status": "ok" if result.success else "fallback",
                "latency_ms": result.latency_ms,
                "error_category": result.error_category,
            })
        return status


class OpenAIChatCompletionsProvider(BaseLLMProvider):
    """OpenAI SDK chat-completions adapter for OpenAI-compatible APIs."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(config)
        self._client = None
        self._initialization_error = ""
        if not config.chat_enabled:
            return
        if client_factory is None:
            try:
                from openai import OpenAI  # type: ignore
                client_factory = OpenAI
            except ImportError as exc:  # pragma: no cover - optional dependency boundary
                self._initialization_error = _safe_error_message(exc, config.api_key)
                return
        try:
            self._client = client_factory(
                base_url=config.base_url,
                api_key=config.api_key,
                timeout=config.timeout_seconds,
                max_retries=config.max_retries,
            )
        except TypeError:
            try:
                self._client = client_factory(
                    base_url=config.base_url,
                    api_key=config.api_key,
                )
            except Exception as exc:
                self._initialization_error = _safe_error_message(exc, config.api_key)
        except Exception as exc:
            self._initialization_error = _safe_error_message(exc, config.api_key)

    @property
    def available(self) -> bool:
        return self._client is not None and not self._runtime_blocked()

    @property
    def chat_client(self) -> Any:
        return None

    def generate(self, messages: list[dict[str, str]] | str, **_: Any) -> LLMGenerationResult:
        if self._runtime_blocked():
            return self._blocked_generation_result()
        if not self.available:
            category = "missing_api_key" if not self.config.api_key else "adapter_unavailable"
            self.record_fallback(category)
            return LLMGenerationResult(
                success=False,
                provider=self.config.provider,
                model=self.config.chat_model,
                error_category=category,
                error_message=self._initialization_error or "Provider adapter is unavailable.",
                fallback_used=True,
            )
        normalized_messages = (
            messages if isinstance(messages, list)
            else [{"role": "user", "content": str(messages)}]
        )
        started = time.perf_counter()
        try:
            completion = self._client.chat.completions.create(
                model=self.config.chat_model,
                messages=normalized_messages,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                max_tokens=self.config.max_tokens,
                stream=False,
                timeout=self.config.timeout_seconds,
            )
            text, token_usage = _chat_completion_text_and_usage(completion)
            return self._record_result(LLMGenerationResult(
                text=text,
                success=True,
                provider=self.config.provider,
                model=self.config.chat_model,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                token_usage=token_usage,
            ))
        except Exception as exc:
            return self._record_result(LLMGenerationResult(
                success=False,
                provider=self.config.provider,
                model=self.config.chat_model,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error_category=categorize_provider_error(exc),
                error_message=_safe_error_message(exc, self.config.api_key),
                fallback_used=True,
            ))

    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        *,
        repair: bool = True,
    ) -> LLMGenerationResult:
        payload_text = json.dumps(user_payload, indent=2, default=str)
        result = self.generate([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload_text},
        ])
        if not result.success:
            return result
        try:
            result.data = extract_json_object(result.text)
            return result
        except Exception as exc:
            if not repair:
                result.success = False
                result.error_category = "invalid_json"
                result.error_message = _safe_error_message(exc, self.config.api_key)
                self.error_counts["invalid_json"] = self.error_counts.get("invalid_json", 0) + 1
                return result
            self.repair_attempts += 1
            repair_result = self.generate([
                {
                    "role": "system",
                    "content": "Return only a valid JSON object. Do not include markdown or commentary.",
                },
                {
                    "role": "user",
                    "content": (
                        "Repair this model response into valid JSON.\n\n"
                        f"EXPECTED_TASK:\n{system_prompt}\n\n"
                        f"ORIGINAL_PAYLOAD:\n{payload_text}\n\n"
                        f"MODEL_RESPONSE:\n{result.text}"
                    ),
                },
            ])
            repair_result.retry_count = result.retry_count + 1
            if not repair_result.success:
                return repair_result
            try:
                repair_result.data = extract_json_object(repair_result.text)
                return repair_result
            except Exception as repair_exc:
                repair_result.success = False
                repair_result.error_category = "invalid_json"
                repair_result.error_message = _safe_error_message(repair_exc, self.config.api_key)
                self.error_counts["invalid_json"] = self.error_counts.get("invalid_json", 0) + 1
                return repair_result

    def health_check(self, *, deep: bool = False) -> dict[str, Any]:
        blocked = self._runtime_blocked()
        status = {
            "provider": self.config.provider,
            "model": self.config.chat_model,
            "adapter": "openai-chat-completions",
            "configured": bool(self.config.api_key),
            "available": self.available,
            "status": "ready" if self.available else "fallback",
            "base_url": self.config.base_url,
        }
        if blocked:
            status["reason"] = self._runtime_unavailable_message()
            status["error_category"] = self._last_runtime_error_category
            status["cooldown_seconds_remaining"] = self._runtime_blocked_seconds()
        elif not status["configured"]:
            status["reason"] = (
                "NVIDIA_API_KEY is not configured. "
                "Save a valid NVIDIA API key on the Settings page or set NVIDIA_API_KEY before starting the backend."
            )
        elif self._initialization_error:
            status["reason"] = self._initialization_error
        if deep and self.available:
            result = self.generate([
                {"role": "system", "content": "Return only OK."},
                {"role": "user", "content": "health_check"},
            ])
            status.update({
                "status": "ok" if result.success else "fallback",
                "latency_ms": result.latency_ms,
                "error_category": result.error_category,
            })
        return status


class NvidiaHttpChatCompletionsProvider(BaseLLMProvider):
    """Direct NVIDIA API Catalog chat-completions adapter.

    The OpenAI SDK can raise transient APIConnectionError on this endpoint in
    some local Windows environments while the same `/chat/completions` request
    succeeds over plain HTTP clients. This adapter keeps the request shape
    OpenAI-compatible and removes that SDK dependency from the NVIDIA path.
    """

    adapter_name = "nvidia-http-chat-completions"

    def __init__(
        self,
        config: ProviderConfig,
        *,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(config)
        self._urlopen = urlopen or urllib.request.urlopen
        self._initialization_error = ""

    @property
    def available(self) -> bool:
        return self.config.chat_enabled and not self._runtime_blocked()

    def _request_payload(self, messages: list[dict[str, str]] | str) -> dict[str, Any]:
        normalized_messages = (
            messages if isinstance(messages, list)
            else [{"role": "user", "content": str(messages)}]
        )
        return {
            "model": self.config.chat_model,
            "messages": normalized_messages,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }

    def generate(self, messages: list[dict[str, str]] | str, **_: Any) -> LLMGenerationResult:
        if self._runtime_blocked():
            return self._blocked_generation_result()
        if not self.available:
            category = "missing_api_key" if not self.config.api_key else "adapter_unavailable"
            self.record_fallback(category)
            return LLMGenerationResult(
                success=False,
                provider=self.config.provider,
                model=self.config.chat_model,
                error_category=category,
                error_message=self._initialization_error or "Provider adapter is unavailable.",
                fallback_used=True,
            )

        started = time.perf_counter()
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload = json.dumps(self._request_payload(messages), ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
            body = json.loads(raw_body)
            text, token_usage = _chat_completion_text_and_usage(body)
            return self._record_result(LLMGenerationResult(
                text=text,
                success=True,
                provider=self.config.provider,
                model=self.config.chat_model,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                token_usage=token_usage,
            ))
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = str(exc)
            message = f"HTTP {getattr(exc, 'code', '')}: {body}".strip()
            return self._record_result(LLMGenerationResult(
                success=False,
                provider=self.config.provider,
                model=self.config.chat_model,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error_category=categorize_provider_error(message),
                error_message=_safe_error_message(message, self.config.api_key),
                fallback_used=True,
            ))
        except Exception as exc:
            return self._record_result(LLMGenerationResult(
                success=False,
                provider=self.config.provider,
                model=self.config.chat_model,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error_category=categorize_provider_error(exc),
                error_message=_safe_error_message(exc, self.config.api_key),
                fallback_used=True,
            ))

    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        *,
        repair: bool = True,
    ) -> LLMGenerationResult:
        payload_text = json.dumps(user_payload, indent=2, default=str)
        result = self.generate([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload_text},
        ])
        if not result.success:
            return result
        try:
            result.data = extract_json_object(result.text)
            return result
        except Exception as exc:
            if not repair:
                result.success = False
                result.error_category = "invalid_json"
                result.error_message = _safe_error_message(exc, self.config.api_key)
                self.error_counts["invalid_json"] = self.error_counts.get("invalid_json", 0) + 1
                return result
            self.repair_attempts += 1
            repair_result = self.generate([
                {
                    "role": "system",
                    "content": "Return only a valid JSON object. Do not include markdown or commentary.",
                },
                {
                    "role": "user",
                    "content": (
                        "Repair this model response into valid JSON.\n\n"
                        f"EXPECTED_TASK:\n{system_prompt}\n\n"
                        f"ORIGINAL_PAYLOAD:\n{payload_text}\n\n"
                        f"MODEL_RESPONSE:\n{result.text}"
                    ),
                },
            ])
            repair_result.retry_count = result.retry_count + 1
            if not repair_result.success:
                return repair_result
            try:
                repair_result.data = extract_json_object(repair_result.text)
                return repair_result
            except Exception as repair_exc:
                repair_result.success = False
                repair_result.error_category = "invalid_json"
                repair_result.error_message = _safe_error_message(repair_exc, self.config.api_key)
                self.error_counts["invalid_json"] = self.error_counts.get("invalid_json", 0) + 1
                return repair_result

    def health_check(self, *, deep: bool = False) -> dict[str, Any]:
        blocked = self._runtime_blocked()
        status = {
            "provider": self.config.provider,
            "model": self.config.chat_model,
            "adapter": self.adapter_name,
            "configured": bool(self.config.api_key),
            "available": self.available,
            "status": "ready" if self.available else "fallback",
            "base_url": self.config.base_url,
        }
        if blocked:
            status["reason"] = self._runtime_unavailable_message()
            status["error_category"] = self._last_runtime_error_category
            status["cooldown_seconds_remaining"] = self._runtime_blocked_seconds()
        elif not status["configured"]:
            status["reason"] = (
                "NVIDIA_API_KEY is not configured. "
                "Save a valid NVIDIA API key on the Settings page or set NVIDIA_API_KEY before starting the backend."
            )
        elif not self.config.chat_model:
            status["reason"] = "NVIDIA model is required."
        if deep and self.available:
            result = self.generate([
                {"role": "system", "content": "Return only OK."},
                {"role": "user", "content": "health_check"},
            ])
            status.update({
                "status": "ok" if result.success else "fallback",
                "latency_ms": result.latency_ms,
                "error_category": result.error_category,
            })
        return status


def create_llm_provider(
    config: ProviderConfig,
    *,
    chat_client_factory: Callable[..., Any] | None = None,
    http_client: Any = None,
) -> BaseLLMProvider:
    if config.provider == "nvidia":
        return NvidiaHttpChatCompletionsProvider(config)
    if config.adapter == "openai-compatible":
        return OpenAICompatibleLLMProvider(
            config,
            chat_client_factory=chat_client_factory,
            http_client=http_client,
        )
    return BaseLLMProvider(config)
