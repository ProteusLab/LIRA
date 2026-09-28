"""Minimal reference interpreter for scalar (shape 1) LIRA statement sequences.

Standard operations follow SMT-LIB bit-vector semantics (shifts by >= width give
0 / sign fill, signed division truncates and wraps).
"""
from typing import Callable, Dict, List

from python.lira.arch import Arch, Instruction, Operation
from python.lira.ir import StatementSeq
from python.lira import float_ops


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
        self.tables = {t.name: t for t in arch.tables_int}
        self.instrs = {i.name: i for i in arch.instructions}
        self.fops = {f.name: f for f in arch.float_operations}
        self.fpu = float_ops.FPUBinding.from_arch(arch)
        self.regs: Dict[str, List[int]] = {rf.name: [0] * rf.regs_num() for rf in arch.register_files}
        self.env: Dict[str, Callable] = {}
        self.dyn: Dict[str, int] = {}

    def run_op(self, op: Operation, args: List[int]) -> List[int]:
        """Evaluate an operation on scalar (single-lane) arguments."""
        if op.semantic_base:
            return _std(op.semantic_base, op, args)
        if op.semantic_table:
            return [self.tables[op.semantic_table].values[args[0]]]
        return [v[0] for v in self.run(self.snippets[op.semantic_func].seq, [[a] for a in args])]

    def run_fop(self, fop, args: List[int]) -> List[int]:
        (crf, ci), (srf, si) = self.fpu.control, self.fpu.status
        st = self.fpu.state(self.regs[crf][ci])
        res = float_ops.evaluate(fop, args, st)
        self.regs[srf][si] |= self.fpu.status_bits(st.flags)
        return res

    def _rf_size(self, name):
        return next(rf.reg_size.lanes_base for rf in self.arch.register_files if rf.name == name)

    def run(self, seq: StatementSeq, inputs: List[List[int]]) -> List[List[int]]:
        """Execute a sequence; every value is a list of lanes."""
        vals: Dict[str, List[int]] = {}
        outputs: Dict[int, List[int]] = {}
        for st in seq.stmts:
            assert st.shape.lanes_mult is None
            n = st.shape.lanes_base
            args = [vals[i] for i in st.inputs]
            k, spec = st.kind, st.specifier

            def lanewise(fn):
                assert all(len(a) == n for a in args), st
                outs = [fn([a[i] for a in args]) for i in range(n)]
                return [list(c) for c in zip(*outs)] if outs and outs[0] else [[] for _ in st.outputs]

            if k == 'input': res = [inputs[int(spec)]]
            elif k == 'output': outputs[int(spec)] = args[0]; res = []
            elif k == 'const': res = [[int(spec)] * n]
            elif k == 'dyn_const': res = [[self.dyn[spec]] * n]
            elif k == 'read':
                w = st.outputs_types[0]
                assert n * w == self._rf_size(spec), st
                reg = self.regs[spec][args[0][0]]
                res = [[(reg >> (i * w)) & _m(w) for i in range(n)]]
            elif k == 'write':
                idx, value = args
                w = self._rf_size(spec) // n
                assert len(value) == n
                self.regs[spec][idx[0]] = sum(v << (i * w) for i, v in enumerate(value))
                res = []
            elif k == 'op': res = lanewise(lambda a: self.run_op(self.ops[spec], a))
            elif k == 'fop': res = lanewise(lambda a: self.run_fop(self.fops[spec], a))
            elif k == 'env': res = lanewise(lambda a: self.env[spec](*a) or [])
            elif k == 'cond_env':
                nin = len(args) - 1 - len(st.outputs)
                res = lanewise(lambda a: (self.env[spec](*a[1:1 + nin]) or []) if a[0] else a[1 + nin:])
            elif k == 'index': res = [list(range(n))]
            elif k == 'gather':
                value, index, default = args
                res = [[value[j] if j < len(value) else default[i] for i, j in enumerate(index)]]
            elif k == 'replicate': res = [[args[0][0]] * n]
            elif k == 'extract_first': res = [args[0][:n]]
            elif k == 'extend_zero': res = [args[0] + [0] * (n - len(args[0]))]
            elif k == 'fold':
                width = len(st.outputs)
                state = [a[0] for a in args[:width]]
                vectors = args[width:]
                for lane in range(len(vectors[0])):
                    state = self.run_op(self.ops[spec], state + [v[lane] for v in vectors])[:width]
                res = [[v] for v in state]
            else:
                raise NotImplementedError(k)
            assert len(res) == len(st.outputs), st
            for name, w, v in zip(st.outputs, st.outputs_types, res):
                assert all(0 <= x <= _m(w) for x in v), (st, v)
                assert len(v) == (1 if k == 'fold' else n), st
                vals[name] = v
        return [outputs[i] for i in sorted(outputs)]

    def run_scalar(self, seq: StatementSeq, inputs: List[int]) -> List[int]:
        return [v[0] for v in self.run(seq, [[i] for i in inputs])]

    # -- encoding helpers ------------------------------------------------------
    def encode(self, ins: Instruction, operands: List[int]) -> int:
        self.dyn['enc_base'] = ins.encoding.const_encoding_part
        return self.run_scalar(self.snippets[ins.encoding.encode].seq, operands)[0]

    def decode(self, ins: Instruction, word: int) -> List[int]:
        return [self.run_scalar(self.snippets[d].seq, [word])[0] for d in ins.encoding.decode]

    def valid_operands(self, ins: Instruction, operands: List[int]) -> bool:
        c = ins.encoding.constraint_encode
        return not c or bool(self.run_scalar(self.snippets[c].seq, operands)[0])

    def valid_word(self, ins: Instruction, word: int) -> bool:
        e = ins.encoding
        if word & e.const_mask != e.const_encoding_part:
            return False
        return not e.constraint_decode or bool(self.run_scalar(self.snippets[e.constraint_decode].seq, [word])[0])

    def execute(self, ins: Instruction, operands: List[int]):
        self.run_scalar(ins.semantic, operands)
