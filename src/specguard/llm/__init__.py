from __future__ import annotations

import os
from .base import LLMConfig, LLMClient
from .openai_compat import OpenAICompatClient
from .local_placeholder import LocalPlaceholderClient


def make_client(deterministic: bool) -> tuple[LLMClient | None, LLMConfig | None]:
    provider = os.environ.get("SPEC_GUARD_LLM_PROVIDER", "").strip().lower()
    if not provider:
        return None, None

    model = os.environ.get("SPEC_GUARD_OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.environ.get("SPEC_GUARD_OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("SPEC_GUARD_OPENAI_API_KEY")

    temperature = 0.0 if deterministic else float(os.environ.get("SPEC_GUARD_LLM_TEMPERATURE", "0.2"))
    seed = 1 if deterministic else None

    cfg = LLMConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        seed=seed,
    )

    if provider in ("openai", "openai_compat", "openai-compatible"):
        return OpenAICompatClient(cfg), cfg
    if provider in ("local", "ollama", "llama", "vllm"):
        return LocalPlaceholderClient(cfg), cfg

    raise RuntimeError(f"Unknown LLM provider: {provider}")
