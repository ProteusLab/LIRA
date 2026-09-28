"""AArch64 architectural state and shared semantic building blocks for LIRA.

State model
-----------
* `X`    - 32 x 64-bit registers: x0..x30 and `sp` at index 31. The A64 encoding
           value 31 means either SP or XZR depending on the instruction; XZR is
           not a storage element, it is expressed in semantics (see S.x_read /
           S.x_write).
* `NZCV` - one 4-bit register holding PSTATE.{N,Z,C,V} (N is bit 3).
* `V`    - 32 x 128-bit SIMD&FP registers. Scalar B/H/S/D views are the low
           bits; writing a scalar clears the upper bits (FPCR.NEP = 0).
* `FPCR`, `FPSR` - FP control/status (32 bits each). Their attributes bind the
           FPU state used by `fop` statements (see LIRA docs/float_ops.md).
* PC and memory are environment functions (`pc_read`, `pc_write`,
  `mem_read_<n>`, `mem_write_<n>`); if `pc_write` is not called, the
  environment advances PC by 4.

Helper ASL functions (AddWithCarry, ShiftReg, ExtendReg, DecodeBitMasks,
ConditionHolds, ...) are pure `Operation`s whose semantics are snippets.
"""
from typing import Callable, Dict, List, Optional

from python.lira.ir import Shape
from python.lira.arch import (EnvironmentFunction, FloatOperation, Operation, Register,
                              RegisterFile, Snippet, TableInt)
from python.lira import float_ops
from python.lira.ir_builder import BaseBuilder, SnippetBuilder, Value
from python.lira.ir_ser_txt import serialize_statement_seq
from python.lira import ir_ops


def _mask(w: int) -> int:
    return (1 << w) - 1


