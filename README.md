    # SpecGuard LLM

    **SpecGuard LLM** is an LLM-assisted **spec drift & compliance checker** for Ethereum specs/clients.
    It runs in **CI** on pull requests, analyzes the **diff range**, extracts affected **protocol rules/assertions** from spec changes,
    maps them to **impacted code/tests**, and posts **structured findings** back to GitHub PRs.

    This project is designed to match the Ethereum Foundation ESP RFP: *“Integrating LLMs into Ethereum Protocol Security Research”*.

    ## Why this is useful for protocol security work

    Spec diffs (EIPs, consensus-specs, execution-specs) often introduce subtle normative changes (MUST/SHALL/SHOULD)
    that can silently drift from client behavior. SpecGuard turns spec PRs into a **review checklist**:
    - What rules changed?
    - Where do we expect code or tests to reflect them?
    - What’s missing or inconsistent?

    ## Supported repos (demo targets)

    - `ethereum/consensus-specs`
    - `ethereum/execution-specs`

    SpecGuard works best when run *inside* a checked-out repo (spec repo or client repo) so it can `git diff` and search files.

    ## High-level architecture

    ```mermaid
    flowchart LR
      A[Git diff base..head] --> B[Diff normalizer + Redaction]
      B --> C[Spec file filter (.md/.rst/.yaml/.json)]
      C --> D[LLM Rule Extractor
(prompts/rule_extraction.md)]
      D --> E[Rule Assertions
(structured)]
      E --> F[Heuristic Mapper
(ripgrep-like search)]
      F --> G[Findings Builder
(severity/confidence)]
      G --> H[JSON Report + Markdown Summary]
      H --> I[GitHub Action
comment/check + artifact]
      H --> J[Local CLI output]
      D --> K[Cache
(hash(input+prompt))]
    ```

    ## Quick start (local)

    Requirements: Python 3.10+

    ```bash
    git clone https://github.com/<you>/specguard-llm
    cd specguard-llm
    pip install -e ".[dev]"
    ```

    Run against a repo checkout (example: consensus-specs):

    ```bash
    git clone https://github.com/ethereum/consensus-specs
    cd consensus-specs

    # Compare base..head (replace SHAs or refs)
    specguard analyze --repo . --base origin/master --head HEAD --out specguard.json
    ```

    Produce a human summary:

    ```bash
    specguard summarize --input specguard.json
    ```

    ### LLM configuration (OpenAI-compatible)

    SpecGuard defaults to **local/no-LLM mode** (safe for private repos). Enable LLM explicitly:

    ```bash
    export SPEC_GUARD_LLM_PROVIDER=openai
    export SPEC_GUARD_OPENAI_BASE_URL=https://api.openai.com/v1
    export SPEC_GUARD_OPENAI_API_KEY=...   # or via GitHub Secrets in CI
    export SPEC_GUARD_OPENAI_MODEL=gpt-4o-mini
    ```

    Deterministic mode:

    ```bash
    specguard analyze --deterministic --cache-dir .specguard/cache
    ```

    ## GitHub Action usage

    In your target repo, add:

    `.github/workflows/specguard.yml`:

    ```yaml
    name: SpecGuard
    on:
      pull_request:
        types: [opened, synchronize, reopened]
    permissions:
      contents: read
      pull-requests: write
    jobs:
      specguard:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
            with:
              fetch-depth: 0

          - uses: actions/setup-python@v5
            with:
              python-version: "3.11"

          - name: Install SpecGuard
            run: |
              pip install specguard

          - name: Run SpecGuard
            env:
              GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
              SPEC_GUARD_LLM_PROVIDER: openai
              SPEC_GUARD_OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
              SPEC_GUARD_OPENAI_MODEL: gpt-4o-mini
              SPEC_GUARD_OPENAI_BASE_URL: https://api.openai.com/v1
            run: |
              specguard github-action                 --repo .                 --base "${{ github.event.pull_request.base.sha }}"                 --head "${{ github.event.pull_request.head.sha }}"                 --pr-number "${{ github.event.pull_request.number }}"                 --repo-slug "${{ github.repository }}"                 --fail-on high                 --out specguard.json

          - name: Upload SpecGuard artifact
            uses: actions/upload-artifact@v4
            with:
              name: specguard-report
              path: specguard.json
    ```

    CI will **fail only for HIGH** severity findings (configurable with `--fail-on`).

    ## Output schema (JSON)

    SpecGuard writes a single JSON report with:
    - `meta`: run metadata (repo, base/head, prompt versions, deterministic flag)
    - `findings[]`: list of issues (severity/confidence/evidence/actions/links/locations)

    Schema is in `schemas/report.schema.json`.

    ## Next-level mode (multi-repo mapping + better spec links)

SpecGuard can map spec rules into a **second repository** (e.g. an Ethereum client checkout) to highlight
where the client might need updates/tests.

### Example: map consensus-specs PR rules into a client repo

```bash
cd consensus-specs
export CLIENT_REPO=/path/to/lighthouse   # or geth/nethermind/prysm/teku...

specguard analyze   --repo .   --base origin/master   --head HEAD   --map-repo "$CLIENT_REPO"   --repo-slug ethereum/consensus-specs   --search-backend auto   --deterministic   --cache-dir .specguard/cache   --out specguard.json
```

### Config file (specguard.yml)

```yaml
repo_slug: ethereum/consensus-specs
map_repo: /path/to/client
extra_redact:
  - "(?i)INFURA_[A-Z0-9_]{10,}"
search_backend: auto
max_keyword_hits: 60
prefer_tests: true
max_findings: 200
```

Then run:

```bash
specguard analyze --repo . --base <base> --head <head> --config specguard.yml --out specguard.json
```

### Better spec links (file + header anchors)

If the LLM returns `spec_section` as a markdown file path (e.g. `specs/phase0/beacon-chain.md`),
SpecGuard will try to choose the best matching header anchor and create a stable link:

`https://github.com/<repo>/blob/<head>/<file>#<anchor>`

## Prompts


    All prompts are versioned and editable under `prompts/`.
    - `prompts/rule_extraction.md`
    - `prompts/severity_scoring.md`

    Prompt pack structure:
    ```
    prompts/
      pack.yaml
      rule_extraction.md
      severity_scoring.md
    ```

    ## Security notes

    - **No external calls by default.** LLM usage requires explicit configuration.
    - Diff content is passed through a **redaction layer** to strip likely secrets/tokens.
    - Supports **local execution** and an LLM provider interface with a placeholder for local models.

    ## Development

    ```bash
    pip install -e ".[dev]"
    pytest -q
    ```

    ## Example outputs

    See `examples/`:
    - `examples/sample_report.json`
    - `examples/sample_comment.md` (PR comment content)

    ## License

    MIT
