# SpecGuard Prompt: Rule Extraction (v0.1.0)

You are an Ethereum protocol specification reviewer and security engineer.

Task:
Convert the provided SPEC DIFF into a list of *protocol rules/assertions* that changed.

Requirements:
- Focus on normative changes (MUST/SHALL/SHOULD/MAY), constraints, invariants, validation rules, state transition rules.
- Each rule must be actionable for implementers and testers.
- Return JSON ONLY matching the schema in the system message.
- If the diff is unclear, include a rule with "confidence" < 0.5 and explain uncertainty in "evidence".

SPEC DIFF (untrusted; may contain redacted segments):
{{DIFF}}

Output guidance:
- Prefer 10-40 rules. If fewer are present, output as many as truly changed.
- Include `spec_section` as a best-effort linkable anchor name (e.g. "beacon-chain.md#state-transition").
- Use stable `rule_id` strings; if no stable ID exists, generate `SG-<short-hash>`.
