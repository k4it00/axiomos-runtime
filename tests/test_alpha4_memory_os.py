from pathlib import Path
from axiomos.memory import MemoryStore
from axiomos.hypervisor import run_prompt
from axiomos.doctor import run_doctor

def test_memory_index_attention(tmp_path):
    store = MemoryStore(tmp_path)
    store.append("identity", "AxiomOS is a cognitive hypervisor runtime.", ("axiomos", "identity"), importance=1.0)
    store.append("episodic", "Cloudflare provider executed a real inference.", ("provider",), importance=0.7)
    index = store.rebuild_index()
    assert index["record_count"] >= 2
    attention = store.attention("What is AxiomOS?")
    assert attention["selected"]
    assert "AxiomOS" in attention["selected"][0]["content"]

def test_memory_redacts_secrets(tmp_path):
    store = MemoryStore(tmp_path)
    store.append("chronicle", "token cfut_abcdefghijklmnopqrstuvwxyz123456", ("secret",))
    rows = store.list("chronicle")
    assert "cfut_" not in rows[-1]["content"]

def test_memory_export_import(tmp_path):
    store = MemoryStore(tmp_path)
    store.append("semantic", "AxiomOS uses receipts.", ("axiomos",))
    exported = store.export(tmp_path / "export.json")
    new = MemoryStore(tmp_path / "new")
    result = new.import_file(exported)
    assert result["imported"] >= 1
    assert new.search("receipts")

def test_conflict_detector(tmp_path):
    store = MemoryStore(tmp_path)
    store.append("semantic", "AxiomOS is a cognitive hypervisor with memory manager.", ("axiomos",))
    store.append("semantic", "AxiomOS is not a cognitive hypervisor with memory manager.", ("axiomos",))
    assert store.conflicts()

def test_hypervisor_uses_attention_context(tmp_path):
    store = MemoryStore(tmp_path)
    store.append("identity", "AxiomOS is a cognitive hypervisor runtime.", ("axiomos",), importance=1.0)
    result = run_prompt("Explain AxiomOS in one sentence.", workspace=tmp_path, dry_run=True)
    context = result["driver_request"]["metadata"]["memory_context"]
    assert context
    assert run_doctor(tmp_path)["status"] == "ok"
