from dataclasses import dataclass
from typing import Optional

@dataclass
class Shape:
    lanes_base: int
    lanes_mult: Optional[str]

@dataclass
class Statement:
    shape: Shape
    outputs: list[str]
    outputs_types: list[int]
    kind: str
    specifier: str
    inputs: list[str]

@dataclass
class StatementSeq:
    stmts: [Statement]
