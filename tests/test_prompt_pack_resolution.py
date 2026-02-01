from pathlib import Path

from specguard.analyze import load_prompt_pack


def test_load_prompt_pack_falls_back_to_tool_repo(tmp_path):
    # tmp_path is a fake target repo without prompts/
    version, _, prompts = load_prompt_pack(Path(tmp_path))
    assert version
    assert isinstance(prompts, dict)
    assert len(prompts) > 0
