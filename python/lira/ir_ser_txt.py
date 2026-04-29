from lira.ir import *

import re

def serialize_shape(shape: Shape) -> str:
    return f'{shape.lanes_base}{shape.lanes_mult if shape.lanes_mult else ""}'

def deserialize_shape(s: str) -> Shape:
    m = re.fullmatch(r'(\d+)(.*)', s)
    return Shape(int(m.group(1)), m.group(2) or None)

def serialize_statement(stmt: Statement) -> str:
    shape_str = serialize_shape(stmt.shape)
    out_parts = [x for typ, name in zip(stmt.outputs_types, stmt.outputs) for x in (str(typ), name)]
    parts = [shape_str] + out_parts + ['=', stmt.kind, stmt.specifier] + stmt.inputs
    return " ".join(parts)

def deserialize_statement(s: str) -> Statement:
    m = re.match(r'^(\w+)\s+(.*?)\s*=\s*(\w+)\s+(\S+)\s*(.*)$', s)
    shape_str, outputs_str, kind, specifier, inputs_str = m.groups()
    shape = deserialize_shape(shape_str)
    pairs = outputs_str.split()
    outputs_types = [int(pairs[i]) for i in range(0, len(pairs), 2)]
    outputs = [pairs[i+1] for i in range(0, len(pairs), 2)]
    inputs = inputs_str.split() if inputs_str else []
    return Statement(shape, outputs, outputs_types, kind, specifier, inputs)

def serialize_statement_seq(seq: StatementSeq) -> str:
    return ''.join(f'{serialize_statement(s)};\n' for s in seq.stmts)

def deserialize_statement_seq(s: str) -> StatementSeq:
    raw_stmts = [part.strip() for part in s.split(";") if part.strip()]
    return StatementSeq([deserialize_statement(raw) for raw in raw_stmts])
