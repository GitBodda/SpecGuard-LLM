from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class LLMConfig:
    provider: str
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout_s: int = 60
    temperature: float = 0.0
    seed: Optional[int] = 1


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> str:
        """Return a JSON string."""
        ...