class Ctx:
    """Collects everything that ends up in the Arch besides instructions."""

    def __init__(self):
        regs = [Register(f'x{i}', ['lr'] if i == 30 else []) for i in range(31)]
        regs.append(Register('sp', ['sp']))
        self.rf_x = RegisterFile('X', ['gpr'], Shape(64, None), regs)
        self.rf_nzcv = RegisterFile('NZCV', ['flags'], Shape(4, None), [Register('nzcv', ['flags'])])
        self.rf_v = RegisterFile('V', ['simdfp'], Shape(128, None),
                                 [Register(f'v{i}', []) for i in range(32)])
        self.rf_fpcr = RegisterFile('FPCR', ['sysreg'], Shape(32, None), [Register('fpcr', [
            'fpu.control', 'fpu.rmode@22+2', 'fpu.fz@24', 'fpu.fz16@19', 'fpu.dn@25'])])
        self.rf_fpsr = RegisterFile('FPSR', ['sysreg'], Shape(32, None), [Register('fpsr', [
            'fpu.status', 'fpu.flag.invalid@0', 'fpu.flag.divbyzero@1', 'fpu.flag.overflow@2',
            'fpu.flag.underflow@3', 'fpu.flag.inexact@4', 'fpu.flag.input_denormal@7'])])
        self.fops: Dict[str, FloatOperation] = {}
        self.tables: Dict[str, TableInt] = {}

        self.envs: Dict[str, EnvironmentFunction] = {}
        self.env_pc_read = self._env('pc_read', ['pc.read'], [], [64])
        self.env_pc_write = self._env('pc_write', ['pc.write'], [64], [])
        self.env_svc = self._env('supervisor_call', ['exception.svc'], [16], [])
        for n in (8, 16, 32, 64, 128):
            self._env(f'mem_read_{n}', ['mem.read'], [64], [n])
            self._env(f'mem_write_{n}', ['mem.write'], [64, n], [])
        # Environment hooks for behaviour outside the instruction semantics
        # (memory system, pointer authentication keys, exceptions, system state)
        # Alignment rules of ordered/atomic (FEAT_LSE2: within 16 bytes) and
        # exclusive (natural) accesses; a violation is an Alignment fault
        self._env('check_alignment', ['mem.align'], [64, 8, 1], [])      # addr, bytes, exclusive
        self._env('exclusive_mark', ['mem.exclusive'], [64, 8], [])        # addr, bytes
        self._env('exclusive_check', ['mem.exclusive'], [64, 8], [1])      # pass; clears
        self._env('exclusive_clear', ['mem.exclusive'], [], [])
        self._env('mem_copy', ['mem.read', 'mem.write'], [64, 64, 64, 1], [])  # dst, src, n, may overlap
        self._env('mem_set', ['mem.write'], [64, 64, 8], [])               # dst, n, byte
        self._env('pac_add', ['pauth'], [64, 64, 3], [64])                 # ptr, modifier, key
        self._env('pac_auth', ['pauth'], [64, 64, 3], [64])
        self._env('pac_strip', ['pauth'], [64, 1], [64])                   # ptr, is_data
        self._env('pac_generic', ['pauth'], [64, 64], [64])                # PACGA
        self._env('barrier', ['sys.barrier'], [4, 4], [])                  # kind, CRm
        self._env('hint', ['sys.hint'], [7], [])                           # CRm:op2 (WFE, SEV, ...)
        self._env('wait_timeout', ['sys.hint'], [1, 64], [])               # WFET/WFIT
        self._env('branch_target', ['sys.bti'], [2], [])                   # BTI landing pad
        self._env('exception_call', ['exception'], [3, 16], [])            # BRK/HLT/HVC/SMC/UDF
        self._env('exception_return', ['exception', 'pc.write'], [2], [])  # ERET/ERETAA/ERETAB/DRPS
        self._env('debug_state', ['exception'], [2], [])                   # DCPS1..3
        self._env('sys_op', ['sys.op'], [3, 4, 4, 3, 64], [])              # SYS: op1 CRn CRm op2 Xt
        self._env('sys_op_read', ['sys.op'], [3, 4, 4, 3], [64])           # SYSL
        self._env('sysreg_read', ['sys.reg'], [1, 3, 4, 4, 3], [64])       # MRS: o0 op1 CRn CRm op2
        self._env('sysreg_write', ['sys.reg'], [1, 3, 4, 4, 3, 64], [])
        self._env('pstate_write', ['sys.pstate'], [3, 3, 4], [])           # MSR (imm): op1 op2 CRm

        self.ops: Dict[str, Operation] = {}
        self.snippets: Dict[str, Snippet] = {}
        self._snippet_by_body: Dict[str, str] = {}
        self._builders: Dict[str, Callable] = {}

    def _env(self, name, attrs, ins, outs) -> EnvironmentFunction:
        e = EnvironmentFunction(name, attrs, ins, outs)
        self.envs[name] = e
        return e

    # -- operations / snippets ---------------------------------------------
    def collect_ops(self, b: BaseBuilder):
        for op in b.operations_map.values():
            prev = self.ops.setdefault(op.name, op)
            assert prev == op, f'conflicting definitions of operation {op.name}'
        for fop in b.float_operations_map.values():
            prev = self.fops.setdefault(fop.name, fop)
            assert prev == fop, f'conflicting definitions of float operation {fop.name}'

    def add_snippet(self, b: SnippetBuilder, dedup: bool = True) -> str:
        """Register a snippet; identical bodies are shared. Returns its name."""
        self.collect_ops(b)
        snip = b.build()
        body = serialize_statement_seq(snip.seq)
        if dedup and body in self._snippet_by_body:
            return self._snippet_by_body[body]
        assert snip.name not in self.snippets, snip.name
        self.snippets[snip.name] = snip
        self._snippet_by_body.setdefault(body, snip.name)
        return snip.name

    def table_op(self, name: str, in_width: int, out_width: int, values: List[int]) -> Operation:
        """Operation defined by a lookup table (`semantic_table`)."""
        if name not in self.ops:
            assert len(values) == 1 << in_width
            self.tables[name] = TableInt(name, [], list(values))
            self.ops[name] = Operation(name, [], [in_width], [out_width], semantic_table=name)
        return self.ops[name]

    def func_op(self, name: str, inputs: List[int], outputs: List[int],
                body: Callable[['S', List[Value]], List[Value]]) -> Operation:
        """Get (building on first use) an operation defined by a snippet."""
        if name not in self.ops:
            sb = SnippetBuilder(f'op_{name}')
            s = S(self, sb)
            args = [sb.input(i, w) for i, w in enumerate(inputs)]
            res = body(s, args)
            assert [r.width for r in res] == outputs, (name, [r.width for r in res])
            for i, r in enumerate(res):
                sb.output(r, i)
            self.add_snippet(sb, dedup=False)
            self.ops[name] = Operation(name, [], inputs, outputs, semantic_func=f'op_{name}')
        return self.ops[name]


