from __future__ import annotations

import os
import requests
from typing import Optional
from rich.console import Console

console = Console()


def github_api_request(method: str, url: str, token: str, json_body=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    r = requests.request(method, url, headers=headers, json=json_body, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub API error {r.status_code}: {r.text[:400]}")
    return r.json() if r.text else None


def post_pr_comment(repo_slug: str, pr_number: int, body_md: str, token: Optional[str] = None) -> None:
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("Missing GITHUB_TOKEN for GitHub API.")
    url = f"https://api.github.com/repos/{repo_slug}/issues/{pr_number}/comments"
    github_api_request("POST", url, token, json_body={"body": body_md})
    console.print("[green]Posted SpecGuard PR comment.[/green]")


def upsert_check_run(
    repo_slug: str,
    head_sha: str,
    conclusion: str,
    title: str,
    summary: str,
    token: Optional[str] = None,
    details_url: Optional[str] = None,
) -> None:
    """Create a GitHub Check Run. Requires `checks: write` permission.

    Many repos don't grant it by default; posting PR comment is often sufficient.
    """
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("Missing GITHUB_TOKEN for GitHub API.")
    url = f"https://api.github.com/repos/{repo_slug}/check-runs"
    body = {
        "name": "SpecGuard",
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {"title": title, "summary": summary},
    }
    if details_url:
        body["details_url"] = details_url
    github_api_request("POST", url, token, json_body=body)
    console.print("[green]Created SpecGuard check-run.[/green]")
