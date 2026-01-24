from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


Severity = Literal["LOW", "MEDIUM", "HIGH"]


class Location(BaseModel):
    path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    kind: Literal["spec", "code", "test", "other"] = "other"


class ExtractedRule(BaseModel):
    rule_id: str
    rule_summary: str
    evidence: str
    spec_section: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    confidence: float = 0.5


class ScoredRule(BaseModel):
    rule_id: str
    severity: Severity
    confidence: float
    rationale: str


class Finding(BaseModel):
    severity: Severity
    confidence: float
    rule_id: str
    rule_summary: str
    evidence: str
    recommended_action: str
    impacted_files: List[str] = Field(default_factory=list)
    locations: List[Location] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)


class ReportMeta(BaseModel):
    tool: str = "specguard"
    version: str
    repo: str
    base: str
    head: str
    timestamp: str
    deterministic: bool
    prompt_pack_version: str
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    cache_hit: bool = False


class Report(BaseModel):
    meta: ReportMeta
    findings: List[Finding]
