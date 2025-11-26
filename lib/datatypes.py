# Data type definitions
from dataclasses import dataclass


@dataclass
class MathIdentifier:
    """A type of Math identifier"""

    hexcode: str
    var: str


@dataclass
class MathConcept:
    """A single Math Concept"""

    description: str
    arity: int
    affixes: list[str]


@dataclass
class CompoundMathConcept:
    """A single Compound Math Concept"""
    description: str
    arity: int
    primitive_concepts: list[str]
    
@dataclass
class Group:
    element_ids: list[str]

@dataclass
class Occurence:
    """Occurence of a concept within the text"""
    compound_concept_id: str
    sog: list
    tag_name: str
    

    