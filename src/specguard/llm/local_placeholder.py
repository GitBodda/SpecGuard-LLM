from __future__ import annotations

import json
from .base import LLMClient, LLMConfig


class LocalPlaceholderClient(LLMClient):
    """Placeholder for local models (e.g. llama.cpp / vLLM / Ollama).

    This does NOT implement local inference; it exists to keep the design modular.
    """

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def complete_json(self, system: str, user: str) -> str:
        # Minimal stub output so the tool still runs in 'local' provider mode.
        return json.dumps({
            "rules": [],
            "note": "Local model provider is a placeholder. Configure SPEC_GUARD_LLM_PROVIDER=openai for real extraction."
        })
