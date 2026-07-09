import argparse, json, sys
import axiomos

from .parser import parse_ax_file
from .validator import validate_document, has_errors
from .axiom_ir import emit_ir
from .graph import build_graph
from .planner import create_plan
from .loop_runtime import list_loops, compile_loops, run_loops_file
from .loop_os import LoopOS
from .doctor import run_doctor
from .memory import MemoryStore
from .drivers import DriverRegistry
from .provider_config import provider_status, set_active_provider, add_cloudflare_provider
from .receipts import list_receipts, show_receipt
from .shell import run_shell, run_one_shot
from .packages import PackageRegistry
from .tools import ToolRequest, execute_tool, ToolRegistry, parse_tool_name, tool_doctor
from .permissions import permission_catalog
from .package_tool_bridge import package_tool_needs, run_package_doctor_tools
from .router import route_prompt
from .capability_broker import explain_broker
from .config import ensure_home, load_config, save_config, get_key, set_key, config_status
from .setup import run_setup, setup_cloudflare_provider, setup_memory, setup_permissions
from .about import about_payload, read_doc

def pj(o):
    print(json.dumps(o, indent=2))

def main(argv=None):
    p = argparse.ArgumentParser(prog="axiom", description="AxiomOS Runtime 1.1 Dev")
    p.add_argument("--version", action="store_true")
    p.add_argument("-q", "--query")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--progress", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("version")
    about = sub.add_parser("about"); about.add_argument("doc", nargs="?")

    setup = sub.add_parser("setup")
    setup.add_argument("--dry-run", action="store_true")
    setup.add_argument("--home")
    setup.add_argument("--profile", default="safe")
    setup_sub = setup.add_subparsers(dest="setup_cmd")
    sp = setup_sub.add_parser("provider"); sp.add_argument("kind"); sp.add_argument("name"); sp.add_argument("--account-env", required=True); sp.add_argument("--token-env", required=True); sp.add_argument("--workspace", default="."); sp.add_argument("--home"); sp.add_argument("--dry-run", action="store_true")
    sp = setup_sub.add_parser("memory"); sp.add_argument("--workspace", default="."); sp.add_argument("--home"); sp.add_argument("--enabled", default="true"); sp.add_argument("--attention-limit", type=int, default=5); sp.add_argument("--compression-chars", type=int, default=900); sp.add_argument("--dry-run", action="store_true")
    sp = setup_sub.add_parser("permissions"); sp.add_argument("--profile", default="safe"); sp.add_argument("--home"); sp.add_argument("--dry-run", action="store_true")

    config = sub.add_parser("config")
    cfg = config.add_subparsers(dest="config_cmd", required=True)
    sp = cfg.add_parser("init"); sp.add_argument("--home")
    sp = cfg.add_parser("path"); sp.add_argument("--home")
    sp = cfg.add_parser("list"); sp.add_argument("--home")
    sp = cfg.add_parser("get"); sp.add_argument("key"); sp.add_argument("--home")
    sp = cfg.add_parser("set"); sp.add_argument("key"); sp.add_argument("value"); sp.add_argument("--home")

    for name in ("parse", "validate", "ir", "graph", "plan", "run", "compile"):
        sp = sub.add_parser(name)
        sp.add_argument("file")
        if name in {"validate", "ir"}:
            sp.add_argument("--strict", action="store_true")
        if name == "run":
            sp.add_argument("--dry-run", action="store_true", default=True)

    loop = sub.add_parser("loop"); ls = loop.add_subparsers(dest="loop_cmd", required=True)
    sp = ls.add_parser("list"); sp.add_argument("file")
    sp = ls.add_parser("compile"); sp.add_argument("file"); sp.add_argument("--output", default="compiled_loops")
    sp = ls.add_parser("run"); sp.add_argument("file"); sp.add_argument("--workspace", default="."); sp.add_argument("--dry-run", action="store_true", default=True)

    loopos = sub.add_parser("loop-os"); los = loopos.add_subparsers(dest="loop_os_cmd", required=True)
    sp = los.add_parser("run"); sp.add_argument("file"); sp.add_argument("--workspace", default="."); sp.add_argument("--dry-run", action="store_true", default=True); sp.add_argument("--name")

    doc = sub.add_parser("doctor"); doc.add_argument("--workspace", default=".")

    prov = sub.add_parser("providers"); ps = prov.add_subparsers(dest="providers_cmd", required=True); sp = ps.add_parser("list"); sp.add_argument("--workspace", default=".")
    model = sub.add_parser("model"); ms = model.add_subparsers(dest="model_cmd", required=True)
    sp = ms.add_parser("list"); sp.add_argument("--workspace", default=".")
    sp = ms.add_parser("set"); sp.add_argument("name"); sp.add_argument("--workspace", default=".")
    sp = ms.add_parser("add"); sp.add_argument("kind"); sp.add_argument("name"); sp.add_argument("--account-env", required=True); sp.add_argument("--token-env", required=True); sp.add_argument("--workspace", default=".")

    mem = sub.add_parser("memory"); mm = mem.add_subparsers(dest="memory_cmd", required=True)
    sp = mm.add_parser("stats"); sp.add_argument("--workspace", default=".")
    sp = mm.add_parser("list"); sp.add_argument("--type"); sp.add_argument("--workspace", default=".")
    sp = mm.add_parser("search"); sp.add_argument("query"); sp.add_argument("--workspace", default=".")
    sp = mm.add_parser("attention"); sp.add_argument("query"); sp.add_argument("--workspace", default=".")
    sp = mm.add_parser("conflicts"); sp.add_argument("--workspace", default=".")
    sp = mm.add_parser("export"); sp.add_argument("path"); sp.add_argument("--workspace", default=".")
    sp = mm.add_parser("import"); sp.add_argument("path"); sp.add_argument("--workspace", default=".")
    sp = mm.add_parser("rebuild-index"); sp.add_argument("--workspace", default=".")

    rec = sub.add_parser("receipt"); rr = rec.add_subparsers(dest="receipt_cmd", required=True)
    sp = rr.add_parser("list"); sp.add_argument("--workspace", default=".")
    sp = rr.add_parser("show"); sp.add_argument("ref"); sp.add_argument("--workspace", default=".")

    package = sub.add_parser("package"); pk = package.add_subparsers(dest="package_cmd", required=True)
    sp = pk.add_parser("install"); sp.add_argument("path"); sp.add_argument("--workspace", default=".")
    sp = pk.add_parser("list"); sp.add_argument("--workspace", default=".")
    sp = pk.add_parser("show"); sp.add_argument("name"); sp.add_argument("--workspace", default=".")
    sp = pk.add_parser("doctor"); sp.add_argument("name", nargs="?"); sp.add_argument("--workspace", default=".")
    sp = pk.add_parser("capabilities"); sp.add_argument("--workspace", default=".")

    tools = sub.add_parser("tools"); ts = tools.add_subparsers(dest="tools_cmd", required=True)
    sp = ts.add_parser("list"); sp.add_argument("--workspace", default=".")
    sp = ts.add_parser("doctor"); sp.add_argument("--workspace", default=".")
    tool = sub.add_parser("tool"); tls = tool.add_subparsers(dest="tool_cmd", required=True)
    sp = tls.add_parser("run"); sp.add_argument("name"); sp.add_argument("--path"); sp.add_argument("--content"); sp.add_argument("--command"); sp.add_argument("--workspace", default="."); sp.add_argument("--execute", action="store_true"); sp.add_argument("--approve", action="store_true")

    perms = sub.add_parser("permissions"); ps = perms.add_subparsers(dest="permissions_cmd", required=True); ps.add_parser("list")

    pkgtools = sub.add_parser("package-tools"); pts = pkgtools.add_subparsers(dest="package_tools_cmd", required=True)
    sp = pts.add_parser("needs"); sp.add_argument("package"); sp.add_argument("--workspace", default=".")
    sp = pts.add_parser("doctor"); sp.add_argument("package"); sp.add_argument("--workspace", default="."); sp.add_argument("--execute", action="store_true")

    broker = sub.add_parser("broker"); bs = broker.add_subparsers(dest="broker_cmd", required=True)
    sp = bs.add_parser("explain"); sp.add_argument("prompt"); sp.add_argument("--workspace", default="."); sp.add_argument("--execute", action="store_true")
    sp = bs.add_parser("providers"); sp.add_argument("--workspace", default=".")

    sub.add_parser("drivers")

    a = p.parse_args(argv)

    if a.version: return pj({"version": axiomos.__version__})
    if a.cmd == "version": return pj({"version": axiomos.__version__})
    if a.cmd == "about":
        if a.doc: return print(read_doc(a.doc))
        return pj(about_payload())
    if a.query and not a.cmd:
        if a.progress or a.execute: print("AxiomOS: routing request...", file=sys.stderr)
        code = run_one_shot(a.query, a.execute)
        if a.progress or a.execute: print("AxiomOS: done.", file=sys.stderr)
        raise SystemExit(code)
    if not a.cmd: raise SystemExit(run_shell())

    if a.cmd == "setup":
        if not a.setup_cmd: return pj(run_setup(home=a.home, dry_run=a.dry_run, profile=a.profile))
        if a.setup_cmd == "provider":
            if a.kind != "cloudflare": return pj({"status": "error", "message": "Only cloudflare provider setup is supported."})
            return pj(setup_cloudflare_provider(a.name, a.account_env, a.token_env, workspace=a.workspace, home=a.home, dry_run=a.dry_run))
        if a.setup_cmd == "memory":
            return pj(setup_memory(home=a.home, workspace=a.workspace, enabled=str(a.enabled).lower()=="true", attention_limit=a.attention_limit, compression_chars=a.compression_chars, dry_run=a.dry_run))
        if a.setup_cmd == "permissions":
            return pj(setup_permissions(a.profile, home=a.home, dry_run=a.dry_run))

    if a.cmd == "config":
        if a.config_cmd == "init": return pj(config_status(ensure_home(a.home)))
        data = load_config(a.home)
        if a.config_cmd == "path": return pj(config_status(a.home))
        if a.config_cmd == "list": return pj(data)
        if a.config_cmd == "get": return pj({"key": a.key, "value": get_key(data, a.key)})
        if a.config_cmd == "set":
            data = set_key(data, a.key, a.value)
            path = save_config(data, a.home)
            return pj({"status": "ok", "path": str(path), "key": a.key, "value": get_key(data, a.key)})

    if a.cmd in {"parse", "validate", "ir", "graph", "plan", "run", "compile"}:
        doc = parse_ax_file(a.file)
        if a.cmd == "parse": return pj(doc.to_dict())
        if a.cmd == "validate":
            d = validate_document(doc, strict=a.strict); pj({"diagnostics": d}); raise SystemExit(1 if has_errors(d) else 0)
        if a.cmd == "ir":
            ir = emit_ir(doc, strict=a.strict); pj(ir.to_dict()); raise SystemExit(1 if has_errors(ir.diagnostics) else 0)
        d = validate_document(doc)
        if has_errors(d): pj({"diagnostics": d}); raise SystemExit(1)
        g = build_graph(doc)
        if a.cmd == "graph": return pj(g)
        plan = create_plan(g)
        if a.cmd == "plan": return pj(plan)
        if a.cmd == "compile": return pj({"status": "compiled", "file": a.file, "plan": plan})
        return pj({"status": "dry_run_plan_only", "message": "No execution happened. Parsed, validated, graphed, and planned only.", "plan": plan})

    if a.cmd == "loop":
        if a.loop_cmd == "list": return pj(list_loops(a.file))
        if a.loop_cmd == "compile": return pj(compile_loops(a.file, a.output))
        if a.loop_cmd == "run": return pj(run_loops_file(a.file, workspace=a.workspace, dry_run=a.dry_run))
    if a.cmd == "loop-os": return pj(LoopOS(a.workspace).run_file(a.file, dry_run=a.dry_run, name=a.name))
    if a.cmd == "doctor": return pj(run_doctor(a.workspace))
    if a.cmd == "providers": return pj({"providers": provider_status(a.workspace)})
    if a.cmd == "model":
        if a.model_cmd == "list": return pj({"models": provider_status(a.workspace)})
        if a.model_cmd == "set": return pj({"active_provider": set_active_provider(a.name, a.workspace)})
        if a.model_cmd == "add" and a.kind == "cloudflare": return pj({"added": add_cloudflare_provider(a.name, a.account_env, a.token_env, a.workspace)})
    if a.cmd == "memory":
        store = MemoryStore(a.workspace)
        if a.memory_cmd == "stats": return pj(store.stats())
        if a.memory_cmd == "list": return pj({"records": store.list(a.type)})
        if a.memory_cmd == "search": return pj({"records": store.search(a.query)})
        if a.memory_cmd == "attention": return pj(store.attention(a.query))
        if a.memory_cmd == "conflicts": return pj({"conflicts": store.conflicts()})
        if a.memory_cmd == "export": return pj({"path": store.export(a.path)})
        if a.memory_cmd == "import": return pj(store.import_file(a.path))
        if a.memory_cmd == "rebuild-index": return pj(store.rebuild_index())
    if a.cmd == "receipt":
        if a.receipt_cmd == "list": return pj({"receipts": list_receipts(a.workspace)})
        if a.receipt_cmd == "show": return pj(show_receipt(a.ref, a.workspace))
    if a.cmd == "package":
        reg = PackageRegistry(a.workspace)
        if a.package_cmd == "install": return pj(reg.install(a.path))
        if a.package_cmd == "list": return pj({"packages": reg.list()})
        if a.package_cmd == "show": return pj(reg.get(a.name))
        if a.package_cmd == "doctor": return pj(reg.doctor(a.name))
        if a.package_cmd == "capabilities": return pj({"capabilities": reg.capabilities()})
    if a.cmd == "tools":
        if a.tools_cmd == "list": return pj({"tools": ToolRegistry().list()})
        if a.tools_cmd == "doctor": return pj(tool_doctor(a.workspace))
    if a.cmd == "tool":
        tool, action = parse_tool_name(a.name)
        args = {}
        if a.path is not None: args["path"] = a.path
        if a.content is not None: args["content"] = a.content
        if a.command is not None: args["command"] = a.command
        return pj(execute_tool(ToolRequest(tool, action, args, dry_run=not a.execute, human_approved=a.approve), workspace=a.workspace))
    if a.cmd == "permissions": return pj({"permissions": permission_catalog()})
    if a.cmd == "package-tools":
        if a.package_tools_cmd == "needs": return pj(package_tool_needs(a.package, workspace=a.workspace))
        if a.package_tools_cmd == "doctor": return pj(run_package_doctor_tools(a.package, workspace=a.workspace, dry_run=not a.execute))
    if a.cmd == "broker":
        if a.broker_cmd == "providers": return pj({"providers": provider_status(a.workspace)})
        route = route_prompt(a.prompt)
        dry_run = not a.execute
        intent = {"goal": a.prompt, "domain": route["domain"], "required_packages": route["packages"], "required_capabilities": tuple(sorted(set([route["domain"]] + route["packages"] + route["verification"]))), "risk": route["risk"], "quality_target": route["quality_target"], "constraints": ("dry_run",) if dry_run else ("execution_unlocked",)}
        return pj(explain_broker(a.prompt, route, intent, workspace=a.workspace, dry_run=dry_run))
    if a.cmd == "drivers": return pj({"drivers": DriverRegistry().list()})

if __name__ == "__main__":
    main()
