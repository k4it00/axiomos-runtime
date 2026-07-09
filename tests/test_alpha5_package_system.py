from pathlib import Path
from axiomos.packages import load_manifest, PackageRegistry
from axiomos.doctor import run_doctor

def test_load_manifest(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "axiom_package.yaml").write_text('name: demo\nversion: 0.1.0\ncapabilities: [demo_cap]\npermissions: [filesystem]\npolicies: [safe]\n', encoding='utf-8')
    manifest = load_manifest(pkg)
    assert manifest.name == "demo"
    assert "demo_cap" in manifest.capabilities

def test_install_list_show_doctor(tmp_path):
    src = tmp_path / "srcpkg"
    src.mkdir()
    (src / "axiom_package.yaml").write_text('name: demo\nversion: 0.1.0\ndescription: Demo\ncapabilities: [demo_cap]\ncommands: [demo.run]\ndrivers: [dry_run]\npermissions: [filesystem]\npolicies: [safe]\n', encoding='utf-8')
    reg = PackageRegistry(tmp_path)
    installed = reg.install(src)
    assert installed["package"]["name"] == "demo"
    assert reg.list()[0]["name"] == "demo"
    assert reg.get("demo")["version"] == "0.1.0"
    assert "demo_cap" in reg.capabilities()
    assert reg.doctor("demo")["status"] == "ok"

def test_doctor_includes_packages(tmp_path):
    assert run_doctor(tmp_path)["status"] == "ok"
