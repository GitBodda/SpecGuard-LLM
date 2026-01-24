from specguard.utils import extract_md_headers, md_slugify_header

def test_md_slugify():
    assert md_slugify_header("State Transition") == "state-transition"
    assert md_slugify_header("Fork-choice & Safety!") == "fork-choice-safety"

def test_extract_md_headers():
    md = "# Title\n\n## State Transition\nText\n### Block validity\n"
    hs = extract_md_headers(md)
    assert ("State Transition", "state-transition") in hs
    assert ("Block validity", "block-validity") in hs
