from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Dimension:
    lanes_base: int
    lanes_mult: Optional[str] = None

@dataclass
class Shape:
    dimensions: list[Dimension] = field(default_factory=list)

    def is_scalar(self) -> bool:
        return not self.dimensions

@dataclass
class Statement:
    shape: Shape
    outputs: list[str]
    outputs_types: list[int]
    kind: str
    specifier: str
    inputs: list[str]

    def input(self, id: int, ss: 'StatementSeq') -> 'Statement':
        target = self.inputs[id]
        for stmt in ss.stmts:
            if target in stmt.outputs:
                return stmt
        raise ValueError(f'input {target} not found')

@dataclass
class StatementSeq:
    stmts: list[Statement]
