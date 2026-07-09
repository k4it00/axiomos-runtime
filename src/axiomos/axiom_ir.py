from dataclasses import dataclass,asdict
from .validator import validate_document
@dataclass(frozen=True)
class AxiomIR:
    version:str; meta:dict; nodes:list; edges:list; diagnostics:list
    def to_dict(self): return asdict(self)
def emit_ir(doc,strict=False): return AxiomIR(doc.version,doc.meta,[n.to_dict() for n in doc.nodes],[e.to_dict() for e in doc.edges],validate_document(doc,strict))
