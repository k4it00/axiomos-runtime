from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json, uuid, re

from .redaction import redact_text, redact

MEMORY_TYPES = ("chronicle","episodic","semantic","procedural","project","failure","working","identity")
DURABLE_TYPES = {"semantic", "procedural", "project", "identity"}
DEFAULT_SETTINGS = {
    "enabled": True,
    "save_chronicle": True,
    "save_episodic": True,
    "save_failures": True,
    "attention_limit": 5,
    "compression_chars": 900,
    "index_enabled": True,
}

@dataclass(frozen=True)
class MemoryRecord:
    id: str
    type: str
    content: str
    tags: tuple[str, ...]
    metadata: dict[str, Any]
    created_at: str
    importance: float = 0.5
    def to_dict(self): return asdict(self)

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]{3,}", (text or "").lower()))

def _score_text(query: str, content: str, tags=(), importance=0.5) -> float:
    q = _tokenize(query)
    c = _tokenize(content)
    if not q:
        return 0
    overlap = len(q & c) / max(1, len(q))
    tag_bonus = 0.15 if any(str(t).lower() in query.lower() for t in tags) else 0
    return round(overlap + tag_bonus + float(importance) * 0.1, 4)

class MemoryIndex:
    def __init__(self, workspace="."):
        self.root = Path(workspace) / ".axiom" / "memory"
        self.path = self.root / "index.json"
    def build(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        index = {}
        for rec in records:
            words = sorted(_tokenize(rec.get("content","")) | set(str(t).lower() for t in rec.get("tags", ())))
            for w in words:
                index.setdefault(w, []).append(rec["id"])
        obj = {"built_at": datetime.now(timezone.utc).isoformat(), "terms": index, "record_count": len(records)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        return obj
    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"built_at": None, "terms": {}, "record_count": 0}
        return json.loads(self.path.read_text(encoding="utf-8"))

class MemoryCompressor:
    def __init__(self, max_chars: int = 900):
        self.max_chars = max_chars
    def compress(self, record: dict[str, Any]) -> dict[str, Any]:
        content = record.get("content", "")
        if len(content) <= self.max_chars:
            return record
        out = dict(record)
        out["content"] = content[: self.max_chars].rstrip() + "…"
        out.setdefault("metadata", {})["compressed"] = True
        out["metadata"]["original_chars"] = len(content)
        return out

class AttentionSelector:
    def __init__(self, workspace="."):
        self.workspace = workspace
    def select(self, query: str, records: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
        scored = []
        for rec in records:
            score = _score_text(query, rec.get("content",""), rec.get("tags", ()), rec.get("importance", 0.5))
            if rec.get("type") in {"identity", "project"} and "axiomos" in query.lower():
                score += 0.25
            if score > 0:
                scored.append((score, rec))
        scored.sort(key=lambda x: (x[0], x[1].get("created_at","")), reverse=True)
        return [dict(r, attention_score=s) for s, r in scored[:limit]]

class MemoryConflictDetector:
    NEGATION_PATTERNS = [("is", "is not"), ("uses", "does not use"), ("has", "does not have"), ("can", "cannot")]
    def detect(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        durable = [r for r in records if r.get("type") in DURABLE_TYPES]
        conflicts = []
        for i, a in enumerate(durable):
            ac = a.get("content","").lower()
            for b in durable[i+1:]:
                bc = b.get("content","").lower()
                shared = _tokenize(ac) & _tokenize(bc)
                if len(shared) < 3:
                    continue
                for pos, neg in self.NEGATION_PATTERNS:
                    if (pos in ac and neg in bc) or (neg in ac and pos in bc):
                        conflicts.append({"a": a["id"], "b": b["id"], "reason": "possible_negation_conflict", "shared_terms": sorted(list(shared))[:10]})
                        break
        return conflicts

class WorkingContextBuilder:
    def __init__(self, workspace="."):
        self.workspace = workspace
    def build(self, query: str, records: list[dict[str, Any]], limit: int = 5, max_chars: int = 900) -> dict[str, Any]:
        selected = [MemoryCompressor(max_chars).compress(r) for r in AttentionSelector(self.workspace).select(query, records, limit=limit)]
        return {"query": query, "selected": selected, "count": len(selected)}

class MemoryStore:
    def __init__(self, workspace="."):
        self.workspace = Path(workspace)
        self.root = self.workspace / ".axiom" / "memory"
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.workspace / ".axiom" / "memory_settings.json"
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            self.settings_path.write_text(json.dumps(DEFAULT_SETTINGS, indent=2), encoding="utf-8")
        for t in MEMORY_TYPES:
            (self.root / f"{t}.jsonl").touch(exist_ok=True)
    def settings(self):
        return json.loads(self.settings_path.read_text(encoding="utf-8"))
    def set_setting(self, key, value):
        s = self.settings()
        s[key] = value
        self.settings_path.write_text(json.dumps(s, indent=2), encoding="utf-8")
        return s
    def append(self, memory_type, content, tags=(), metadata=None, importance=0.5):
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unknown memory type: {memory_type}")
        if not self.settings().get("enabled", True):
            return None
        rec = MemoryRecord("mem_" + uuid.uuid4().hex[:12], memory_type, redact_text(str(content)), tuple(tags), redact(metadata or {}), datetime.now(timezone.utc).isoformat(), float(importance))
        with (self.root / f"{memory_type}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        if self.settings().get("index_enabled", True):
            self.rebuild_index()
        return rec
    def list(self, memory_type=None, limit=20):
        files = [self.root / f"{memory_type}.jsonl"] if memory_type else [self.root / f"{t}.jsonl" for t in MEMORY_TYPES]
        rows = []
        for p in files:
            if p.exists():
                rows.extend(json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip())
        return rows[-limit:]
    def all_records(self):
        return self.list(limit=1000000)
    def search(self, query, memory_type=None, limit=20):
        return AttentionSelector(self.workspace).select(query, self.list(memory_type, limit=1000000), limit=limit)
    def attention(self, query, limit=None):
        s = self.settings()
        return WorkingContextBuilder(self.workspace).build(query, self.all_records(), limit=limit or int(s.get("attention_limit", 5)), max_chars=int(s.get("compression_chars", 900)))
    def conflicts(self):
        return MemoryConflictDetector().detect(self.all_records())
    def rebuild_index(self):
        return MemoryIndex(self.workspace).build(self.all_records())
    def export(self, path):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"settings": self.settings(), "records": self.all_records()}, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(target)
    def import_file(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        count = 0
        for rec in data.get("records", []):
            self.append(rec.get("type","episodic"), rec.get("content",""), tuple(rec.get("tags", ())), rec.get("metadata", {}), rec.get("importance", 0.5))
            count += 1
        self.rebuild_index()
        return {"imported": count}
    def stats(self):
        counts = {}
        for t in MEMORY_TYPES:
            p = self.root / f"{t}.jsonl"
            counts[t] = len([x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]) if p.exists() else 0
        index = MemoryIndex(self.workspace).load()
        return {"root": str(self.root), "settings": self.settings(), "counts": counts, "index": {"record_count": index.get("record_count"), "built_at": index.get("built_at")}}
