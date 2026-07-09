from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import json, uuid

from .redaction import redact

REQUIRED_RECEIPT_FIELDS = ("receipt_id", "type", "status", "created_at")

def make_receipt(receipt_type: str, status: str, payload: dict[str, Any] | None = None, receipt_id: str | None = None) -> dict[str, Any]:
    return redact({
        "receipt_id": receipt_id or f"{receipt_type}_{uuid.uuid4().hex[:10]}",
        "type": receipt_type,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **(payload or {}),
    })

def validate_receipt_schema(receipt: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_RECEIPT_FIELDS if field not in receipt]

def write_receipt(receipt: dict[str, Any], workspace=".") -> Path:
    missing = validate_receipt_schema(receipt)
    if missing:
        raise ValueError(f"Receipt missing fields: {missing}")
    out = Path(workspace) / "axiom_runs"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{receipt['receipt_id']}.json"
    path.write_text(json.dumps(redact(receipt), indent=2), encoding="utf-8")
    return path

def list_receipts(workspace="."):
    p = Path(workspace) / "axiom_runs"
    p.mkdir(parents=True, exist_ok=True)
    return sorted(str(x) for x in p.glob("*.json"))

def show_receipt(ref, workspace="."):
    p = Path(ref)
    if not p.exists():
        p = Path(workspace) / "axiom_runs" / (ref if str(ref).endswith(".json") else str(ref) + ".json")
    receipt = json.loads(p.read_text(encoding="utf-8"))
    missing = validate_receipt_schema(receipt)
    if missing:
        receipt["_schema_warnings"] = {"missing": missing}
    return receipt
