from __future__ import annotations
from pathlib import Path
from typing import Any
import axiomos

def _root() -> Path:
    return Path(__file__).resolve().parents[2]

def about_payload(workspace=".") -> dict[str, Any]:
    root = _root()
    docs = ["PROJECT_STATUS.md", "ROADMAP.md", "ARCHITECTURE.md", "CONSTITUTION.md", "DESIGN_DECISIONS.md", "HERMES_COMPARISON.md", "CHANGELOG.md"]
    return {
        "name": "AxiomOS Runtime",
        "version": axiomos.__version__,
        "identity": "A cognitive hypervisor runtime for LLMs, tools, agents, memory, packages, loops, providers, and future reasoning engines.",
        "current_release": "1.1.0-dev0",
        "stable_release": "1.0.0",
        "architecture": ["Hypervisor", "Capability Broker", "Memory OS", "Package System", "Tool Driver Layer", "Permission Kernel", "Loop OS", "Receipts"],
        "docs": {doc: str(root / doc) if (root / doc).exists() else None for doc in docs},
        "next": "AxiomOS 1.1 Dev 2 — Hermes-style Shell UX + History + Settings",
    }

def read_doc(name: str) -> str:
    allowed = {
        "status": "PROJECT_STATUS.md",
        "roadmap": "ROADMAP.md",
        "architecture": "ARCHITECTURE.md",
        "constitution": "CONSTITUTION.md",
        "decisions": "DESIGN_DECISIONS.md",
        "hermes": "HERMES_COMPARISON.md",
        "changelog": "CHANGELOG.md",
    }
    key = name.lower()
    if key not in allowed:
        raise KeyError(f"Unknown about doc: {name}")
    return (_root() / allowed[key]).read_text(encoding="utf-8")
