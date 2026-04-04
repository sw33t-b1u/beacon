"""Generate JSON Schema files from Pydantic models.

Run once to produce schema/*.schema.json:
  uv run python cmd/generate_schemas.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent.parent / "schema"


def main() -> int:
    SCHEMA_DIR.mkdir(exist_ok=True)

    # PIR output schema
    from beacon.generator.pir_builder import PIROutput

    pir_schema = PIROutput.model_json_schema()
    _write(SCHEMA_DIR / "pir_output.schema.json", pir_schema)

    # BusinessContext input schema
    from beacon.ingest.schema import BusinessContext

    bc_schema = BusinessContext.model_json_schema()
    _write(SCHEMA_DIR / "business_context.schema.json", bc_schema)

    return 0


def _write(path: Path, schema: dict) -> None:
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written: {path}")


if __name__ == "__main__":
    sys.exit(main())
