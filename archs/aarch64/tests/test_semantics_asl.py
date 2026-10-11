"""Differential test of LIRA semantics against the Arm ASL, run in aslref.

The ASL is the reference: it is the pseudocode the description is written from
(asl_oracle.py runs it). The comparison covers the whole state the description
models: X0..X30, SP, Z0..Z31, P0..P15, FFR, NZCV, FPCR, FPSR, SVCR, ZA (when
enabled) and the memory window; an exception must be the same (ESR) and a data
abort must be one on both sides. The QEMU tests (test_semantics_sve.py,
test_semantics_sme.py) are a further check against an implementation.

The instructions are those of test_semantics_sme.py with its states.
$LIRA_SVE_VQS (powers of two) and $LIRA_SVE_ONLY apply.
"""
import random

import pytest

from . import asl_oracle
from .lira_interp import Machine
from .test_semantics_sme import is_mem, is_sme, pick_operands, random_sme_mem_state, random_sme_state
from .test_semantics_sve import ONLY, VQS, Fault, Layout, Memory, SmeTrap, mem_case_states

pytestmark = pytest.mark.skipif(not asl_oracle.available(),
                                reason='needs aslref ($ASLREF) and the ASL bundle ($LIRA_ASL_BUNDLE)')

CASES_PER_INSN = 4
STATES_PER_CASE = 6
BIG_VQ = 8                  # from this VQ on (ZA of 32 KiB or more), 2 cases of 2 states


def lira_state(arch, ins, word, st, vq):
    """The state after the word in the reference interpreter, 'fault' or
    ('exception', ESR)."""
    m = Machine(arch, vq)
    m.regs['X'][:len(st['X'])] = st['X']
    m.regs['Z'][:len(st['Z'])] = st['Z']
    m.regs['P'][:len(st['P'])] = st['P']
    m.regs['FFR'][0] = st['FFR']
    for k in ('NZCV', 'FPCR', 'FPSR', 'SVCR', 'ZA'):
        m.regs[k][0] = st.get(k, 0)
    mem = Memory(Layout(vq), st['MEM']) if 'MEM' in st else None
    if mem:
        for n in (8, 16, 32, 64, 128):
            m.env[f'mem_read_{n}'], m.env[f'mem_write_{n}'] = mem.read(n), mem.write(n)
    m.env['sme_access_trap'] = lambda kind: (_ for _ in ()).throw(SmeTrap(kind))
    try:
        m.execute(ins, m.decode(ins, word))
    except Fault:
        return 'fault'
    except SmeTrap as e:
        return ('exception', e.esr)
    out = {'X': m.regs['X'][:31], 'SP': m.regs['X'][31], 'Z': list(m.regs['Z']), 'P': list(m.regs['P']),
           **{k: m.regs[k][0] for k in ('FFR', 'NZCV', 'FPCR', 'FPSR', 'SVCR', 'ZA')}}
    if mem:
        out['MEM'] = bytes(mem.data)
    return out


def diff(asl, lira):
    if not isinstance(asl, dict) or not isinstance(lira, dict):
        fmt = lambda r: r if r == 'fault' else f'ESR {r[1]:#x}' if isinstance(r, tuple) else 'no exception'
        return [] if asl == lira else [f'ASL {fmt(asl)}, LIRA {fmt(lira)}']
    d = []
    for k in ('X', 'Z', 'P'):
        d += [f'{k}{i}: {a:#x} vs {b:#x}' for i, (a, b) in enumerate(zip(asl[k], lira[k])) if a != b]
    d += [f'{k}: {asl[k]:#x} vs {lira[k]:#x}' for k in ('SP', 'FFR', 'NZCV', 'FPCR', 'FPSR', 'SVCR')
          if asl[k] != lira[k]]
    if asl['SVCR'] & 2 and asl['ZA'] != lira['ZA']:          # ZA is ARBITRARY when off
        x = asl['ZA'] ^ lira['ZA']
        bad = [i for i in range((x.bit_length() + 7) // 8) if x >> (8 * i) & 0xff]
        d.append('ZA bytes: ' + ', '.join(f'{i:#x}: {asl["ZA"] >> 8 * i & 0xff:#04x} vs '
                                           f'{lira["ZA"] >> 8 * i & 0xff:#04x}' for i in bad[:4]))
    if 'MEM' in lira and asl['MEM'] != lira['MEM']:
        bad = [i for i, (a, b) in enumerate(zip(asl['MEM'], lira['MEM'])) if a != b]
        d.append('memory: ' + ', '.join(f'{i:#x}: {asl["MEM"][i]:#04x} vs {lira["MEM"][i]:#04x}'
                                        for i in bad[:4]))
    return d


@pytest.mark.parametrize('vq', [v for v in VQS if v & (v - 1) == 0])
def test_sme_semantics_match_asl(arch, machine, vq, tmp_path):
    rng = random.Random(300 + vq)
    functions = asl_oracle.Functions()
    cases, meta = [], []
    for ins in arch.instructions:
        if not is_sme(ins) or not ONLY.search(ins.name):
            continue
        n_cases, n_states = (CASES_PER_INSN, STATES_PER_CASE) if vq < BIG_VQ else (2, 2)
        for _ in range(n_cases):
            ops = pick_operands(machine, ins, rng)
            word = machine.encode(ins, ops)
            if is_mem(ins):
                states = [st for st, _ in mem_case_states(arch, rng, vq, ins, ops, word, n_states,
                                                          random_sme_mem_state)]
                for st in states:
                    st['W0'] = Layout(vq).w0
            else:
                states = [random_sme_state(rng, vq) for _ in range(n_states)]
            for st in states:
                cases.append((ins.name, word, st))
                meta.append((ins, ops))
    assert cases, 'no SME instruction selected'
    results = asl_oracle.run(cases, vq, tmp_path, functions)
    failures, seen = [], set()
    for (name, word, st), (ins, ops), asl in zip(cases, meta, results):
        if name in seen:
            continue
        d = diff(asl, lira_state(arch, ins, word, st, vq))
        if d:
            seen.add(name)
            failures.append((name, hex(word), dict(zip(ins.operand_names, ops)), 'asl vs lira:', d[:6]))
    summary = ' '.join(sorted(seen))
    assert not failures, '\n'.join(map(str, failures[:30])) + f'\n({len(failures)} failing)\n' + summary
