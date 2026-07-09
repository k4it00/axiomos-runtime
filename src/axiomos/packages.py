from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import json, shutil, yaml, uuid

from .redaction import redact
from .receipts import make_receipt, write_receipt

MANIFEST_NAMES = ("axiom_package.yaml", "axiom_package.yml", "package.yaml", "package.yml")

@dataclass(frozen=True)
class PackageManifest:
    name: str
    version: str
    description: str
    capabilities: tuple[str, ...]
    commands: tuple[str, ...]
    drivers: tuple[str, ...]
    permissions: tuple[str, ...]
    policies: tuple[str, ...]
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def find_manifest(path: str | Path) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    for name in MANIFEST_NAMES:
        candidate = p / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No package manifest found in {p}")

def load_manifest(path: str | Path) -> PackageManifest:
    manifest_path = find_manifest(path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    required = ("name", "version", "capabilities")
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise ValueError(f"Package manifest missing required fields: {missing}")
    return PackageManifest(
        name=str(data["name"]),
        version=str(data["version"]),
        description=str(data.get("description", "")),
        capabilities=tuple(data.get("capabilities", []) or []),
        commands=tuple(data.get("commands", []) or []),
        drivers=tuple(data.get("drivers", []) or []),
        permissions=tuple(data.get("permissions", []) or []),
        policies=tuple(data.get("policies", []) or []),
        path=str(manifest_path.parent),
    )

class PackageRegistry:
    def __init__(self, workspace: str | Path = "."):
        self.workspace = Path(workspace)
        self.root = self.workspace / ".axiom" / "packages"
        self.root.mkdir(parents=True, exist_ok=True)
        self.receipts = self.workspace / "axiom_runs"
        self.receipts.mkdir(parents=True, exist_ok=True)

    def _package_dir(self, name: str) -> Path:
        return self.root / name

    def install(self, source: str | Path) -> dict[str, Any]:
        manifest = load_manifest(source)
        target = self._package_dir(manifest.name)
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        src = Path(manifest.path or source)
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            shutil.copy2(src, target / src.name)
        installed = load_manifest(target)
        receipt = make_receipt("package_install", "installed", {"action": "package_install", "package": installed.to_dict()}, receipt_id="pkg_" + uuid.uuid4().hex[:10])
        path = write_receipt(receipt, self.workspace)
        return {"package": installed.to_dict(), "receipt_path": str(path)}

    def list(self) -> list[dict[str, Any]]:
        rows = []
        for child in sorted(self.root.iterdir()) if self.root.exists() else []:
            if child.is_dir():
                try:
                    rows.append(load_manifest(child).to_dict())
                except Exception as exc:
                    rows.append({"name": child.name, "error": str(exc)})
        return rows

    def get(self, name: str) -> dict[str, Any]:
        return load_manifest(self._package_dir(name)).to_dict()

    def capabilities(self) -> dict[str, Any]:
        caps: dict[str, list[str]] = {}
        for pkg in self.list():
            for cap in pkg.get("capabilities", []):
                caps.setdefault(cap, []).append(pkg.get("name"))
        return caps

    def doctor(self, name: str | None = None) -> dict[str, Any]:
        packages = [self.get(name)] if name else self.list()
        checks = []
        for pkg in packages:
            if "error" in pkg:
                checks.append({"package": pkg.get("name"), "status": "error", "detail": pkg["error"]})
                continue
            checks.append({"package": pkg["name"], "status": "ok", "detail": f"{len(pkg.get('capabilities', []))} capabilities"})
            if not pkg.get("permissions"):
                checks.append({"package": pkg["name"], "status": "warn", "detail": "no permissions declared"})
            if not pkg.get("policies"):
                checks.append({"package": pkg["name"], "status": "warn", "detail": "no policies declared"})
        return {"status": "ok" if all(c["status"] in {"ok","warn"} for c in checks) else "error", "checks": checks}
