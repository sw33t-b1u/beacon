"""Generate JSON Schema files from Pydantic models.

Run once to produce schema/*.schema.json:
  uv run python cmd/generate_schemas.py
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent.parent / "schema"


def main() -> int:
    SCHEMA_DIR.mkdir(exist_ok=True)

    # PIR output schema — generated from the document envelope (BEACON 0.16.0+)
    from beacon.generator.pir_builder import PIROutputDocument

    pir_schema = PIROutputDocument.model_json_schema()
    _write(SCHEMA_DIR / "pir_output.schema.json", pir_schema)

    # BusinessContext input schema
    from beacon.ingest.schema import BusinessContext

    bc_schema = BusinessContext.model_json_schema()
    _write(SCHEMA_DIR / "business_context.schema.json", bc_schema)

    return 0


def _write(path: Path, schema: dict) -> None:
    # sort_keys=True ensures byte-identical output across runs (idempotent).
    content = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")
    print(f"Written: {path}")
