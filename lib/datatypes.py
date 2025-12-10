# Data type definitions
from dataclasses import dataclass


@dataclass
class PrimitiveSymbol:
    """The most basic symbols that make up mathematical notation (mi elements)"""
    text: str
    unicode_name: str | None

@dataclass
class SoG:
    start_id: str
    stop_id: str
    type: str
    
@dataclass
class MathConcept:
    """A single Math Concept"""
    code_var_name: str
    description: str
    tensor_rank: int
    affixes: list[str]
    sog_list: list[SoG]
    primitive_symbols: list[str]
    
@dataclass
class Group:
    ancestry_level_start: int
    ancestry_level_stop: int
    start_id: str
    stop_id: str

@dataclass
class EoI:
    symbolic_code: str

@dataclass
class Occurence:
    """Occurence of a concept within the text"""
    mc_id: str
    tag_name: str


    

    