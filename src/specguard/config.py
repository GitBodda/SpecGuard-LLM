from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class SpecGuardConfig:
    # Optional secondary repo for mapping (e.g., a client repo checkout)
    map_repo: Optional[str] = None

    # GitHub slug for spec repo links (owner/repo)
    repo_slug: Optional[str] = None

    # Extra redaction regex patterns
    extra_redact: List[str] = field(default_factory=list)

    # Search behavior
    max_keyword_hits: int = 40
    search_backend: str = "auto"  # auto|rg|git_grep
    prefer_tests: bool = True

    # Output behavior
    max_findings: int = 200


def load_config(path: Optional[str]) -> SpecGuardConfig:
    if not path:
        return SpecGuardConfig()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    obj = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cfg = SpecGuardConfig()

    cfg.map_repo = obj.get("map_repo", cfg.map_repo)
    cfg.repo_slug = obj.get("repo_slug", cfg.repo_slug)
    cfg.extra_redact = list(obj.get("extra_redact", cfg.extra_redact) or [])
    cfg.max_keyword_hits = int(obj.get("max_keyword_hits", cfg.max_keyword_hits))
    cfg.search_backend = str(obj.get("search_backend", cfg.search_backend))
    cfg.prefer_tests = bool(obj.get("prefer_tests", cfg.prefer_tests))
    cfg.max_findings = int(obj.get("max_findings", cfg.max_findings))
    return cfg
