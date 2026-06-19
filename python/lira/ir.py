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

    def input(self, id: int, ss: 'StatementSeq') -> 'Statement':
        target = self.inputs[id]
        for stmt in ss.stmts:
            if target in stmt.outputs:
                return stmt
        raise ValueError(f'input {target} not found')

@dataclass
class StatementSeq:
    stmts: list[Statement]
