"""The symbolic walker (lira_smt) agrees with the reference interpreter.

For every instruction the walker models, random register fields are fixed and
the other operands, registers, PC and memory are left symbolic; substituting a
random concrete state into the resulting terms must give what lira_interp
computes for that state: registers, next PC, memory writes, or the exception.
"""
import random

import pytest

z3 = pytest.importorskip('z3')

from .conftest import sample_operands                                       # noqa: E402
from .lira_interp import Machine                                            # noqa: E402
from .lira_smt import (REG_FIELDS, Raised, SymMachine, bv, concrete_step, in_scope,  # noqa: E402
                       operand_terms)
from .test_semantics_hw import EDGE                                         # noqa: E402

CASES_PER_INSN = 3
STATES_PER_CASE = 4
WINDOW, WINDOW_SIZE = 0x10000, 256
M64 = (1 << 64) - 1


def concrete(arch, ins, ops, st):
    """lira_interp on the state: memory is the window over zeros."""
    def byte(a):
        o = a - WINDOW
        return st['MEM'][o] if 0 <= o < WINDOW_SIZE else 0
    return concrete_step(arch, ins, ops, st['X'], st['NZCV'], st['PC'], byte)


def symbolic_step(sm: SymMachine, st, fields, ops):
    """The walker's result with the state `st` and operand values substituted."""
    mem = z3.K(z3.BitVecSort(64), bv(0, 8))
    for i, b in enumerate(st['MEM']):
        mem = z3.Store(mem, bv(WINDOW + i, 64), bv(b, 8))
    sub = [(sm.inputs[k], v) for k, v in [
        *[(f'X{i}', bv(x, 64)) for i, x in enumerate(st['X'][:31])], ('SP', bv(st['X'][31], 64)),
        ('NZCV', bv(st['NZCV'], 4)), ('PC', bv(st['PC'], 64)), ('MEM', mem)] if k in sm.inputs]
    sub += [(z3.BitVec(n, w), bv(v, w)) for n, w, v in fields]
    val = lambda t: z3.simplify(z3.substitute(t, *sub))                      # noqa: E731
    for e in sm.exceptions:
        if z3.is_true(val(e.cond)):
            return Raised(e.kind, None if e.imm is None else val(e.imm).as_long())
    regs = sm.written()
    x = [val(regs['SP' if i == 31 else f'X{i}']).as_long() if ('SP' if i == 31 else f'X{i}') in regs
         else st['X'][i] for i in range(32)]
    nzcv = val(regs['NZCV']).as_long() if 'NZCV' in regs else st['NZCV']
    written = {}
    for w in sm.writes:
        if z3.is_true(val(w.guard)):
            a, v = val(w.addr).as_long(), val(w.value).as_long()
            for i in range(w.value.size() // 8):
                written[(a + i) & M64] = v >> 8 * i & 0xff
    return x, nzcv, val(sm.next_pc).as_long(), written


def random_state(rng):
    pick = lambda: rng.choice([rng.getrandbits(64), rng.choice(EDGE),          # noqa: E731
                               WINDOW + rng.randrange(-16, WINDOW_SIZE + 16)])
    return {'X': [pick() for _ in range(32)], 'NZCV': rng.getrandbits(4), 'PC': rng.getrandbits(62) << 2,
            'MEM': bytes(rng.getrandbits(8) for _ in range(WINDOW_SIZE))}


def test_walker_matches_interpreter(arch):
    machine = Machine(arch)
    rng = random.Random(7)
    scope = [i for i in arch.instructions if in_scope(i)]
    assert len(scope) > 450
    failures = []
    for ins in scope:
        for _ in range(CASES_PER_INSN):
            ops = sample_operands(machine, ins, rng)
            fixed = {n: v for n, v in zip(ins.operand_names, ops) if n in REG_FIELDS}
            fields = [(n, w, v) for n, w, v in zip(ins.operand_names, ins.operand_sizes, ops) if n not in fixed]
            sm = SymMachine(arch)
            sm.execute(ins, operand_terms(ins, fixed))
            for _ in range(STATES_PER_CASE):
                st = random_state(rng)
                want = concrete(arch, ins, ops, st)
                got = symbolic_step(sm, st, fields, ops)
                same = (got.kind, got.imm) == (want.kind, want.imm) if isinstance(want, Raised) and \
                    isinstance(got, Raised) else got == want
                if not same:
                    failures.append((ins.name, dict(zip(ins.operand_names, ops)), got, want))
                    break
            else:
                continue
            break
    assert not failures, '\n'.join(map(str, failures[:20])) + f'\n({len(failures)} failing)'
