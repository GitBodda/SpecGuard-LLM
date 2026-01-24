from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import yaml

from .config import SpecGuardConfig
from jsonschema import validate as jsonschema_validate
from rich.console import Console

from .cache import cache_key, try_load, store
from .llm import make_client
from .models import ExtractedRule, Finding, Location, Report, ReportMeta, ScoredRule
from .utils import (
    git_changed_files,
    git_diff,
    guess_spec_links,
    is_code_file,
    is_spec_file,
    is_test_path,
    load_text,
    redact,
    find_keyword_hits,
    git_show,
    extract_md_headers,
    write_json,
    sha256_text,
)

console = Console()


def load_prompt_pack(root: Path) -> tuple[str, dict, dict]:
    pack_path = root / "prompts" / "pack.yaml"
    pack = yaml.safe_load(load_text(pack_path))
    version = str(pack.get("version", "0.0.0"))
    prompts = {}
    for key, fname in pack.get("prompts", {}).items():
        prompts[key] = load_text(root / "prompts" / fname)
    return version, pack, prompts


def llm_extract_rules(
    diff_text: str,
    prompts: dict,
    deterministic: bool,
    cache_dir: Optional[Path],
    prompt_pack_version: str,
    llm_model: Optional[str],
) -> tuple[List[ExtractedRule], bool]:
    """Return rules and whether it was cache hit."""
    prompt = prompts["rule_extraction"]
    user = prompt.replace("{{DIFF}}", diff_text)

    # JSON schema for the model
    system = (
        "You MUST return JSON with this schema: "
        "{rules: [{rule_id: string, rule_summary: string, evidence: string, "
        "spec_section: string|null, keywords: string[], confidence: number}]}"
    )

    client, cfg = make_client(deterministic=deterministic)
    if client is None:
        return [], False

    cache_hit = False
    cache_obj = None
    key = None
    if cache_dir:
        key = cache_key(prompt_pack_version, prompt, diff_text, cfg.model if cfg else llm_model)
        res, cache_obj = try_load(cache_dir, key)
        cache_hit = res.hit

    if cache_obj is None:
        raw = client.complete_json(system=system, user=user)
        try:
            cache_obj = json.loads(raw)
        except json.JSONDecodeError:
            # best-effort: wrap
            cache_obj = {"rules": [], "raw": raw}

        if cache_dir and key:
            store(cache_dir, key, cache_obj)

    rules = []
    for r in cache_obj.get("rules", []):
        try:
            rules.append(ExtractedRule.model_validate(r))
        except Exception:
            continue
    return rules, cache_hit


def llm_score_severity(
    rules: List[ExtractedRule],
    prompts: dict,
    deterministic: bool,
    cache_dir: Optional[Path],
    prompt_pack_version: str,
    llm_model: Optional[str],
) -> tuple[List[ScoredRule], bool]:
    client, cfg = make_client(deterministic=deterministic)
    if client is None:
        return [], False

    prompt = prompts["severity_scoring"]
    input_obj = {"rules": [r.model_dump() for r in rules]}
    user = prompt + "\n\nINPUT:\n" + json.dumps(input_obj, ensure_ascii=False)
    system = (
        "Return JSON with schema: {scores: [{rule_id: string, severity: 'LOW'|'MEDIUM'|'HIGH', "
        "confidence: number, rationale: string}]}"
    )

    cache_hit = False
    cache_obj = None
    key = None
    if cache_dir:
        key = cache_key(prompt_pack_version, prompt, json.dumps(input_obj, ensure_ascii=False), cfg.model if cfg else llm_model)
        res, cache_obj = try_load(cache_dir, key)
        cache_hit = res.hit

    if cache_obj is None:
        raw = client.complete_json(system=system, user=user)
        try:
            cache_obj = json.loads(raw)
        except json.JSONDecodeError:
            cache_obj = {"scores": [], "raw": raw}
        if cache_dir and key:
            store(cache_dir, key, cache_obj)

    scores = []
    for s in cache_obj.get("scores", []):
        try:
            scores.append(ScoredRule.model_validate(s))
        except Exception:
            continue
    return scores, cache_hit


