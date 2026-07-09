def build_graph(doc):
    edges=[e.to_dict() for e in doc.edges]; task_ids=[n.id for n in doc.nodes if n.type=='TASK']; deps={t:[] for t in task_ids}
    for n in doc.nodes:
        for k,v in n.properties.items():
            refs=v if isinstance(v,list) else [v]
            if k=='depends_on':
                for r in refs: edges.append({'source':r,'target':n.id,'relation':'depends_on','properties':{},'line':n.line}); deps.setdefault(n.id,[]).append(r)
            elif k in {'mitigation','resolves','verifies','evidence','test'}:
                for r in refs: edges.append({'source':n.id,'target':r,'relation':k,'properties':{},'line':n.line})
    ready=[]; blocked=[]
    for t in task_ids:
        miss=[d for d in deps.get(t,[]) if d in task_ids]
        blocked.append({'task_id':t,'blocked_by':miss}) if miss else ready.append(t)
    return {'nodes':[n.to_dict() for n in doc.nodes],'edges':edges,'ready_tasks':ready,'blocked_tasks':blocked}


def detect_cycles(graph):
    deps = {}
    for e in graph.get("edges", []):
        if e.get("relation") == "depends_on":
            deps.setdefault(e["target"], []).append(e["source"])
    visited, stack, cycles = set(), set(), []
    def visit(node, path):
        if node in stack:
            idx = path.index(node) if node in path else 0
            cycles.append(path[idx:] + [node])
            return
        if node in visited:
            return
        visited.add(node); stack.add(node)
        for nxt in deps.get(node, []):
            visit(nxt, path + [nxt])
        stack.remove(node)
    for n in deps:
        visit(n, [n])
    return cycles
