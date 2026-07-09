from pathlib import Path
from datetime import datetime, timezone
import re,uuid,json
from .receipts import make_receipt, write_receipt
SECTION_RE=re.compile(r"^##\s+(?P<title>.+?)\s*$"); FIELD_RE=re.compile(r"^###\s+(?P<field>.+?)\s*$"); MAX_RE=re.compile(r"(?i)(?P<num>\d+)\s+(?:passes|pass|iterations|iteration)")
def _fname(s): return s.lower().strip().replace(" ","_").replace("-","_")
def _max(*texts):
    m=MAX_RE.search("\n".join(t or "" for t in texts)); return max(1,min(int(m.group("num")),20)) if m else 2
def parse_loops_md(path):
    p=Path(path); raw=[]; cur=None; field=None
    for line in p.read_text(encoding="utf-8").splitlines():
        sec=SECTION_RE.match(line)
        if sec:
            if cur: raw.append(cur)
            cur={"name":sec.group("title").strip(),"fields":{}}; field=None; continue
        if cur is None: continue
        f=FIELD_RE.match(line)
        if f: field=_fname(f.group("field")); cur["fields"][field]=""; continue
        if field: cur["fields"][field]+=line+"\n"
    if cur: raw.append(cur)
    return [{"loop_id":"loop_"+uuid.uuid5(uuid.NAMESPACE_URL,r["name"]).hex[:10],"name":r["name"],"goal":r["fields"].get("goal","").strip() or f"Run loop: {r['name']}","action":r["fields"].get("action","").strip() or "Perform bounded loop action.","acceptance_check":r["fields"].get("acceptance_check","").strip() or "Acceptance check missing.","stop_condition":r["fields"].get("stop_condition","").strip() or "Stop at max passes.","max_passes":_max(r["fields"].get("stop_condition","")),"source":str(p)} for r in raw]
def list_loops(path): return {"loops":parse_loops_md(path)}
def compile_loops(path,output_dir="compiled_loops"):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); written=[]
    for i,l in enumerate(parse_loops_md(path),1):
        target=out/f"{i:02d}_{l['name'].lower().replace(' ','_')}.ax"; target.write_text(f'AXIOM 0.2\n\nGOAL G1 "{l["goal"]}"\n\nTASK T1 "{l["action"]}"\n    max_passes: {l["max_passes"]}\n\nVERIFY V1 "{l["acceptance_check"]}"\n    required: true\n',encoding="utf-8"); written.append(str(target))
    return {"written":written}
def run_loops_file(path,workspace=".",dry_run=True,loop_name=None):
    loops=parse_loops_md(path); out=Path(workspace)/"axiom_runs"; out.mkdir(parents=True,exist_ok=True); runs=[]
    for l in loops:
        passes=[]; status="running"; stop=None
        for idx in range(1,l["max_passes"]+1):
            check=l["acceptance_check"].lower(); ver="verification_pending" if any(k in check for k in ("real-device","device","emulator","manual","external")) else ("passed_dry_run" if idx>=l["max_passes"] else "pending")
            passes.append({"pass_index":idx,"action":"DRY-RUN: "+l["action"],"progress":True,"verification_status":ver,"notes":"No model/tool/external action executed."})
            if ver=="passed_dry_run": status="success"; stop="acceptance_check_passed_dry_run"; break
            if ver=="verification_pending" and idx>=l["max_passes"]: status="stopped"; stop="verification_pending"; break
        receipt={"receipt_id":"loopreceipt_"+uuid.uuid4().hex[:10],"type":"loop_run","created_at":datetime.now(timezone.utc).isoformat(),"run":{"loop":l,"status":status,"passes":passes,"stop_reason":stop or "max_passes"},"status":status,"stop_reason":stop or "max_passes","dry_run":dry_run,"external_actions":0,"tools_executed":0}
        rp=out/f"{receipt['receipt_id']}.json"; rp.write_text(json.dumps(receipt,indent=2),encoding="utf-8"); runs.append({"run":receipt["run"],"receipt":receipt,"receipt_path":str(rp)})
    return {"status":"ok" if runs else "blocked","runs":runs}