def _extract_search_terms(rule_summary: str, keywords: List[str]) -> List[str]:
    backticked = re.findall(r"`([^`]{3,64})`", rule_summary)
    upper_consts = re.findall(r"\b[A-Z0-9_]{4,}\b", rule_summary)
    base = list(dict.fromkeys([*backticked, *upper_consts, *(keywords or [])]))
    for t in rule_summary.split():
        t = t.strip(" ,.;:()[]{}<>\"'")
        if 3 <= len(t) <= 32 and t.isascii():
            base.append(t)
        if len(base) >= 18:
            break
    seen=set()
    out=[]
    for t in base:
        tl=t.lower()
        if tl in seen:
            continue
        seen.add(tl)
        out.append(t)
    return out[:20]


def _best_header_anchor(md_text: str, rule_summary: str) -> str | None:
    headers = extract_md_headers(md_text)
    if not headers:
        return None
    tokens = {t.lower().strip(" ,.;:()[]{}") for t in rule_summary.split() if len(t) >= 4}
    best = None
    best_score = 0
    for title, anchor in headers:
        htoks = {t.lower().strip(" ,.;:()[]{}") for t in title.split() if len(t) >= 4}
        score = len(tokens & htoks)
        if score > best_score:
            best_score = score
            best = anchor
    return best if best_score > 0 else None


def _build_spec_link(repo_slug: str | None, head: str, spec_path: str | None, md_anchor: str | None) -> List[str]:
    if not spec_path:
        return []
    if spec_path.startswith("http://") or spec_path.startswith("https://"):
        return [spec_path]
    if repo_slug:
        url = f"https://github.com/{repo_slug}/blob/{head}/{spec_path}"
        if md_anchor:
            url += f"#{md_anchor}"
        return [url]
    if md_anchor:
        return [f"{spec_path}#{md_anchor}"]
    return [spec_path]


def heuristic_findings(
    repo: str,
    rules: List[ExtractedRule],
    scores: List[ScoredRule],
    repo_slug: Optional[str],
    head: str,
    map_repo: Optional[str] = None,
    search_backend: str = "auto",
    max_keyword_hits: int = 40,
    prefer_tests: bool = True,
) -> List[Finding]:
    score_by_id = {s.rule_id: s for s in scores}
    findings: List[Finding] = []

    for r in rules:
        s = score_by_id.get(r.rule_id)
        severity = s.severity if s else ("MEDIUM" if r.confidence >= 0.7 else "LOW")
        confidence = min(1.0, max(0.0, (s.confidence if s else r.confidence)))

        terms = _extract_search_terms(r.rule_summary, r.keywords)

        hits = find_keyword_hits(repo, terms, max_hits=max_keyword_hits, backend=search_backend)
        map_hits = []
        if map_repo and Path(map_repo).exists():
            map_hits = find_keyword_hits(map_repo, terms, max_hits=max_keyword_hits, backend=search_backend)

        impacted = []
        locations: List[Location] = []

        def add_hits(hs, prefix=""):
            for path, lno, _ in hs:
                shown = f"{prefix}{path}" if prefix else path
                impacted.append(shown)
                kind = "test" if is_test_path(path) else ("code" if is_code_file(path) else "spec")
                locations.append(Location(path=shown, start_line=lno, end_line=lno, kind=kind))

        add_hits(hits)
        if map_hits:
            add_hits(map_hits, prefix="(map_repo)/")

        md_anchor = None
        spec_path = r.spec_section
        if spec_path and repo_slug and spec_path.endswith(".md"):
            try:
                md_text = git_show(repo, head, spec_path)
                md_anchor = _best_header_anchor(md_text, r.rule_summary)
            except Exception:
                md_anchor = None

        links = _build_spec_link(repo_slug, head, spec_path, md_anchor) if repo_slug else guess_spec_links(repo_slug, spec_path)

        has_test = any(loc.kind == "test" for loc in locations)
        if (severity == "HIGH") and (not has_test) and prefer_tests:
            recommended = (
                "Consensus-critical change: verify implementation AND add/extend tests/spec vectors. "
                "No obvious test hits were found by keyword search—consider adding new tests."
            )
            confidence = max(0.0, confidence - 0.05)
        else:
            if not impacted:
                recommended = (
                    "Search client/reference-impl code for this rule and add/adjust validation. "
                    "Add or update tests covering the changed behavior."
                )
            else:
                recommended = (
                    "Review impacted code locations to ensure they implement the updated rule. "
                    "Add/extend tests (unit/spec vectors) to assert the new behavior."
                )

        evidence = r.evidence
        if s and s.rationale:
            evidence = evidence.strip() + "\n\nRisk rationale: " + s.rationale.strip()

        findings.append(Finding(
            severity=severity,
            confidence=confidence,
            rule_id=r.rule_id,
            rule_summary=r.rule_summary,
            evidence=evidence,
            recommended_action=recommended,
            impacted_files=sorted(list(set(impacted)))[:50],
            locations=locations[:50],
            links=links,
        ))
    return findings


