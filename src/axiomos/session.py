from dataclasses import dataclass,field,asdict
@dataclass
class AxiomSession:
    mode:str='balanced'; reasoning:str='medium'; workspace:str='.'; last:dict|None=None; history:list=field(default_factory=list)
    def to_dict(self): return asdict(self)
