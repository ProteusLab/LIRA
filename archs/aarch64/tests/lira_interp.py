"""Minimal reference interpreter for scalar (shape 1) LIRA statement sequences.

Standard operations follow SMT-LIB bit-vector semantics (shifts by >= width give
0 / sign fill, signed division truncates and wraps).
"""
from typing import Callable, Dict, List

from python.lira.arch import Arch, Instruction, Operation
from python.lira.ir import StatementSeq


def _m(w): return (1 << w) - 1
def _s(v, w): return v - (1 << w) if v >> (w - 1) & 1 else v


def _std(base: str, op: Operation, a: List[int]) -> List[int]:
    n = op.inputs[-1]
    o = op.outputs[0]
    if base == 'not': r = ~a[0]
    elif base == 'neg': r = -a[0]
    elif base == 'popcnt': r = bin(a[0]).count('1')
    elif base == 'clz': r = n - a[0].bit_length()
    elif base == 'ctz': r = n if a[0] == 0 else (a[0] & -a[0]).bit_length() - 1
    elif base == 'reverse': r = int(format(a[0], f'0{n}b')[::-1], 2)
    elif base == 'add': r = a[0] + a[1]
    elif base == 'sub': r = a[0] - a[1]
    elif base == 'mul': r = a[0] * a[1]
    elif base == 'and': r = a[0] & a[1]
    elif base == 'orr': r = a[0] | a[1]
    elif base == 'xor': r = a[0] ^ a[1]
    elif base == 'lsl': r = a[0] << a[1] if a[1] < n else 0
    elif base == 'lsr': r = a[0] >> a[1] if a[1] < n else 0
    elif base == 'asr': r = _s(a[0], n) >> min(a[1], n)
    elif base == 'ror':
        k = a[1] % n
        r = (a[0] >> k) | (a[0] << (n - k))
    elif base == 'rol':
        k = a[1] % n
        r = (a[0] << k) | (a[0] >> (n - k))
    elif base in ('eq', 'ne', 'slt', 'sle', 'sgt', 'sge', 'ult', 'ule', 'ugt', 'uge'):
        x, y = (a[0], a[1]) if base[0] == 'u' or base in ('eq', 'ne') else (_s(a[0], n), _s(a[1], n))
        r = {'eq': x == y, 'ne': x != y, 'slt': x < y, 'sle': x <= y, 'sgt': x > y,
             'sge': x >= y, 'ult': x < y, 'ule': x <= y, 'ugt': x > y, 'uge': x >= y}[base]
    elif base == 'add_overflow':
        s = _s(a[0], n) + _s(a[1], n); r = not (-(1 << (n - 1)) <= s < (1 << (n - 1)))
    elif base == 'sub_overflow':
        s = _s(a[0], n) - _s(a[1], n); r = not (-(1 << (n - 1)) <= s < (1 << (n - 1)))
    elif base == 'div_u': r = a[2] if a[1] == 0 else a[0] // a[1]
    elif base == 'div_s':
        if a[1] == 0:
            r = a[2]
        else:
            x, y = _s(a[0], n), _s(a[1], n)
            q = abs(x) // abs(y)
            r = q if (x < 0) == (y < 0) else -q
    elif base == 'rem_u': r = a[0] if a[1] == 0 else a[0] % a[1]
    elif base == 'rem_s':
        if a[1] == 0:
            r = a[0]
        else:
            x, y = _s(a[0], op.inputs[0]), _s(a[1], op.inputs[0])
            r = abs(x) % abs(y) * (-1 if x < 0 else 1)
    elif base == 'select': r = a[1] if a[0] else a[2]
    elif base == 'extend_zero': r = a[0]
    elif base == 'extend_sign': r = _s(a[0], op.inputs[0])
    elif base == 'extract_low': r = a[0]
    else:
        raise NotImplementedError(base)
    return [int(r) & _m(o)]


class Machine:
    def __init__(self, arch: Arch):
        self.arch = arch
        self.ops = {o.name: o for o in arch.operations}
        self.snippets = {s.name: s for s in arch.snippets}
        self.instrs = {i.name: i for i in arch.instructions}
        self.regs: Dict[str, List[int]] = {rf.name: [0] * rf.regs_num() for rf in arch.register_files}
        self.env: Dict[str, Callable] = {}
        self.dyn: Dict[str, int] = {}

    def run_op(self, op: Operation, args: List[int]) -> List[int]:
        if op.semantic_base:
            return _std(op.semantic_base, op, args)
        return self.run(self.snippets[op.semantic_func].seq, args)

    def run(self, seq: StatementSeq, inputs: List[int]) -> List[int]:
        vals: Dict[str, int] = {}
        outputs: Dict[int, int] = {}
        for st in seq.stmts:
            assert st.shape.lanes_base == 1 and st.shape.lanes_mult is None
            args = [vals[i] for i in st.inputs]
            k, spec = st.kind, st.specifier
            if k == 'input': res = [inputs[int(spec)]]
            elif k == 'output': outputs[int(spec)] = args[0]; res = []
            elif k == 'const': res = [int(spec)]
            elif k == 'dyn_const': res = [self.dyn[spec]]
            elif k == 'read': res = [self.regs[spec][args[0]]]
            elif k == 'write': self.regs[spec][args[0]] = args[1]; res = []
            elif k == 'op': res = self.run_op(self.ops[spec], args)
            elif k == 'env': res = self.env[spec](*args) or []
            elif k == 'cond_env':
                nin = len(args) - 1 - len(st.outputs)
                res = (self.env[spec](*args[1:1 + nin]) or []) if args[0] else args[1 + nin:]
            else:
                raise NotImplementedError(k)
            assert len(res) == len(st.outputs), st
            for name, w, v in zip(st.outputs, st.outputs_types, res):
                assert 0 <= v <= _m(w), (st, v)
                vals[name] = v
        return [outputs[i] for i in sorted(outputs)]

    # -- encoding helpers ------------------------------------------------------
    def encode(self, ins: Instruction, operands: List[int]) -> int:
        self.dyn['enc_base'] = ins.encoding.const_encoding_part
        return self.run(self.snippets[ins.encoding.encode].seq, operands)[0]

    def decode(self, ins: Instruction, word: int) -> List[int]:
        return [self.run(self.snippets[d].seq, [word])[0] for d in ins.encoding.decode]

    def valid_operands(self, ins: Instruction, operands: List[int]) -> bool:
        c = ins.encoding.constraint_encode
        return not c or bool(self.run(self.snippets[c].seq, operands)[0])

    def valid_word(self, ins: Instruction, word: int) -> bool:
        e = ins.encoding
        if word & e.const_mask != e.const_encoding_part:
            return False
        return not e.constraint_decode or bool(self.run(self.snippets[e.constraint_decode].seq, [word])[0])

    def execute(self, ins: Instruction, operands: List[int]):
        self.run(ins.semantic, operands)