def analyze_repo(
    repo: str,
    base: str,
    head: str,
    out_path: Path,
    deterministic: bool = False,
    cache_dir: Optional[Path] = None,
    repo_slug: Optional[str] = None,
    extra_redaction_regex: Optional[List[str]] = None,
    schema_path: Optional[Path] = None,
    map_repo: Optional[str] = None,
    search_backend: str = "auto",
    max_keyword_hits: int = 40,
    prefer_tests: bool = True,
    max_findings: int = 200,
) -> Report:

    root = Path(__file__).resolve().parents[3]  # repo root
    prompt_pack_version, _, prompts = load_prompt_pack(root)

    changed = git_changed_files(repo, base, head)
    spec_files = [p for p in changed if is_spec_file(p)]
    code_files = [p for p in changed if is_code_file(p)]

    # Always analyze spec changes if present; if none, still analyze the whole diff but mark.
    paths = spec_files if spec_files else None
    diff = git_diff(repo, base, head, paths=paths)

    # Redaction
    red = redact(diff, extra_patterns=extra_redaction_regex)
    safe_diff = red.redacted_text

    # LLM extraction
    rules, extract_cache_hit = llm_extract_rules(
        diff_text=safe_diff,
        prompts=prompts,
        deterministic=deterministic,
        cache_dir=cache_dir,
        prompt_pack_version=prompt_pack_version,
        llm_model=None,
    )

    # If LLM disabled or no rules extracted, do a small heuristic extraction to remain usable.
    if not rules:
        rules = heuristic_rules_from_diff(safe_diff, spec_files or changed)

    # LLM severity scoring
    scores, score_cache_hit = llm_score_severity(
        rules=rules,
        prompts=prompts,
        deterministic=deterministic,
        cache_dir=cache_dir,
        prompt_pack_version=prompt_pack_version,
        llm_model=None,
    )

    findings = heuristic_findings(
        repo,
        rules,
        scores,
        repo_slug=repo_slug,
        head=head,
        map_repo=map_repo,
        search_backend=search_backend,
        max_keyword_hits=max_keyword_hits,
        prefer_tests=prefer_tests,
    )

    findings = findings[:max_findings]

    # Build meta
    client, cfg = make_client(deterministic=deterministic)
    meta = ReportMeta(
        version="0.2.0",
        repo=str(Path(repo).resolve()),
        base=base,
        head=head,
        timestamp=datetime.now(timezone.utc).isoformat(),
        deterministic=deterministic,
        prompt_pack_version=prompt_pack_version,
        llm_provider=(cfg.provider if cfg else None),
        model=(cfg.model if cfg else None),
        cache_hit=bool(extract_cache_hit or score_cache_hit),
    )
    report = Report(meta=meta, findings=findings)

    obj = report.model_dump()
    write_json(out_path, obj)

    # Validate schema if provided
    if schema_path:
        schema = json.loads(load_text(schema_path))
        jsonschema_validate(instance=obj, schema=schema)

    return report


def heuristic_rules_from_diff(diff_text: str, files: List[str]) -> List[ExtractedRule]:
    """Fallback: extract up to ~10 rules from added lines containing normative keywords."""
    rules: List[ExtractedRule] = []
    normative = ("MUST", "SHALL", "SHOULD", "MAY", "MUST NOT", "SHALL NOT", "REQUIRED")
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            if any(k in line for k in normative) and len(line) > 10:
                summary = line[1:].strip()
                rid = "SG-" + sha256_text(summary)[:8]
                rules.append(ExtractedRule(
                    rule_id=rid,
                    rule_summary=summary[:200],
                    evidence="Heuristic extraction from added normative line in diff.",
                    spec_section=(files[0] if files else None),
                    keywords=[w.strip(" ,.;:()[]{}").lower() for w in summary.split()[:8]],
                    confidence=0.55,
                ))
        if len(rules) >= 10:
            break
    return rules
