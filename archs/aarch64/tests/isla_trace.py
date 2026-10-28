"""Isla traces as z3 terms.

isla-footprint prints, for a partially symbolic opcode, `(segments (|f| w vN)
...)` and one `(trace ...)` per path of the Sail model: SMT declarations,
definitions and assertions (the path condition) interleaved with register and
memory events. `paths` replays each trace over the shared initial state of
lira_smt (X0..X30, SP, NZCV, PC, MEM and the opcode fields, by name): the first
value read from a register (or, for PSTATE, seen in it before a write) is its
initial value, a read from memory is the bytes of the memory written so far,
and the last write of a register is its final value.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import z3

from .lira_smt import MEM_SORT

TOKEN = re.compile(r'\s+|;[^\n]*|(\()|(\))|(\|[^|]*\|)|("(?:[^"\\]|\\.)*")|([^\s()|";]+)')

# Sail register -> LIRA input
GPRS = {f'R{i}': f'X{i}' for i in range(31)}
NZCV_FIELDS = ('N', 'Z', 'C', 'V')                  # NZCV bits 3..0
# Sail state the instruction may change that LIRA does not describe
BOOKKEEPING = re.compile(r'^(__\w+|SEE|InGuardedPage|Branchtypetaken|BTypeNext|BTypeCompleted|'
                         r'ShouldAdvanceIT|ShouldAdvanceSS|SPESampleInFlight|EventRegister|BTypeCompatible|'
                         r'IsWFEsleep|IsWFIsleep|_DormantCtlReg)$')      # the last: WFE/WFI sleeping
UNPREDICTABLE = ('ConstrainUnpredictable', 'ConstrainUnpredictableBool', 'ConstrainUnpredictableInteger',
                 'ConstrainUnpredictableBits')
OTHER_ERROR = 'lira_other_error'          # isla_oracle.LIRA_CAUGHT


class TraceError(Exception):
    pass


def parse(text: str):
    """S-expressions of `text`: lists, and atoms as strings (|quoted| symbols
    keep their bars)."""
    stack, cur = [], []
    for m in TOKEN.finditer(text):
        lp, rp, q, s, a = m.groups()
        if lp:
            stack.append(cur)
            cur = []
        elif rp:
            done, cur = cur, stack.pop()
            cur.append(done)
        elif q or s or a:
            cur.append(q or s or a)
    if stack:
        raise TraceError('unbalanced parentheses (truncated trace?)')
    return cur


def unbar(s: str) -> str:
    return s[1:-1] if s.startswith('|') and s.endswith('|') else s


@dataclass
class Path:
    """One path of the Sail model, over the shared initial state."""
    index: int
    cond: List[z3.BoolRef] = field(default_factory=list)        # path condition
    binds: List[z3.BoolRef] = field(default_factory=list)       # trace values = initial state
    final: Dict[str, z3.BitVecRef] = field(default_factory=dict)  # X0.., SP, NZCV written
    next_pc: Optional[z3.BitVecRef] = None                      # _PC written (branch)
    mem: z3.ArrayRef = None                                     # memory after the writes
    mem_writes: int = 0
    exception: Optional[str] = None                             # exceptype
    esr: Optional[z3.BitVecRef] = None
    unmapped_writes: Dict[str, str] = field(default_factory=dict)
    unbound_reads: List[str] = field(default_factory=list)      # symbolic state LIRA lacks
    calls: set = field(default_factory=set)
    init_vars: set = field(default_factory=set)                 # declared at reset, before (cycle)
    choices: List[z3.ExprRef] = field(default_factory=list)     # UNKNOWN enumeration values chosen

    @property
    def unpredictable(self) -> bool:
        return any(c in self.calls for c in UNPREDICTABLE)

    @property
    def other_error(self) -> bool:
        return OTHER_ERROR in self.calls


class Translator:
    """SMT expressions and values of one trace to z3."""
    enums: Dict[Tuple[str, Tuple[str, ...]], z3.DatatypeSortRef] = {}     # shared: z3 sorts are global

    def __init__(self, segments: Dict[str, z3.BitVecRef], location):
        self.env: Dict[str, z3.ExprRef] = dict(segments)
        self.location = location             # (|imm6| nil), (|R1| nil): a field or register
        self.members: Dict[str, z3.ExprRef] = {}
        self.sorts: Dict[str, z3.SortRef] = {}

    def enum(self, name, members):
        key = (name, tuple(members))
        if key not in Translator.enums:
            sort, consts = z3.EnumSort(f'{name}_{len(Translator.enums)}', list(members))
            Translator.enums[key] = (sort, consts)
        sort, consts = Translator.enums[key]
        self.sorts[name] = sort
        self.members.update(zip(members, consts))

    def sort(self, ty):
        if ty == 'Bool':
            return z3.BoolSort()
        if isinstance(ty, list) and ty[:2] == ['_', 'BitVec']:
            return z3.BitVecSort(int(ty[2]))
        if isinstance(ty, str) and unbar(ty) in self.sorts:
            return self.sorts[unbar(ty)]
        raise TraceError(f'type {ty}')

    def declare(self, var, ty):
        if var not in self.env:
            self.env[var] = z3.Const(f'isla_{var}', self.sort(ty))

    def exp(self, e) -> z3.ExprRef:
        if isinstance(e, str):
            if e in self.env:
                return self.env[e]
            if e == 'true':
                return z3.BoolVal(True)
            if e == 'false':
                return z3.BoolVal(False)
            if e.startswith('#x'):
                return z3.BitVecVal(int(e[2:], 16), 4 * (len(e) - 2))
            if e.startswith('#b'):
                return z3.BitVecVal(int(e[2:], 2), len(e) - 2)
            if unbar(e) in self.members:
                return self.members[unbar(e)]
            raise TraceError(f'unknown atom {e}')
        head = e[0]
        if len(e) >= 3 and e[1] == '@':                               # (x @ y @ ...): concatenation
            return z3.Concat(*[self.exp(x) for x in e[0::2]])
        if len(e) == 2 and e[1] == 'nil' and isinstance(head, str) and head.startswith('|'):
            return self.location(unbar(head))
        if head == '_' and e[1].startswith('bv'):                     # (_ bvN W), N may be negative
            w = int(e[2])
            return z3.BitVecVal(int(e[1][2:]) % (1 << w), w)
        if isinstance(head, list):                                    # ((_ extract i j) x) ...
            op, x = head, self.exp(e[1])
            if op[1] == 'extract':
                return z3.Extract(int(op[2]), int(op[3]), x)
            if op[1] == 'zero_extend':
                return z3.ZeroExt(int(op[2]), x) if int(op[2]) else x
            if op[1] == 'sign_extend':
                return z3.SignExt(int(op[2]), x) if int(op[2]) else x
            if op[1] == 'rotate_left':
                return z3.RotateLeft(x, int(op[2]))
            if op[1] == 'rotate_right':
                return z3.RotateRight(x, int(op[2]))
            if op[1] == 'repeat':
                return z3.Concat(*[x] * int(op[2])) if int(op[2]) > 1 else x
            raise TraceError(f'operator {op}')
        a = [self.exp(x) for x in e[1:]]
        f = OPS.get(head)
        if f is None:
            raise TraceError(f'operator {head}')
        return f(*a)

    def value(self, v):
        """An event value: a z3 term, a dict for a struct, or None for what
        the comparison does not use (unions, vectors, unit)."""
        if isinstance(v, list) and v[:2] == ['_', 'struct']:
            return {unbar(f[0]): self.value(f[1]) for f in v[2:]}
        if isinstance(v, list) and (v[:1] == ['_'] and v[1] in ('vec', 'unit', 'poison') or
                                    isinstance(v[0], str) and v[0].startswith('|')):
            return None
        return self.exp(v)


def _chain(f):
    return lambda *a: _fold(f, a)


def _fold(f, a):
    r = a[0]
    for x in a[1:]:
        r = f(r, x)
    return r


OPS = {
    'not': z3.Not, 'and': z3.And, 'or': z3.Or, 'xor': _chain(z3.Xor), '=>': z3.Implies,
    '=': lambda x, *ys: z3.And(*[x == y for y in ys]) if len(ys) > 1 else x == ys[0],
    'distinct': z3.Distinct, 'ite': z3.If,
    'bvnot': lambda x: ~x, 'bvneg': lambda x: -x,
    'bvand': _chain(lambda x, y: x & y), 'bvor': _chain(lambda x, y: x | y), 'bvxor': _chain(lambda x, y: x ^ y),
    'bvnand': lambda x, y: ~(x & y), 'bvnor': lambda x, y: ~(x | y), 'bvxnor': lambda x, y: ~(x ^ y),
    'bvadd': _chain(lambda x, y: x + y), 'bvsub': lambda x, y: x - y, 'bvmul': _chain(lambda x, y: x * y),
    'bvudiv': z3.UDiv, 'bvsdiv': lambda x, y: x / y, 'bvurem': z3.URem, 'bvsrem': z3.SRem,
    'bvsmod': lambda x, y: x % y,
    'bvshl': lambda x, y: x << y, 'bvlshr': z3.LShR, 'bvashr': lambda x, y: x >> y,
    'concat': lambda *a: z3.Concat(*a) if len(a) > 1 else a[0],
    'bvult': z3.ULT, 'bvule': z3.ULE, 'bvugt': z3.UGT, 'bvuge': z3.UGE,
    'bvslt': lambda x, y: x < y, 'bvsle': lambda x, y: x <= y, 'bvsgt': lambda x, y: x > y,
    'bvsge': lambda x, y: x >= y,
    'select': z3.Select, 'store': z3.Store,
}


def consts(*es) -> List[z3.ExprRef]:
    """The uninterpreted constants (variables) in the expressions."""
    seen, out, todo = set(), {}, list(es)
    while todo:
        e = todo.pop()
        if e.get_id() in seen:
            continue
        seen.add(e.get_id())
        if z3.is_const(e) and e.decl().kind() == z3.Z3_OP_UNINTERPRETED:
            out[e.decl().name()] = e
        todo.extend(e.children())
    return list(out.values())


def symbolic(v) -> bool:
    """Whether an event value depends on a free variable."""
    if isinstance(v, dict):
        return any(symbolic(x) for x in v.values())
    if not isinstance(v, z3.ExprRef):
        return False
    s = z3.simplify(v)
    return not (z3.is_bv_value(s) or z3.is_true(s) or z3.is_false(s) or
                z3.is_app(s) and s.decl().kind() == z3.Z3_OP_DT_CONSTRUCTOR)


def le_bytes(mem, addr, n):
    bs = [z3.Select(mem, addr + i) for i in range(n)]
    return z3.Concat(*reversed(bs)) if n > 1 else bs[0]


def store_bytes(mem, addr, data, n):
    for i in range(n):
        mem = z3.Store(mem, addr + i, z3.Extract(8 * i + 7, 8 * i, data))
    return mem


def paths(text: str, inputs: Dict[str, z3.ExprRef], segments: Dict[str, z3.BitVecRef]) -> List[Path]:
    """The paths of an isla-footprint output. `inputs` are lira_smt's initial
    state terms (created as needed), `segments` the opcode field variables."""
    sexps = parse(text)
    seg_vars = {}
    for s in sexps:
        if s and s[0] == 'segments':
            for name, _w, var in s[1:]:
                seg_vars[var] = segments[unbar(name)]
    out = []
    for s in sexps:
        if s and s[0] == 'trace':
            out.append(replay(len(out), s[1:], inputs, seg_vars, segments))
    return out


def _input(inputs, name, sort=None):
    if name not in inputs:
        inputs[name] = z3.Const(name, z3.BitVecSort(64) if sort is None else sort)
    return inputs[name]


def replay(index: int, events, inputs, seg_vars, segments) -> Path:
    def location(name):
        if name in segments:
            return segments[name]
        reg = GPRS.get(name) or {'SP_EL0': 'SP', '_PC': 'PC'}.get(name)
        if reg is None:
            raise TraceError(f'location {name}')
        return _input(inputs, reg)

    t = Translator(seg_vars, location)
    p = Path(index)
    mem = _input(inputs, 'MEM', MEM_SORT)
    seen = set()                 # registers (and PSTATE fields) read or written so far
    in_init = True
    fresh = set()                # the free Booleans declared after the reset

    def bind(name, value, width):
        if name not in seen:
            seen.add(name)
            p.binds.append(value == _input(inputs, name, z3.BitVecSort(width)))

    def pstate(value, written_fields):
        if isinstance(value, dict):
            for f in NZCV_FIELDS:
                if f not in seen and f in value and f not in written_fields:
                    seen.add(f)
                    p.binds.append(value[f] == z3.Extract(3 - NZCV_FIELDS.index(f), 3 - NZCV_FIELDS.index(f),
                                                          _input(inputs, 'NZCV', z3.BitVecSort(4))))

    for ev in events:
        kind = ev[0]
        if kind == 'declare-const':
            t.declare(ev[1], ev[2])
            if in_init:
                p.init_vars.add(f'isla_{ev[1]}')
            elif ev[2] == 'Bool':
                fresh.add(f'isla_{ev[1]}')
        elif kind == 'cycle':
            in_init = False
        elif kind == 'define-const':
            e = t.env[ev[1]] = t.exp(ev[-1])
            # an UNKNOWN enumeration value (ConstrainUnpredictable's choice):
            # an ite over free Booleans
            if isinstance(e.sort(), z3.DatatypeSortRef) and not z3.is_const(e):
                vs = consts(e)
                if vs and all(v.decl().name() in fresh for v in vs):
                    p.choices.append(e)
        elif kind == 'define-enum':
            t.enum(unbar(ev[1]), [unbar(m) for m in ev[3]])
        elif kind in ('assert', 'assume'):
            p.cond.append(t.exp(ev[1]))
        elif kind == 'read-reg':
            reg, acc, val = unbar(ev[1]), ev[2], t.value(ev[3])
            if reg in GPRS:
                bind(GPRS[reg], val, 64)
            elif reg == 'SP_EL0':
                bind('SP', val, 64)
            elif reg == '_PC':
                bind('PC', val, 64)
            elif reg == 'PSTATE':
                pstate(val, ())
            elif reg not in seen and symbolic(val):
                p.unbound_reads.append(reg)
            seen.add(reg)
        elif kind == 'write-reg':
            reg, acc, val = unbar(ev[1]), ev[2], t.value(ev[3])
            if reg in GPRS:
                seen.add(GPRS[reg])
                p.final[GPRS[reg]] = val
            elif reg == 'SP_EL0':
                seen.add('SP')
                p.final['SP'] = val
            elif reg == '_PC':
                p.next_pc = val
            elif reg == 'PSTATE':
                fld = unbar(acc[0][2]) if acc != 'nil' and acc and acc[0][:2] == ['_', 'field'] else None
                pstate(val, (fld,) if fld else NZCV_FIELDS)
                if fld in NZCV_FIELDS or fld is None:
                    p.final['NZCV'] = z3.Concat(*[val[f] for f in NZCV_FIELDS])
                    seen.update(NZCV_FIELDS if fld is None else (fld,))
                elif p.exception is None:
                    p.unmapped_writes[f'PSTATE.{fld}'] = str(val.get(fld))
            elif reg == 'ESR_EL1':
                p.esr = val['bits'] if isinstance(val, dict) else val
            elif not BOOKKEEPING.match(reg) and p.exception is None:
                p.unmapped_writes[reg] = str(val)
        elif kind == 'read-mem':
            value, addr, n = t.exp(ev[1]), t.exp(ev[3]), int(ev[4])
            p.binds.append(value == le_bytes(mem, addr, n))
        elif kind == 'write-mem':
            addr, data, n = t.exp(ev[3]), t.exp(ev[4]), int(ev[5])
            mem = store_bytes(mem, addr, data, n)
            p.mem_writes += 1
        elif kind == 'abstract-primop' and unbar(ev[1]) == 'sail_take_exception':
            rec = t.value(ev[3])
            exc = rec['exception'] if isinstance(rec, dict) else None
            p.exception = str(exc['exceptype']) if exc else 'unknown'
        elif kind == 'call':
            p.calls.add(unbar(ev[1]))
        # branch, branch-address, cycle, assume-reg, return, instr, mark-reg,
        # function-assumption, use-function-assumption: nothing to replay
    p.mem = mem
    return p


# -----------------------------------------------------------------------------
# z3 -> Isla SMT (for --instruction-constraint: binary operators, no `let`)

def to_isla(e: z3.ExprRef) -> str:
    if z3.is_true(e):
        return 'true'
    if z3.is_false(e):
        return 'false'
    if z3.is_bv_value(e):
        return '#b' + format(e.as_long(), f'0{e.size()}b')
    if z3.is_const(e):
        return e.decl().name()
    k = e.decl().kind()
    args = [to_isla(a) for a in e.children()]
    if k == z3.Z3_OP_EXTRACT:
        hi, lo = e.params()
        return f'((_ extract {hi} {lo}) {args[0]})'
    if k == z3.Z3_OP_ZERO_EXT:
        return f'((_ zero_extend {e.params()[0]}) {args[0]})'
    if k == z3.Z3_OP_SIGN_EXT:
        return f'((_ sign_extend {e.params()[0]}) {args[0]})'
    if k == z3.Z3_OP_DISTINCT and len(args) == 2:
        return f'(not (= {args[0]} {args[1]}))'
    name = {z3.Z3_OP_NOT: 'not', z3.Z3_OP_AND: 'and', z3.Z3_OP_OR: 'or', z3.Z3_OP_EQ: '=',
            z3.Z3_OP_ITE: 'ite', z3.Z3_OP_BNOT: 'bvnot', z3.Z3_OP_BNEG: 'bvneg', z3.Z3_OP_BAND: 'bvand',
            z3.Z3_OP_BOR: 'bvor', z3.Z3_OP_BXOR: 'bvxor', z3.Z3_OP_BADD: 'bvadd', z3.Z3_OP_BSUB: 'bvsub',
            z3.Z3_OP_BMUL: 'bvmul', z3.Z3_OP_CONCAT: 'concat', z3.Z3_OP_ULT: 'bvult', z3.Z3_OP_ULEQ: 'bvule',
            z3.Z3_OP_UGT: 'bvugt', z3.Z3_OP_UGEQ: 'bvuge', z3.Z3_OP_SLT: 'bvslt', z3.Z3_OP_SLEQ: 'bvsle',
            z3.Z3_OP_SGT: 'bvsgt', z3.Z3_OP_SGEQ: 'bvsge', z3.Z3_OP_BSHL: 'bvshl', z3.Z3_OP_BLSHR: 'bvlshr',
            z3.Z3_OP_BASHR: 'bvashr', z3.Z3_OP_BUDIV: 'bvudiv', z3.Z3_OP_BUREM: 'bvurem'}.get(k)
    if name is None:
        raise TraceError(f'no Isla form for {e.decl()}')
    if name in ('not', 'bvnot', 'bvneg', 'ite', 'and', 'or') or len(args) <= 2:
        return f'({name} {" ".join(args)})'
    return _fold(lambda x, y: f'({name} {x} {y})', args)        # Isla's are binary
