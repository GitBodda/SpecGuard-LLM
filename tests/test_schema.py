import json
from pathlib import Path

from jsonschema import validate

from specguard.models import Report


def test_report_schema_matches_examples():
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "schemas" / "report.schema.json").read_text(encoding="utf-8"))
    example = json.loads((root / "examples" / "sample_report.json").read_text(encoding="utf-8"))
    validate(instance=example, schema=schema)
    # also validate pydantic parsing
    Report.model_validate(example)
