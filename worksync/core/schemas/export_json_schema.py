"""Exports each pydantic model in models.py to a JSON Schema file next to it.

Run with: python -m worksync.core.schemas.export_json_schema
"""

import json
from pathlib import Path

from worksync.core.schemas.models import (
    AuditEntry,
    CaseRecord,
    ComplianceFlags,
    Decision,
    Envelope,
    RiskOutput,
)

OUTPUT_DIR = Path(__file__).parent
MODELS = {
    "case_record": CaseRecord,
    "risk_output": RiskOutput,
    "compliance_flags": ComplianceFlags,
    "decision": Decision,
    "audit_entry": AuditEntry,
    "envelope": Envelope,
}


def main() -> None:
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        out_path = OUTPUT_DIR / f"{name}.schema.json"
        out_path.write_text(json.dumps(schema, indent=2) + "\n")
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
