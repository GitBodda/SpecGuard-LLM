from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, List

import click
from rich.console import Console
from rich.table import Table

from .analyze import analyze_repo
from .config import load_config
from .models import Report
from .reporting import summarize_report_md
from .utils import load_json, load_text

console = Console()


def _normalize_fail_on(v: str) -> str:
    v = v.strip().lower()
    if v in ("high", "h"):
        return "HIGH"
    if v in ("medium", "med", "m"):
        return "MEDIUM"
    if v in ("low", "l"):
        return "LOW"
    raise click.BadParameter("fail-on must be one of: low|medium|high")


def _exit_code(report: Report, fail_on: str) -> int:
    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    threshold = order[fail_on]
    worst = max([order.get(f.severity, 1) for f in report.findings], default=1)
    return 2 if worst >= threshold else 0


@click.group()
def main() -> None:
    """SpecGuard: LLM-assisted spec drift & compliance checker for Ethereum specs/clients."""
    pass


@main.command()
@click.option("--repo", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--base", required=True, help="Base git ref/SHA (e.g. origin/master or PR base sha).")
@click.option("--head", required=True, help="Head git ref/SHA (e.g. HEAD or PR head sha).")
@click.option("--out", "out_path", required=True, type=click.Path(dir_okay=False))
@click.option("--repo-slug", default=None, help="GitHub repo slug like ethereum/consensus-specs (for links).")
@click.option("--config", "config_path", default=None, help="Path to specguard.yml for advanced settings.")
@click.option("--map-repo", default=None, help="Secondary repo to map rules into (e.g. a client repo checkout).")
@click.option("--search-backend", default="auto", type=click.Choice(["auto","rg","git_grep"]))
@click.option("--max-keyword-hits", default=40, type=int)
@click.option("--no-prefer-tests", is_flag=True, help="Disable test-gap hinting.")
@click.option("--max-findings", default=200, type=int)
@click.option("--deterministic", is_flag=True, help="Force temperature=0 and stable seed when using an LLM.")
@click.option("--cache-dir", default=None, type=click.Path(file_okay=False), help="Enable caching directory.")
@click.option("--extra-redact", multiple=True, help="Additional redaction regex patterns (can repeat).")
def analyze(
    repo: str,
    base: str,
    head: str,
    out_path: str,
    repo_slug: Optional[str],
    config_path: Optional[str],
    map_repo: Optional[str],
    search_backend: str,
    max_keyword_hits: int,
    no_prefer_tests: bool,
    max_findings: int,
    deterministic: bool,
    cache_dir: Optional[str],
    extra_redact: List[str],
) -> None:

    """Analyze base..head diffs and output JSON report."""
    cfg = load_config(config_path)
    effective_repo_slug = repo_slug or cfg.repo_slug
    effective_map_repo = map_repo or cfg.map_repo
    effective_extra_redact = list(cfg.extra_redact) + (list(extra_redact) if extra_redact else [])

    cfg = load_config(config_path)
    effective_map_repo = map_repo or cfg.map_repo

    report = analyze_repo(
        repo=repo,
        base=base,
        head=head,
        out_path=Path(out_path),
        deterministic=deterministic,
        cache_dir=(Path(cache_dir) if cache_dir else None),
        repo_slug=repo_slug,
        map_repo=effective_map_repo,
        search_backend=search_backend or cfg.search_backend,
        max_keyword_hits=max_keyword_hits or cfg.max_keyword_hits,
        prefer_tests=(not no_prefer_tests) and cfg.prefer_tests,
        max_findings=max_findings or cfg.max_findings,
        schema_path=Path(__file__).resolve().parents[3] / "schemas" / "report.schema.json",
    )
    md = summarize_report_md(report)

    if comment:
        from .github import post_pr_comment
        post_pr_comment(repo_slug=repo_slug, pr_number=pr_number, body_md=md)

    if check_run:
        from .github import upsert_check_run
        # conclusion derived from fail status
        conclusion = "failure" if _exit_code(report, fail_on) != 0 else "success"
        upsert_check_run(
            repo_slug=repo_slug,
            head_sha=head,
            conclusion=conclusion,
            title="SpecGuard LLM",
            summary=md[:65000],
        )

    code = _exit_code(report, fail_on)
    if code != 0:
        raise SystemExit(code)
