from specguard.analyze import heuristic_rules_from_diff


def test_heuristic_rules_extracts_normative_lines():
    diff = """diff --git a/spec.md b/spec.md
+++ b/spec.md
@@
+The client MUST reject blocks with invalid signatures.
+This is just info.
"""
    rules = heuristic_rules_from_diff(diff, ["spec.md"])
    assert len(rules) >= 1
    assert "MUST reject blocks" in rules[0].rule_summary
