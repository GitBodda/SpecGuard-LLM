from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


def run(cmd: List[str], cwd: Optional[str] = None) -> str:
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


SPEC_EXTENSIONS = {".md", ".rst", ".yaml", ".yml", ".json", ".ssz", ".toml"}
CODE_EXTENSIONS = {".py", ".go", ".rs", ".java", ".kt", ".ts", ".js", ".c", ".cpp", ".h", ".hpp"}
TEST_HINTS = ("test", "tests", "spec_tests", "vectors")


def is_spec_file(p: str) -> bool:
    return Path(p).suffix.lower() in SPEC_EXTENSIONS


def is_code_file(p: str) -> bool:
    return Path(p).suffix.lower() in CODE_EXTENSIONS


def is_test_path(p: str) -> bool:
    low = p.lower()
    return any(h in low.split("/") for h in TEST_HINTS)


SECRET_PATTERNS = [
    # Generic API keys / tokens
    re.compile(r"(?i)(api[_-]?key|secret|token|auth|bearer)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})['\"]?"),
    # OpenAI keys
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    # GitHub tokens
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    # AWS
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # Private key blocks
    re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|PGP) PRIVATE KEY-----[\s\S]+?-----END (?:RSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
]


@dataclass
class RedactionResult:
    redacted_text: str
    redacted_count: int
    redaction_notes: List[str]


def redact(text: str, extra_patterns: Optional[List[str]] = None) -> RedactionResult:
    redacted = text
    count = 0
    notes: List[str] = []

    patterns = list(SECRET_PATTERNS)
    if extra_patterns:
        for p in extra_patterns:
            try:
                patterns.append(re.compile(p))
            except re.error:
                notes.append(f"Ignored invalid extra redaction regex: {p}")

    for pat in patterns:
        def _repl(m):
            nonlocal count
            count += 1
            return "[REDACTED]"
        redacted2, n = pat.subn(_repl, redacted)
        if n > 0:
            notes.append(f"Redacted {n} match(es) for pattern: {pat.pattern[:40]}...")
        redacted = redacted2

    return RedactionResult(redacted_text=redacted, redacted_count=count, redaction_notes=notes)


def git_changed_files(repo: str, base: str, head: str) -> List[str]:
    out = run(["git", "diff", "--name-only", f"{base}..{head}"], cwd=repo)
    return [l.strip() for l in out.splitlines() if l.strip()]


def git_diff(repo: str, base: str, head: str, paths: Optional[List[str]] = None) -> str:
    cmd = ["git", "diff", "--unified=3", f"{base}..{head}"]
    if paths:
        cmd += ["--"] + paths
    return run(cmd, cwd=repo)


def guess_spec_links(repo_slug: Optional[str], spec_section: Optional[str]) -> List[str]:
    if not spec_section:
        return []
    # If spec_section already looks like a URL, keep it
    if spec_section.startswith("http://") or spec_section.startswith("https://"):
        return [spec_section]
    # Otherwise build GitHub link if repo_slug provided
    if repo_slug:
        return [f"https://github.com/{repo_slug}/blob/HEAD/{spec_section}"]
    return [spec_section]


def git_show(repo: str, rev: str, path: str) -> str:
    return run(["git", "show", f"{rev}:{path}"], cwd=repo)


def has_cmd(cmd: str, repo: str) -> bool:
    try:
        run([cmd, "--version"], cwd=repo)
        return True
    except Exception:
        return False


def _rg_hits(repo: str, kw: str, max_hits: int) -> List[Tuple[str, int, str]]:
    try:
        out = run(["rg", "-n", "--no-heading", "--hidden", "--glob", "!.git/*", "--", kw], cwd=repo)
    except Exception:
        return []
    hits: List[Tuple[str,int,str]] = []
    for line in out.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, lno_s, content = parts
        try:
            lno = int(lno_s)
        except ValueError:
            continue
        hits.append((path, lno, content[:200]))
        if len(hits) >= max_hits:
            break
    return hits


def _git_grep_hits(repo: str, kw: str, max_hits: int) -> List[Tuple[str, int, str]]:
    try:
        out = run(["git", "grep", "-n", "--", kw], cwd=repo)
    except Exception:
        return []
    hits: List[Tuple[str,int,str]] = []
    for line in out.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, lno_s, content = parts
        try:
            lno = int(lno_s)
        except ValueError:
            continue
        hits.append((path, lno, content[:200]))
        if len(hits) >= max_hits:
            break
    return hits


def find_keyword_hits(
    repo: str,
    keywords: Iterable[str],
    max_hits: int = 30,
    backend: str = "auto",
) -> List[Tuple[str, int, str]]:
    """Best-effort keyword search.

    backend:
      - auto: prefer ripgrep if available, else git grep
      - rg: force ripgrep
      - git_grep: force git grep
    """
    hits: List[Tuple[str,int,str]] = []
    use_rg = has_cmd("rg", repo) if backend in ("auto", "rg") else False

    for kw in keywords:
        if not kw or len(kw) < 3:
            continue
        if backend == "git_grep":
            new_hits = _git_grep_hits(repo, kw, max_hits=max_hits - len(hits))
        else:
            new_hits = _rg_hits(repo, kw, max_hits=max_hits - len(hits)) if use_rg else _git_grep_hits(repo, kw, max_hits=max_hits - len(hits))
        hits.extend(new_hits)
        if len(hits) >= max_hits:
            break
    return hits


def md_slugify_header(header: str) -> str:
    """GitHub-style-ish anchor slug for markdown headers (best-effort)."""
    h = header.strip().lower()
    h = re.sub(r"[^a-z0-9\s\-]", "", h)
    h = re.sub(r"\s+", "-", h).strip("-")
    return h


def extract_md_headers(md_text: str) -> List[Tuple[str, str]]:
    """Return list of (header_text, anchor)."""
    headers: List[Tuple[str,str]] = []
    for line in md_text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not m:
            continue
        title = m.group(2).strip()
        headers.append((title, md_slugify_header(title)))
    return headers
    return hits
