from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .utils import sha256_text, load_text, write_json, load_json


@dataclass
class CacheResult:
    hit: bool
    path: Optional[Path] = None


def cache_key(prompt_version: str, prompt_text: str, input_text: str, model: str | None) -> str:
    basis = f"{prompt_version}\n{model or ''}\n{prompt_text}\n---\n{input_text}"
    return sha256_text(basis)


def try_load(cache_dir: Path, key: str) -> tuple[CacheResult, Optional[dict]]:
    path = cache_dir / f"{key}.json"
    if path.exists():
        return CacheResult(hit=True, path=path), load_json(path)
    return CacheResult(hit=False, path=path), None


def store(cache_dir: Path, key: str, obj: dict) -> CacheResult:
    path = cache_dir / f"{key}.json"
    write_json(path, obj)
    return CacheResult(hit=False, path=path)
