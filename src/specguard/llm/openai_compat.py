from __future__ import annotations

import json
import os
from typing import Any, Dict

import requests

from .base import LLMClient, LLMConfig


class OpenAICompatClient(LLMClient):
    """OpenAI-compatible chat/completions client.

    Works with OpenAI or any API that implements `POST /chat/completions`.
    """

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        if not cfg.base_url:
            self.cfg.base_url = "https://api.openai.com/v1"
        if not cfg.api_key:
            self.cfg.api_key = os.environ.get("SPEC_GUARD_OPENAI_API_KEY")

    def complete_json(self, system: str, user: str) -> str:
        if not self.cfg.api_key:
            raise RuntimeError("Missing API key for OpenAI-compatible provider.")
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.cfg.temperature,
            "response_format": {"type": "json_object"},
        }
        # OpenAI supports seed on some models; keep best-effort
        if self.cfg.seed is not None:
            payload["seed"] = self.cfg.seed

        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=self.cfg.timeout_s)
        if r.status_code >= 400:
            raise RuntimeError(f"LLM request failed ({r.status_code}): {r.text[:400]}")
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Unexpected LLM response format: {e}; data keys={list(data.keys())}")
