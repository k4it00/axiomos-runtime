import re
SECRET_PATTERNS=[re.compile(r"cfut_[A-Za-z0-9_-]{20,}"),re.compile(r"sk-[A-Za-z0-9_-]{16,}"),re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*[A-Za-z0-9_\-]{8,}")]
REF_KEYS={"depends_on","mitigation","resolves","verifies","evidence","evidence_ref","test","owner_ref"}
def _refs(v): return v if isinstance(v,list) else [v]
def _has(p,keys): return any(k in p and p[k] not in ("",None,[]) for k in keys)
def validate_document(doc,strict=False):
    ds=list(doc.diagnostics); seen={}
    for n in doc.nodes:
        if n.id in seen: ds.append({"level":"ERROR","line":n.line,"message":f"Duplicate node id: {n.id}"})
        seen[n.id]=n; hay=n.text+" "+" ".join(str(v) for v in n.properties.values())
        if any(p.search(hay) for p in SECRET_PATTERNS): ds.append({"level":"ERROR","line":n.line,"message":f"Possible raw secret found in node {n.id}"})
    ids=set(seen)
    for e in doc.edges:
        if e.source not in ids: ds.append({"level":"ERROR","line":e.line,"message":f"EDGE references missing source: {e.source}"})
        if e.target not in ids: ds.append({"level":"ERROR","line":e.line,"message":f"EDGE references missing target: {e.target}"})
    for n in doc.nodes:
        for k,v in n.properties.items():
            if k in REF_KEYS:
                for r in _refs(v):
                    if isinstance(r,str) and r and r not in ids and not r.startswith(("http://","https://","file:","env:")): ds.append({"level":"ERROR","line":n.line,"message":f"Missing reference {r} in {n.id}.{k}"})
    types={n.type for n in doc.nodes}
    if "GOAL" in types and "SUCCESS" not in types: ds.append({"level":"WARN","line":0,"law":"LAW-0001","message":"GOAL without SUCCESS"})
    if "SUCCESS" in types and "VERIFY" not in types: ds.append({"level":"WARN","line":0,"law":"LAW-0003","message":"SUCCESS without VERIFY"})
    for n in doc.nodes:
        p=n.properties
        if n.type in {"FACT","CLAIM"} and not _has(p,("evidence","evidence_ref","source")): ds.append({"level":"WARN","line":n.line,"law":"LAW-0001","message":f"{n.type} {n.id} without evidence/source"})
        if n.type=="HYPOTHESIS" and not _has(p,("test","verify","verification")): ds.append({"level":"WARN","line":n.line,"law":"LAW-0003","message":f"HYPOTHESIS {n.id} without test/verification"})
        if n.type=="RISK":
            if not _has(p,("severity",)): ds.append({"level":"WARN","line":n.line,"law":"LAW-0001","message":f"RISK {n.id} without severity"})
            if not _has(p,("mitigation","mitigated_by")): ds.append({"level":"WARN","line":n.line,"law":"LAW-0001","message":f"RISK {n.id} without mitigation"})
    if strict: ds=[{**d,"level":"ERROR"} if d.get("level")=="WARN" else d for d in ds]
    return ds
def has_errors(ds): return any(d.get("level")=="ERROR" for d in ds)
