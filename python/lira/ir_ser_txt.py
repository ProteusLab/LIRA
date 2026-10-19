from .ir import *

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
    tokens = s.split()
    try:
        eq = tokens.index('=')
    except ValueError:
        raise ValueError(f'invalid statement: {s!r}: missing "="') from None

    left = tokens[:eq]
    right = tokens[eq + 1:]
    if not left:
        raise ValueError(f'invalid statement: {s!r}: missing shape')
    if len(right) < 2:
        raise ValueError(f'invalid statement: {s!r}: missing kind or specifier')

    shape = deserialize_shape(left[0])
    output_tokens = left[1:]
    if len(output_tokens) % 2 != 0:
        raise ValueError(f'invalid statement: {s!r}: outputs must be type/name pairs')
    outputs_types = [int(t) for t in output_tokens[0::2]]
    outputs = output_tokens[1::2]
    kind, specifier = right[0], right[1]
    inputs = right[2:]
    return Statement(shape, outputs, outputs_types, kind, specifier, inputs)

def serialize_statement_seq(seq: StatementSeq) -> str:
    return ''.join(f'{serialize_statement(s)}\n' for s in seq.stmts)

def deserialize_statement_seq(s: str) -> StatementSeq:
    stmts = []
    for raw in s.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        stmts.append(deserialize_statement(line))
    return StatementSeq(stmts)
