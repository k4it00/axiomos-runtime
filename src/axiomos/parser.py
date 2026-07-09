import re
from pathlib import Path
from .models import AxiomDocument,AxiomNode,AxiomEdge
NODE_RE=re.compile(r'^(?P<type>[A-Z_]+)\s+(?P<id>[A-Za-z0-9_-]+)\s+"(?P<text>.*)"\s*$'); EDGE_RE=re.compile(r'^EDGE\s+(?P<source>[A-Za-z0-9_-]+)\s*->\s*(?P<target>[A-Za-z0-9_-]+)(?:\s+"(?P<relation>[^"]+)")?\s*$'); PROP_RE=re.compile(r'^\s+(?P<key>[A-Za-z0-9_:-]+):\s*(?P<value>.*)\s*$')
def _parse(raw):
    raw=raw.strip()
    if raw.lower()=="true": return True
    if raw.lower()=="false": return False
    if raw.startswith("[") and raw.endswith("]"):
        inner=raw[1:-1].strip(); return [] if not inner else [x.strip().strip('"').strip("'") for x in inner.split(",")]
    try: return float(raw) if "." in raw else int(raw)
    except ValueError: return raw.strip('"').strip("'")
def parse_ax_text(text):
    doc=AxiomDocument("unknown"); cur=None; meta=False; seen=False
    for i,line in enumerate(text.splitlines(),1):
        s=line.strip()
        if not s or s.startswith("#"): continue
        if s.startswith("AXIOM "): doc.version=s.split(" ",1)[1].strip(); seen=True; cur=None; meta=False; continue
        if s=="META": meta=True; cur=None; continue
        p=PROP_RE.match(line)
        if p and meta and cur is None: doc.meta[p.group("key")]=_parse(p.group("value")); continue
        e=EDGE_RE.match(s)
        if e: cur=AxiomEdge(e.group("source"),e.group("target"),e.group("relation") or "related_to",{},i); doc.edges.append(cur); meta=False; continue
        n=NODE_RE.match(s)
        if n: cur=AxiomNode(n.group("type"),n.group("id"),n.group("text"),{},i); doc.nodes.append(cur); meta=False; continue
        p=PROP_RE.match(line)
        if p and cur is not None: cur.properties[p.group("key")]=_parse(p.group("value")); continue
        doc.diagnostics.append({"level":"ERROR","line":i,"message":f"Unrecognized syntax: {line}"})
    if not seen: doc.diagnostics.append({"level":"ERROR","line":1,"message":"Missing AXIOM version line"})
    return doc
def parse_ax_file(path): return parse_ax_text(Path(path).read_text(encoding="utf-8"))
