"""LLM provider abstraction.

Import-safe and offline-friendly: SDK clients are constructed lazily on first
use, and a missing API key only raises when a call is actually made. A
``NullProvider`` echo fallback keeps offline tests and the heuristic demo path
working without any network access.
"""

from __future__ import annotations

from typing import List, Optional

from app.core.config import Settings, settings as _default_settings
from app.core.logging import get_logger

logger = get_logger("llm.provider")

Message = dict  # {"role": "system"|"user"|"assistant", "content": str}

# OpenAI-compatible base URLs for non-OpenAI providers.
_COMPAT_BASE_URLS = {
    "ollama": None,  # filled from settings.OLLAMA_BASE_URL
    "mistral": "https://api.mistral.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "custom": None,  # filled from settings.LLM_BASE_URL
}

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "ollama": "llama3",
    "mistral": "mistral-small-latest",
    "gemini": "gemini-1.5-flash",
    "custom": "gpt-4o-mini",
}


class LLMProviderError(RuntimeError):
    """Raised when an LLM call cannot be completed (e.g. missing key)."""


class LLMProvider:
    """Abstract base class for chat-capable LLM providers."""

    name = "base"

    def chat(self, messages: List[Message], **kw) -> str:
        raise NotImplementedError

    def complete(self, prompt: str, **kw) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kw)

    @property
    def available(self) -> bool:
        """Whether the provider can actually make a call (key/SDK present)."""
        return True


class NullProvider(LLMProvider):
    """Offline echo provider used when no real LLM is configured."""

    name = "null"

    @property
    def available(self) -> bool:
        return False

    def chat(self, messages: List[Message], **kw) -> str:
        # Echo the last user message so downstream heuristics can take over.
        for m in reversed(messages):
            if m.get("role") == "user":
                return f"[null-provider] {m.get('content', '')}"
        return "[null-provider]"


class OpenAIProvider(LLMProvider):
    """OpenAI / OpenAI-compatible provider (also Ollama/Mistral/Gemini/custom)."""

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str],
        model: str,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError("openai SDK not installed") from exc
        # Local providers (ollama) accept a dummy key.
        key = self.api_key or "not-needed"
        kwargs = {"api_key": key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    @property
    def available(self) -> bool:
        # Local/base_url providers don't require a key.
        return bool(self.api_key or self.base_url)

    def chat(self, messages: List[Message], temperature: float = 0.0, **kw) -> str:
        client = self._get_client()
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                **kw,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"OpenAI-compatible call failed: {exc}") from exc
        return (resp.choices[0].message.content or "").strip()


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    name = "anthropic"

    def __init__(self, api_key: Optional[str], model: str):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise LLMProviderError("Anthropic API key not configured")
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError("anthropic SDK not installed") from exc
        self._client = Anthropic(api_key=self.api_key)
        return self._client

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: List[Message], temperature: float = 0.0, max_tokens: int = 1024, **kw) -> str:
        client = self._get_client()
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        convo = [m for m in messages if m.get("role") != "system"]
        # Only pass ``system`` when non-empty: the Anthropic API rejects an
        # explicit ``system=None`` ("system: Input should be a valid array").
        if system:
            kw["system"] = system
        try:
            resp = client.messages.create(
                model=self.model,
                messages=convo or [{"role": "user", "content": ""}],
                temperature=temperature,
                max_tokens=max_tokens,
                **kw,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"Anthropic call failed: {exc}") from exc
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(parts).strip()


def get_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Factory selecting a provider by ``LLM_PROVIDER``.

    Falls back to :class:`NullProvider` when the chosen provider has no usable
    credentials, so callers can always get a working (offline) object.
    """
    s = settings or _default_settings
    provider = (s.LLM_PROVIDER or "openai").lower()
    model = s.LLM_MODEL or _DEFAULT_MODELS.get(provider, "gpt-4o-mini")

    if provider == "anthropic":
        prov: LLMProvider = AnthropicProvider(api_key=s.LLM_API_KEY, model=model)
    elif provider == "openai":
        prov = OpenAIProvider(api_key=s.LLM_API_KEY, model=model, base_url=s.LLM_BASE_URL)
    elif provider in _COMPAT_BASE_URLS:
        base_url = s.LLM_BASE_URL
        if provider == "ollama":
            base_url = (s.OLLAMA_BASE_URL.rstrip("/") + "/v1") if not base_url else base_url
        elif provider == "gemini":
            base_url = base_url or _COMPAT_BASE_URLS["gemini"]
        elif provider == "mistral":
            base_url = base_url or _COMPAT_BASE_URLS["mistral"]
        prov = OpenAIProvider(api_key=s.LLM_API_KEY, model=model, base_url=base_url)
    else:
        logger.warning("Unknown LLM_PROVIDER %r; using NullProvider", provider)
        return NullProvider()

    if not prov.available:
        logger.info("Provider %s has no credentials; using NullProvider fallback", provider)
        return NullProvider()
    return prov
