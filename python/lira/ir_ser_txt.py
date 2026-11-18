from .ir import *

import re

def serialize_shape(shape: Shape) -> str:
    if shape.is_scalar():
        return '.'
    return '.'.join(f'{d.lanes_base}{d.lanes_mult or ""}' for d in shape.dimensions)

def deserialize_dimension(s: str) -> Dimension:
    m = re.fullmatch(r'(\d+)(.*)', s)
    return Dimension(int(m.group(1)), m.group(2) or None)

def deserialize_shape(s: str) -> Shape:
    return Shape() if s == '.' else Shape(list(map(deserialize_dimension, s.split('.'))))

def serialize_statement(stmt: Statement) -> str:
    shape_parts = [] if stmt.shape.is_scalar() else [serialize_shape(stmt.shape)]
    out_parts = [x for typ, name in zip(stmt.outputs_types, stmt.outputs) for x in (str(typ), name)]
    parts = shape_parts + out_parts + ['=', stmt.kind, stmt.specifier] + stmt.inputs
    return " ".join(parts)

def deserialize_statement(s: str) -> Statement:
    lhs, rhs = s.split('=', 1)
    pairs = lhs.split()
    shape = deserialize_shape(pairs.pop(0)) if len(pairs) % 2 else Shape()
    kind, specifier, *inputs = rhs.split()
    outputs_types = [int(pairs[i]) for i in range(0, len(pairs), 2)]
    outputs = [pairs[i+1] for i in range(0, len(pairs), 2)]
    return Statement(shape, outputs, outputs_types, kind, specifier, inputs)

def serialize_statement_seq(seq: StatementSeq) -> str:
    return ''.join(f'{serialize_statement(s)};\n' for s in seq.stmts)

def deserialize_statement_seq(s: str) -> StatementSeq:
    raw_stmts = [part.strip() for part in s.split(";") if part.strip()]
    return StatementSeq([deserialize_statement(raw) for raw in raw_stmts])
