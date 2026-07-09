from dataclasses import dataclass,field,asdict
from typing import Any
@dataclass
class AxiomNode:
    type:str; id:str; text:str; properties:dict[str,Any]=field(default_factory=dict); line:int=0
    def to_dict(self): return asdict(self)
@dataclass
class AxiomEdge:
    source:str; target:str; relation:str; properties:dict[str,Any]=field(default_factory=dict); line:int=0
    def to_dict(self): return asdict(self)
@dataclass
class AxiomDocument:
    version:str; meta:dict[str,Any]=field(default_factory=dict); nodes:list[AxiomNode]=field(default_factory=list); edges:list[AxiomEdge]=field(default_factory=list); diagnostics:list[dict[str,Any]]=field(default_factory=list)
    def to_dict(self): return {'version':self.version,'meta':self.meta,'nodes':[n.to_dict() for n in self.nodes],'edges':[e.to_dict() for e in self.edges],'diagnostics':self.diagnostics}
