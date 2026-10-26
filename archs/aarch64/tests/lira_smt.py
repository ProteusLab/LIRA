"""Symbolic evaluation of LIRA semantics with z3.

`SymMachine.run` mirrors `lira_interp.Machine.run`, with every lane a z3
bit-vector instead of an int. Register indices must reduce to constants (the
callers fix the register fields of an encoding); the other operands, the
initial registers, PC and memory are free variables. The environment is the
Linux EL0 process of test_semantics_hw.interp_step: a hook gets a guard (the
lane condition of a `cond_env`, else true) and either returns its outputs,
updates the memory or next PC under the guard, or records an exception that
is taken when the guard holds.
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import z3

from python.lira.arch import Arch, Instruction, Operation
from python.lira.ir import StatementSeq

from .lira_interp import Machine

MEM_SORT = z3.ArraySort(z3.BitVecSort(64), z3.BitVecSort(8))

# Encoding fields that are register numbers (fixed by the callers)
REG_FIELDS = ('Rd', 'Rn', 'Rm', 'Ra', 'Rt', 'Rt2', 'Rs', 'Rdn')

# Register files the walker models, and the environment hooks it implements;
# an instruction that uses anything else is outside its scope
REG_FILES = ('X', 'NZCV')
HOOKS = ({f'mem_read_{n}' for n in (8, 16, 32, 64, 128)} | {f'mem_write_{n}' for n in (8, 16, 32, 64, 128)}
         | {'pc_read', 'pc_write', 'check_alignment', 'supervisor_call', 'exception_call', 'exception_return',
            'debug_state', 'barrier', 'hint', 'branch_target', 'wait_timeout'})

# exception_call kinds (insns_v8.EXCEPTIONS): BRK is a breakpoint exception,
# HLT/HVC/SMC/UDF are UNDEFINED at EL0
EXCEPTION_CALL_KINDS = {0: 'brk', 1: 'undefined', 2: 'undefined', 3: 'undefined', 4: 'undefined'}


class OutOfScope(Exception):
    """The instruction uses a part of LIRA the walker does not model."""


def bv(v, w):
    return z3.BitVecVal(v, w)


def const_int(x: z3.BitVecRef) -> int:
    x = z3.simplify(x)
    if not z3.is_bv_value(x):
        raise OutOfScope(f'symbolic value where a constant is needed: {x}')
    return x.as_long()


def _fit(x: z3.BitVecRef, w: int) -> z3.BitVecRef:
    """`x` truncated or zero-extended to `w` bits."""
    n = x.size()
    return x if n == w else z3.Extract(w - 1, 0, x) if n > w else z3.ZeroExt(w - n, x)


def _b(c: z3.BoolRef) -> z3.BitVecRef:
    return z3.If(c, bv(1, 1), bv(0, 1))


def _std(base: str, op: Operation, a: List[z3.BitVecRef]) -> z3.BitVecRef:
    """Mirror of lira_interp._std on bit-vectors."""
    n = op.inputs[-1]
    o = op.outputs[0]
    if base == 'not': r = ~a[0]
    elif base == 'neg': r = -a[0]
    elif base == 'popcnt':
        w = max(o, n.bit_length())
        r = sum(z3.ZeroExt(w - 1, z3.Extract(i, i, a[0])) for i in range(n))
    elif base == 'clz':
        r = bv(n, max(o, n.bit_length()))
        for i in range(n):                  # the highest set bit wins: it comes last
            r = z3.If(z3.Extract(i, i, a[0]) == 1, bv(n - 1 - i, r.size()), r)
    elif base == 'ctz':
        r = bv(n, max(o, n.bit_length()))
        for i in reversed(range(n)):
            r = z3.If(z3.Extract(i, i, a[0]) == 1, bv(i, r.size()), r)
    elif base == 'reverse': r = z3.Concat(*[z3.Extract(i, i, a[0]) for i in range(n)]) if n > 1 else a[0]
    elif base == 'add': r = a[0] + a[1]
    elif base == 'sub': r = a[0] - a[1]
    elif base == 'mul': r = a[0] * a[1]
    elif base == 'and': r = a[0] & a[1]
    elif base == 'orr': r = a[0] | a[1]
    elif base == 'xor': r = a[0] ^ a[1]
    elif base == 'lsl': r = a[0] << a[1]
    elif base == 'lsr': r = z3.LShR(a[0], a[1])
    elif base == 'asr': r = a[0] >> a[1]
    elif base in ('ror', 'rol'):
        k = z3.URem(a[1], bv(n, n))
        right = k if base == 'ror' else z3.URem(bv(n, n) - k, bv(n, n))
        r = z3.LShR(a[0], right) | (a[0] << (bv(n, n) - right))
    elif base == 'eq': r = _b(a[0] == a[1])
    elif base == 'ne': r = _b(a[0] != a[1])
    elif base == 'slt': r = _b(a[0] < a[1])
    elif base == 'sle': r = _b(a[0] <= a[1])
    elif base == 'sgt': r = _b(a[0] > a[1])
    elif base == 'sge': r = _b(a[0] >= a[1])
    elif base == 'ult': r = _b(z3.ULT(a[0], a[1]))
    elif base == 'ule': r = _b(z3.ULE(a[0], a[1]))
    elif base == 'ugt': r = _b(z3.UGT(a[0], a[1]))
    elif base == 'uge': r = _b(z3.UGE(a[0], a[1]))
    elif base == 'add_overflow':
        s = z3.SignExt(1, a[0]) + z3.SignExt(1, a[1])
        r = _b(s != z3.SignExt(1, z3.Extract(n - 1, 0, s)))
    elif base == 'sub_overflow':
        s = z3.SignExt(1, a[0]) - z3.SignExt(1, a[1])
        r = _b(s != z3.SignExt(1, z3.Extract(n - 1, 0, s)))
    elif base == 'div_u': r = z3.If(a[1] == 0, a[2], z3.UDiv(a[0], a[1]))
    elif base == 'div_s': r = z3.If(a[1] == 0, a[2], a[0] / a[1])
    elif base == 'rem_u': r = z3.If(a[1] == 0, a[0], z3.URem(a[0], a[1]))
    elif base == 'rem_s': r = z3.If(a[1] == 0, a[0], z3.SRem(a[0], a[1]))
    elif base == 'select': r = z3.If(a[0] == 1, a[1], a[2])
    elif base == 'extend_zero': r = z3.ZeroExt(o - op.inputs[0], a[0])
    elif base == 'extend_sign': r = z3.SignExt(o - op.inputs[0], a[0])
    elif base == 'extract_low': r = z3.Extract(o - 1, 0, a[0])
    else:
        raise OutOfScope(base)
    return _fit(r, o)


@dataclass
class LiraException:
    cond: z3.BoolRef        # taken when this holds and no earlier exception is
    kind: str               # 'svc', 'brk', 'undefined', 'alignment'
    imm: Optional[z3.BitVecRef] = None


@dataclass
class MemWrite:
    guard: z3.BoolRef
    addr: z3.BitVecRef
    value: z3.BitVecRef     # little-endian, value.size() // 8 bytes


@dataclass
class SymMachine:
    """One symbolic execution of an instruction. The initial state is
    `inputs` (created on first use): X0..X30, SP (X[31]), NZCV, PC and
    MEM (bytes by address)."""
    arch: Arch
    vq: int = 1
    regs: Dict[Tuple[str, int], z3.BitVecRef] = field(default_factory=dict)
    inputs: Dict[str, z3.ExprRef] = field(default_factory=dict)
    exceptions: List[LiraException] = field(default_factory=list)
    writes: List[MemWrite] = field(default_factory=list)
    next_pc: Optional[z3.BitVecRef] = None

    def __post_init__(self):
        self.m = Machine(self.arch, self.vq)      # tables, operations, snippets, shapes
        self.files = {rf.name: rf for rf in self.arch.register_files}
        self.alias = {}
        for rf in self.arch.register_files:
            for a in rf.attributes:
                al = re.fullmatch(r'alias\.(\w+)@0\+(\d+)', a)
                if al:
                    self.alias[al.group(1)] = (rf.name, int(al.group(2)))
        self.mem = self.input('MEM', MEM_SORT)
        self.next_pc = self.input('PC') + 4
        self.env: Dict[str, Callable] = {
            'pc_read': lambda g: [self.input('PC')],
            'pc_write': self._pc_write,
            'supervisor_call': lambda g, imm: self._raise(g, 'svc', imm),
            'exception_call': lambda g, kind, imm: self._raise(g, EXCEPTION_CALL_KINDS[const_int(kind)], imm),
            'exception_return': lambda g, kind: self._raise(g, 'undefined'),
            'debug_state': lambda g, kind: self._raise(g, 'undefined'),
            'check_alignment': self._check_alignment,
            **{name: lambda g, *a: [] for name in ('barrier', 'hint', 'branch_target', 'wait_timeout')},
            **{f'mem_read_{n}': self._reader(n) for n in (8, 16, 32, 64, 128)},
            **{f'mem_write_{n}': self._writer(n) for n in (8, 16, 32, 64, 128)},
        }

    # -- state -----------------------------------------------------------------
    def input(self, name: str, sort=None) -> z3.ExprRef:
        if name not in self.inputs:
            self.inputs[name] = z3.Const(name, z3.BitVecSort(64) if sort is None else sort)
        return self.inputs[name]

    @staticmethod
    def reg_name(rf: str, i: int) -> str:
        """X0..X30, SP; a single-register file by its name (NZCV)."""
        if rf == 'X':
            return 'SP' if i == 31 else f'X{i}'
        return rf if i == 0 else f'{rf}{i}'

    def _size(self, rf: str) -> int:
        return self.m.lanes(self.files[rf].reg_size)

    def reg(self, rf: str, i: int) -> z3.BitVecRef:
        if rf in self.alias:
            owner, w = self.alias[rf]
            return z3.Extract(w - 1, 0, self.reg(owner, i))
        if rf not in REG_FILES:
            raise OutOfScope(f'register file {rf}')
        if (rf, i) not in self.regs:
            self.regs[rf, i] = self.input(self.reg_name(rf, i), z3.BitVecSort(self._size(rf)))
        return self.regs[rf, i]

    def set_reg(self, rf: str, i: int, v: z3.BitVecRef):
        if rf in self.alias:
            owner, w = self.alias[rf]
            return self.set_reg(owner, i, z3.ZeroExt(self._size(owner) - w, v))
        if rf not in REG_FILES:
            raise OutOfScope(f'register file {rf}')
        assert v.size() == self._size(rf), (rf, v)
        self.regs[rf, i] = v

    def written(self) -> Dict[str, z3.BitVecRef]:
        """Final values of the registers the instruction wrote or read."""
        return {self.reg_name(rf, i): v for (rf, i), v in self.regs.items()}

    def read_mem(self, mem, addr: z3.BitVecRef, nbytes: int) -> z3.BitVecRef:
        bs = [z3.Select(mem, addr + i) for i in range(nbytes)]
        return z3.Concat(*reversed(bs)) if nbytes > 1 else bs[0]

    # -- hooks -----------------------------------------------------------------
    def _reader(self, n):
        return lambda g, addr: [self.read_mem(self.mem, addr, n // 8)]

    def _writer(self, n):
        def write(g, addr, v):
            new = self.mem
            for i in range(n // 8):
                new = z3.Store(new, addr + i, z3.Extract(8 * i + 7, 8 * i, v))
            self.mem = z3.If(g, new, self.mem)
            self.writes.append(MemWrite(g, addr, v))
            return []
        return write

    def _pc_write(self, g, target):
        self.next_pc = z3.If(g, target, self.next_pc)
        return []

    def _raise(self, g, kind, imm=None):
        self.exceptions.append(LiraException(g, kind, imm))
        return []

    def _check_alignment(self, g, addr, nbytes, exclusive):
        """test_semantics_hw.check_alignment: exclusives are naturally
        aligned, ordered and atomic accesses stay within 16 bytes (LSE2)."""
        size = z3.ZeroExt(56, nbytes)
        exc = z3.URem(addr, size) != 0
        other = z3.UGT(z3.URem(addr, bv(16, 64)) + size, bv(16, 64))
        return self._raise(z3.And(g, z3.If(exclusive == 1, exc, other)), 'alignment')

    def call(self, name, guard, args) -> List[z3.BitVecRef]:
        if name not in self.env:
            raise OutOfScope(f'environment function {name}')
        return self.env[name](guard, *args) or []

    # -- statements ------------------------------------------------------------
    def run_op(self, op: Operation, args: List[z3.BitVecRef]) -> List[z3.BitVecRef]:
        if op.semantic_base:
            return [_std(op.semantic_base, op, args)]
        if op.semantic_table:
            values = self.m.tables[op.semantic_table].values
            r = bv(0, op.outputs[0])
            for i, v in enumerate(values):
                r = z3.If(args[0] == i, bv(v, op.outputs[0]), r)
            return [r]
        return [v[0] for v in self.run(self.m.snippets[op.semantic_func].seq, [[a] for a in args])]

    def run(self, seq: StatementSeq, inputs: List[List[z3.BitVecRef]]) -> List[List[z3.BitVecRef]]:
        vals: Dict[str, List[z3.BitVecRef]] = {}
        outputs: Dict[int, List[z3.BitVecRef]] = {}
        for st in seq.stmts:
            n = self.m.lanes(st.shape)
            args = [vals[i] for i in st.inputs]
            k, spec = st.kind, st.specifier

            def lanewise(fn):
                assert all(len(a) == n for a in args), st
                outs = [fn([a[i] for a in args]) for i in range(n)]
                return [list(c) for c in zip(*outs)] if outs and outs[0] else [[] for _ in st.outputs]

            if k == 'input': res = [inputs[int(spec)]]
            elif k == 'output': outputs[int(spec)] = args[0]; res = []
            elif k == 'const': res = [[bv(int(spec), st.outputs_types[0])] * n]
            elif k == 'read':
                w = st.outputs_types[0]
                assert n * w == self._size(spec), st
                reg = self.reg(spec, const_int(args[0][0]))
                res = [[z3.Extract(i * w + w - 1, i * w, reg) if n > 1 else reg for i in range(n)]]
            elif k == 'write':
                idx, value = args
                assert len(value) == n
                self.set_reg(spec, const_int(idx[0]), z3.Concat(*reversed(value)) if n > 1 else value[0])
                res = []
            elif k == 'op': res = lanewise(lambda a: self.run_op(self.m.ops[spec], a))
            elif k == 'fop': raise OutOfScope('floating point')
            elif k == 'env': res = lanewise(lambda a: self.call(spec, z3.BoolVal(True), a))
            elif k == 'cond_env':
                nin = len(args) - 1 - len(st.outputs)

                def cond_call(a):
                    g = a[0] == 1
                    outs = self.call(spec, g, a[1:1 + nin])
                    return [z3.If(g, o, f) for o, f in zip(outs, a[1 + nin:])]
                res = lanewise(cond_call)
            elif k == 'index': res = [[bv(i, st.outputs_types[0]) for i in range(n)]]
            elif k == 'gather':
                value, index, default = args
                out = []
                for i, j in enumerate(index):
                    r = default[i]
                    for jj in range(len(value)):
                        r = z3.If(j == jj, value[jj], r)
                    out.append(z3.simplify(r))
                res = [out]
            elif k == 'replicate': res = [[args[0][0]] * n]
            elif k == 'extract_first': res = [args[0][:n]]
            elif k == 'extend_zero': res = [args[0] + [bv(0, st.outputs_types[0])] * (n - len(args[0]))]
            elif k == 'fold':
                width = len(st.outputs)
                state = [a[0] for a in args[:width]]
                vectors = args[width:]
                for lane in range(len(vectors[0])):
                    state = self.run_op(self.m.ops[spec], state + [v[lane] for v in vectors])[:width]
                res = [[v] for v in state]
            else:
                raise OutOfScope(k)
            assert len(res) == len(st.outputs), st
            for name, w, v in zip(st.outputs, st.outputs_types, res):
                assert all(x.size() == w for x in v), (st, v)
                vals[name] = v
        return [outputs[i] for i in sorted(outputs)]

    # -- instructions ----------------------------------------------------------
    def execute(self, ins: Instruction, operands: List[z3.BitVecRef]):
        self.run(ins.semantic, [[o] for o in operands])

    def operand_constraint(self, ins: Instruction, operands: List[z3.BitVecRef]) -> z3.BoolRef:
        c = ins.encoding.constraint_encode
        if not c:
            return z3.BoolVal(True)
        return self.run(self.m.snippets[c].seq, [[o] for o in operands])[0][0] == 1


def operand_terms(ins: Instruction, fixed: Dict[str, int]) -> List[z3.BitVecRef]:
    """The operands: the `fixed` ones constants, the others free variables
    named after their encoding field."""
    return [bv(fixed[n], w) if n in fixed else z3.BitVec(n, w)
            for n, w in zip(ins.operand_names, ins.operand_sizes)]


def uses(ins: Instruction) -> Tuple[set, set, bool]:
    """(register files, environment functions, uses fop) of an instruction."""
    files = {s.specifier for s in ins.semantic.stmts if s.kind in ('read', 'write')}
    hooks = {s.specifier for s in ins.semantic.stmts if s.kind in ('env', 'cond_env')}
    return files, hooks, any(s.kind == 'fop' for s in ins.semantic.stmts)


def in_scope(ins: Instruction) -> bool:
    files, hooks, fp = uses(ins)
    return not fp and files <= set(REG_FILES) and hooks <= HOOKS


class Raised(Exception):
    """An exception of the concrete reference run."""

    def __init__(self, kind, imm=None):
        super().__init__(kind, imm)
        self.kind, self.imm = kind, imm


def concrete_step(arch: Arch, ins: Instruction, ops: List[int], x: List[int], nzcv: int, pc: int, byte):
    """lira_interp with the walker's environment, `byte(addr)` the initial
    memory: (X[0..31], NZCV, next PC, {address: byte written}) or Raised."""
    m64 = (1 << 64) - 1
    m = Machine(arch)
    m.regs['X'][:] = x
    m.regs['NZCV'][0] = nzcv
    written, branch = {}, []

    def at(a):
        a &= m64
        return written[a] if a in written else byte(a)

    def rd(n):
        return lambda addr: [sum(at(addr + i) << 8 * i for i in range(n // 8))]

    def wr(n):
        def f(addr, v):
            for i in range(n // 8):
                written[(addr + i) & m64] = v >> 8 * i & 0xff
        return f

    def raise_(kind, imm=None):
        raise Raised(kind, imm)

    def align(addr, size, exclusive):
        exc = addr % size != 0 if exclusive else addr % 16 + size > 16
        if exc:
            raise Raised('alignment')

    for n in (8, 16, 32, 64, 128):
        m.env[f'mem_read_{n}'], m.env[f'mem_write_{n}'] = rd(n), wr(n)
    m.env.update({
        'pc_read': lambda: [pc], 'pc_write': lambda t: branch.append(t),
        'supervisor_call': lambda imm: raise_('svc', imm),
        'exception_call': lambda kind, imm: raise_(EXCEPTION_CALL_KINDS[kind], imm),
        'exception_return': lambda kind: raise_('undefined'), 'debug_state': lambda kind: raise_('undefined'),
        'check_alignment': align,
        **{h: lambda *a: None for h in ('barrier', 'hint', 'branch_target', 'wait_timeout')}})
    try:
        m.execute(ins, ops)
    except Raised as e:
        return e
    return list(m.regs['X']), m.regs['NZCV'][0], branch[-1] if branch else (pc + 4) & m64, written
