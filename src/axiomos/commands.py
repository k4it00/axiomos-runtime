from .session import AxiomSession
from .hypervisor import run_prompt
from .loop_runtime import list_loops,compile_loops,run_loops_file
from .loop_os import LoopOS
from .memory import MemoryStore
from .doctor import run_doctor
from .receipts import list_receipts,show_receipt
from .provider_config import provider_status,set_active_provider
from .packages import PackageRegistry
from .tools import ToolRequest, execute_tool, ToolRegistry, parse_tool_name, tool_doctor
from .permissions import permission_catalog
from .about import about_payload, read_doc
from .goal_shell import GoalShell
def dispatch_line(line,session:AxiomSession):
    s=line.strip()
    if not s: return {"status":"noop"}
    if not s.startswith("/"):
        r=run_prompt(s,workspace=session.workspace,mode=session.mode,reasoning=session.reasoning,dry_run=True); session.last=r; return r
    parts=s.split(); cmd=parts[0]; args=parts[1:]
    if cmd in {"/exit","/quit"}: return {"status":"exit"}
    if cmd=="/help": return {"status":"ok","commands":["/providers list","/model list|set NAME","/memory stats|list|search","/receipt list|show","/doctor","/loop run FILE","/exit"]}
    if cmd=="/doctor": return run_doctor(session.workspace)
    if cmd=="/providers": return {"status":"ok","providers":provider_status(session.workspace)}
    if cmd=="/model":
        if not args or args[0]=="list": return {"status":"ok","models":provider_status(session.workspace)}
        if args[0]=="set" and len(args)>1: return {"status":"ok","active_provider":set_active_provider(args[1],session.workspace)}
    if cmd=="/memory":
        store=MemoryStore(session.workspace)
        if not args or args[0]=="stats": return {"status":"ok","memory":store.stats()}
        if args[0]=="list": return {"status":"ok","records":store.list(args[1] if len(args)>1 else None)}
        if args[0]=="search" and len(args)>1: return {"status":"ok","records":store.search(" ".join(args[1:]))}
        if args[0]=="attention" and len(args)>1: return {"status":"ok","attention":store.attention(" ".join(args[1:]))}
        if args[0]=="conflicts": return {"status":"ok","conflicts":store.conflicts()}
    if cmd=="/receipt":
        if not args or args[0]=="list": return {"status":"ok","receipts":list_receipts(session.workspace)}
        if args[0]=="show" and len(args)>1: return {"status":"ok","receipt":show_receipt(args[1],session.workspace)}
    if cmd=="/loop" and args and args[0]=="run" and len(args)>1: return run_loops_file(args[1],workspace=session.workspace)
    if cmd=="/package":
        reg=PackageRegistry(session.workspace)
        if not args or args[0]=="list": return {"status":"ok","packages":reg.list()}
        if args[0]=="show" and len(args)>1: return {"status":"ok","package":reg.get(args[1])}
        if args[0]=="doctor": return reg.doctor(args[1] if len(args)>1 else None)
        if args[0]=="capabilities": return {"status":"ok","capabilities":reg.capabilities()}
        if args[0]=="install" and len(args)>1: return {"status":"ok", **reg.install(args[1])}
    if cmd=="/tools":
        if not args or args[0]=="list": return {"status":"ok","tools":ToolRegistry().list()}
        if args[0]=="doctor": return tool_doctor(session.workspace)
    if cmd=="/tool" and args and args[0]=="run" and len(args)>1:
        tool, action = parse_tool_name(args[1])
        return {"status":"ok","result":execute_tool(ToolRequest(tool, action, {"path":"."}, dry_run=True, source="shell"), workspace=session.workspace)}
    if cmd=="/permissions":
        return {"status":"ok","permissions":permission_catalog()}
    if cmd=="/loop-os" and args and args[0]=="run" and len(args)>1:
        return LoopOS(session.workspace).run_file(args[1], dry_run=True)
    if cmd=="/about":
        if args: return {"status":"ok","doc":read_doc(args[0])}
        return {"status":"ok","about":about_payload(session.workspace)}
    if cmd=="/last": return {"status":"ok","last":session.last}
    if cmd=="/goal" and args:
        gs=GoalShell(workspace=session.workspace, memory=MemoryStore(session.workspace))
        goal_text=" ".join(args)
        return {"status":"ok","result":gs.submit(goal_text)}
    return {"status":"error","message":f"Unknown command: {cmd}"}