class S:
    """Thin semantic-building layer over a LIRA BaseBuilder."""

    def __init__(self, ctx: Ctx, b: BaseBuilder):
        self.ctx, self.b = ctx, b

    # -- constants and width changes ----------------------------------------
    def c(self, value: int, width: int, shape: Optional[Shape] = None) -> Value:
        """Constant; with `shape` it is replicated to all lanes."""
        return self.b.const(value & _mask(width), width, shape or Shape(1, None))

    def cl(self, value: int, like: Value, width: Optional[int] = None) -> Value:
        """Constant with the shape (and by default the width) of `like`."""
        return self.c(value, width or like.width, like.shape)

    def zext(self, v: Value, w: int) -> Value:
        return v if v.width == w else self.b.extend_zero(v, w)

    def sext(self, v: Value, w: int) -> Value:
        return v if v.width == w else self.b.extend_sign(v, w)

    def trunc(self, v: Value, w: int) -> Value:
        return v if v.width == w else self.b.extract_low(v, w)

    def bits(self, v: Value, lo: int, width: int) -> Value:
        """v[lo+width-1:lo]"""
        if lo:
            v = self.b.lsr(v, self.cl(lo, v))
        return self.trunc(v, width)

    def bit_at(self, v: Value, pos: Value) -> Value:
        """v[pos] for a dynamic position (pos < width)."""
        return self.trunc(self.b.lsr(v, self.zext(pos, v.width)), 1)

    def concat(self, *parts: Value) -> Value:
        """parts[0]::parts[1]::... (most significant first)."""
        total = sum(p.width for p in parts)
        acc, lo = None, 0
        for p in reversed(parts):
            v = self.zext(p, total)
            if lo:
                v = self.b.lsl(v, self.c(lo, total, p.shape))
            acc = v if acc is None else self.b.orr(acc, v)
            lo += p.width
        return acc

    def replicate1(self, bit: Value, w: int) -> Value:
        """Replicate a 1-bit value to w bits."""
        return self.b.neg(self.zext(bit, w))

    def eqc(self, v: Value, k: int) -> Value:
        return self.b.eq(v, self.cl(k, v))

    def or1(self, *vs: Value) -> Value:
        acc = vs[0]
        for v in vs[1:]:
            acc = self.b.orr(acc, v)
        return acc

    def and1(self, *vs: Value) -> Value:
        acc = vs[0]
        for v in vs[1:]:
            acc = self.b.and_(acc, v)
        return acc

    # -- pass-through arithmetic ---------------------------------------------
    def __getattr__(self, name):
        return getattr(self.b, name)

    def call(self, op: Operation, args: List[Value]) -> List[Value]:
        self.b._op_cache[op.name] = op
        if len(op.outputs) == 1:
            return [self.b.op(op, args)]
        return self.b.seq.op_multi(op, args)

    # -- architectural state -------------------------------------------------
    def x_read(self, idx: Value, w: int) -> Value:
        """X{w}(idx): register 31 reads as zero (XZR)."""
        v = self.b.read(self.ctx.rf_x, idx)
        v = self.b.select(self.eqc(idx, 31), self.c(0, 64), v)
        return self.trunc(v, w)

    def xsp_read(self, idx: Value, w: int) -> Value:
        """`if n == 31 then SP else X`: register 31 is SP."""
        return self.trunc(self.b.read(self.ctx.rf_x, idx), w)

    def x_write(self, idx: Value, v: Value):
        """X{w}(idx) = v: zero-extends; writes to register 31 (XZR) are discarded."""
        old = self.b.read(self.ctx.rf_x, idx)
        self.b.write(self.ctx.rf_x, idx, self.b.select(self.eqc(idx, 31), old, self.zext(v, 64)))

    def xsp_write(self, idx: Value, v: Value):
        """`if d == 31 then SP = ZeroExtend(v) else X[d] = v`"""
        self.b.write(self.ctx.rf_x, idx, self.zext(v, 64))

    def x_write_n(self, n: int, v: Value):
        self.b.write(self.ctx.rf_x, self.c(n, 5), self.zext(v, 64))

    def flags_read(self) -> Value:
        return self.b.read(self.ctx.rf_nzcv, self.c(0, 1))

    def flags_write(self, nzcv: Value):
        self.b.write(self.ctx.rf_nzcv, self.c(0, 1), nzcv)

    def v_read(self, idx: Value, w: int) -> Value:
        """V{w}(idx): low w bits of a SIMD&FP register."""
        return self.trunc(self.b.read(self.ctx.rf_v, idx), w)

    def v_write(self, idx: Value, v: Value):
        """V{w}(idx) = v: upper bits are cleared."""
        self.b.write(self.ctx.rf_v, idx, self.zext(v, 128))

    def sysreg_read(self, rf: RegisterFile) -> Value:
        return self.b.read(rf, self.c(0, 1))

    def sysreg_write(self, rf: RegisterFile, v: Value):
        self.b.write(rf, self.c(0, 1), v)

    def fop(self, base: str, n: int, args: List[Value], m: Optional[int] = None) -> Value:
        """Standard float operation `<base>_<n>[_to_<m>]` (one output)."""
        fop = float_ops.make(base, n, m)
        assert [a.width for a in args] == fop.inputs, (fop.name, [a.width for a in args])
        return self.b.fop(fop, args)[0]

    def rm(self, mode: int) -> Value:
        """Rounding-mode operand of a float operation (`float_ops.DYN` = FPCR)."""
        return self.c(mode, 3)

    def carry(self) -> Value:
        return self.bits(self.flags_read(), 1, 1)

    def pc(self) -> Value:
        return self.b.env(self.ctx.env_pc_read, [])[0]

    def branch(self, target: Value):
        self.b.env(self.ctx.env_pc_write, [target])

    def branch_if(self, cond: Value, target: Value):
        self.b.cond_env(self.ctx.env_pc_write, cond, [target], [])

    def check_alignment(self, addr: Value, n: int, exclusive: bool = False):
        self.b.env(self.ctx.envs['check_alignment'], [addr, self.c(n // 8, 8), self.c(int(exclusive), 1)])

    def mem_read(self, addr: Value, n: int) -> Value:
        return self.b.env(self.ctx.envs[f'mem_read_{n}'], [addr])[0]

    def mem_write(self, addr: Value, v: Value):
        self.b.env(self.ctx.envs[f'mem_write_{v.width}'], [addr, v])

    # -- ASL helper functions ------------------------------------------------
    def add_with_carry(self, x: Value, y: Value, cin: Value):
        n = x.width
        op = self.ctx.func_op(f'add_with_carry_{n}', [n, n, 1], [n, 4], _add_with_carry)
        return self.call(op, [x, y, cin])

    def shift_reg(self, x: Value, shift_type: Value, amount: Value) -> Value:
        n = x.width
        op = self.ctx.func_op(f'shift_reg_{n}', [n, 2, n], [n], _shift_reg)
        return self.call(op, [x, shift_type, amount])[0]

    def extend_reg(self, x: Value, option: Value, shift: Value) -> Value:
        n = x.width
        op = self.ctx.func_op(f'extend_reg_{n}', [n, 3, 3], [n], _extend_reg)
        return self.call(op, [x, option, shift])[0]

    def condition_holds(self, cond: Value) -> Value:
        op = self.ctx.func_op('condition_holds', [4, 4], [1], _condition_holds)
        return self.call(op, [cond, self.flags_read()])[0]

    def decode_bit_masks(self, immn: Value, imms: Value, immr: Value, m: int):
        op = self.ctx.func_op(f'decode_bit_masks_{m}', [1, 6, 6], [m, m],
                              lambda s, a: [s.trunc(v, m) for v in _decode_bit_masks(s, a)])
        return self.call(op, [immn, imms, immr])

    def logic_imm_valid(self, immn: Value, imms: Value) -> Value:
        op = self.ctx.func_op('logic_imm_valid', [1, 6], [1], _logic_imm_valid)
        return self.call(op, [immn, imms])[0]

    def rev_bytes(self, x: Value, container: int) -> Value:
        n = x.width
        op = self.ctx.func_op(f'rev_bytes_{n}_in_{container}', [n], [n],
                              lambda s, a: [_rev_bytes(s, a[0], container)])
        return self.call(op, [x])[0]

    def cls(self, x: Value) -> Value:
        n = x.width
        op = self.ctx.func_op(f'cls_{n}', [n], [n], _cls)
        return self.call(op, [x])[0]


# -----------------------------------------------------------------------------
# Snippet bodies of helper operations
# -----------------------------------------------------------------------------
def _add_with_carry(s: S, a: List[Value]) -> List[Value]:
    x, y, cin = a
    n = x.width
    r = s.add(s.add(x, y), s.zext(cin, n))
    neg = s.bits(r, n - 1, 1)
    zero = s.eqc(r, 0)
    # unsigned carry out: r < x (cin = 0) or r <= x (cin = 1)
    carry = s.select(cin, s.ule(r, x), s.ult(r, x))
    # signed overflow: operands of equal sign, result of different sign
    ovf = s.bits(s.and_(s.xor(x, r), s.xor(y, r)), n - 1, 1)
    return [r, s.concat(neg, zero, carry, ovf)]


def _shift_reg(s: S, a: List[Value]) -> List[Value]:
    x, t, amount = a
    # DecodeShift: 00 LSL, 01 LSR, 10 ASR, 11 ROR
    r = s.select(s.eqc(t, 0), s.lsl(x, amount),
        s.select(s.eqc(t, 1), s.lsr(x, amount),
        s.select(s.eqc(t, 2), s.asr(x, amount), s.ror(x, amount))))
    return [r]


def _extend_reg(s: S, a: List[Value]) -> List[Value]:
    x, option, shift = a
    n = x.width
    # DecodeRegExtend: option<2> = signed, option<1:0> = log2(len / 8)
    variants = []
    for size in (8, 16, 32, 64):
        low = s.trunc(x, min(size, n))
        variants.append((s.zext(low, n), s.sext(low, n)))
    r = variants[3][0]
    for i in (2, 1, 0):
        r = s.select(s.eqc(s.bits(option, 0, 2), i), variants[i][0], r)
    rs = variants[3][1]
    for i in (2, 1, 0):
        rs = s.select(s.eqc(s.bits(option, 0, 2), i), variants[i][1], rs)
    r = s.select(s.bits(option, 2, 1), rs, r)
    return [s.lsl(r, s.zext(shift, n))]


def _condition_holds(s: S, a: List[Value]) -> List[Value]:
    cond, nzcv = a
    n, z, c, v = (s.bits(nzcv, i, 1) for i in (3, 2, 1, 0))
    base = [
        z,                                   # 000 EQ/NE
        c,                                   # 001 CS/CC
        n,                                   # 010 MI/PL
        v,                                   # 011 VS/VC
        s.and_(c, s.not_(z)),                # 100 HI/LS
        s.eq(n, v),                          # 101 GE/LT
        s.and_(s.eq(n, v), s.not_(z)),       # 110 GT/LE
        s.c(1, 1),                           # 111 AL
    ]
    sel = s.bits(cond, 1, 3)
    r = base[7]
    for i in range(6, -1, -1):
        r = s.select(s.eqc(sel, i), base[i], r)
    invert = s.and_(s.bits(cond, 0, 1), s.not_(s.eqc(cond, 0b1111)))
    return [s.xor(r, invert)]


def _bitmask_len(s: S, immn: Value, imms: Value) -> Value:
    """HighestSetBit(immN:NOT(imms)) as a 64-bit value."""
    v = s.concat(immn, s.not_(imms))                   # 7 bits
    return s.sub(s.c(63, 64), s.clz(s.zext(v, 64)))


def _decode_bit_masks(s: S, a: List[Value]) -> List[Value]:
    immn, imms, immr = a
    ln = _bitmask_len(s, immn, imms)
    one, two = s.c(1, 64), s.c(2, 64)
    esize = s.lsl(one, ln)
    levels = s.sub(esize, one)                          # ZeroExtend(Ones(len))
    S_ = s.and_(s.zext(imms, 64), levels)
    R_ = s.and_(s.zext(immr, 64), levels)
    d = s.and_(s.sub(S_, R_), levels)
    welem = s.sub(s.lsl(two, S_), one)                  # Ones(S + 1), S <= 63
    telem = s.sub(s.lsl(two, d), one)                   # Ones(d + 1)
    emask = s.sub(s.lsl(two, levels), one)              # Ones(esize)
    # ROR within an esize-bit element; shift counts are kept in 0..63
    back = s.and_(s.sub(esize, R_), s.c(63, 64))
    rot = s.and_(s.orr(s.lsr(welem, R_), s.lsl(welem, back)), emask)
    # Replicate: multiply by 0x..0001_0001 pattern = Ones(64) / Ones(esize)
    rep = s.div_u(s.c(-1, 64), emask, s.c(1, 64))
    wmask = s.mul(rot, rep)
    tmask = s.mul(telem, rep)
    return [wmask, tmask]


def _logic_imm_valid(s: S, a: List[Value]) -> List[Value]:
    immn, imms = a
    # len >= 1  <=>  immN:NOT(imms) != '000000x'
    hi = s.concat(immn, s.not_(s.bits(imms, 1, 5)))
    len_ok = s.not_(s.eqc(hi, 0))
    ln = _bitmask_len(s, immn, imms)
    levels = s.sub(s.lsl(s.c(1, 64), ln), s.c(1, 64))
    s_ok = s.not_(s.eq(s.and_(s.zext(imms, 64), levels), levels))
    return [s.and_(len_ok, s_ok)]


def _rev_bytes(s: S, x: Value, container: int) -> Value:
    n = x.width
    step = 8
    while step < container:
        pattern = 0
        for i in range(0, n, 2 * step):
            pattern |= _mask(step) << i
        m = s.c(pattern, n)
        k = s.c(step, n)
        x = s.orr(s.and_(s.lsr(x, k), m), s.lsl(s.and_(x, m), k))
        step *= 2
    return x


def _cls(s: S, a: List[Value]) -> List[Value]:
    x = a[0]
    n = x.width
    # CountLeadingZeroBits(x<n-1:1> EOR x<n-2:0>) computed on n bits
    z = s.lsr(s.xor(x, s.lsl(x, s.c(1, n))), s.c(1, n))
    return [s.sub(s.clz(z), s.c(1, n))]
