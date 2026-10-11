"""Differential test of the SME instructions: LIRA semantics vs. QEMU.

The harness of test_semantics_sve.py with SME states: x0..x15 (W12..W15 select
ZA slices), SVCR and ZA as well. A stub first writes SVCR (entering streaming
mode resets the SVE state), loads the registers and ZA, and after the word
stores them, then leaves with SMSTOP. ZA is compared when it is enabled after
the word. Streaming mode has the vector length (SMCR_EL1.LEN = ZCR_EL1.LEN) and
FEAT_SME_FA64, as the description assumes. PSTATE.SM and PSTATE.ZA are each off
in some states, so that SME access traps are compared (by syndrome) too.

$LIRA_SVE_VQS (powers of two only) and $LIRA_SVE_ONLY apply.
"""
import random
import re

import pytest

from .conftest import sample_operands
from .test_semantics_sve import (EDGE, REG_FIELDS, VQS, ONLY, Layout, M64, _lanes, check_results,
                                 mem_case_states, random_state, run_qemu)

pytestmark = pytest.mark.skipif(not any(v & (v - 1) == 0 for v in VQS),
                                reason='streaming vector lengths are powers of two')

CASES_PER_INSN = 6
STATES_PER_CASE = 8
SME_INSNS = re.compile(r'(SMSTART|SMSTOP)_|.*_SVCR$|(revd|psel|sclamp|uclamp)_')


def is_sme(ins):
    return 'instr-class.mortlach' in ins.attributes or bool(SME_INSNS.match(ins.name))


def is_mem(ins):
    return is_sme(ins) and re.match(r'(ld|st)(1[bhwdq]|r)_za', ins.name) is not None


def pick_operands(machine, ins, rng):
    fixed = {n: rng.randrange(8) for n in ins.operand_names if n in REG_FIELDS | {'Rt'}}
    return sample_operands(machine, ins, rng, fixed)


def _index(rng):
    """A slice index register: small, an edge value or random."""
    r = rng.random()
    if r < 0.5:
        return rng.randrange(64)
    if r < 0.7:
        return rng.choice((0xffffffff, 0x7fffffff, 0x80000000, 0xfffffff0, 1 << 32 | 3))
    return rng.getrandbits(64)


def random_sme_state(rng, vq):
    st = random_state(rng, vq)
    st['X'] += [rng.choice(EDGE) if rng.random() < 0.3 else rng.getrandbits(64) for _ in range(4)]
    st['X'] += [_index(rng) for _ in range(4)]                      # x12..x15
    st['SVCR'] = int(rng.random() < 0.85) | int(rng.random() < 0.85) << 1
    vl = 128 * vq
    st['ZA'] = sum(_lanes(rng, vl) << (r * vl) for r in range(vl // 8))
    return st


TSIZE = {'b': 8, 'h': 16, 'w': 32, 'd': 64, 'q': 128}


def random_sme_mem_state(rng, vq, ins, ops):
    """Base register in the window, a small index register X[m].

    QEMU (seen in 10.0.2, sme_ld1) does not zero the inactive elements after
    the last active one of a vertical tile slice load: the last element of
    vertical LD1 slices is kept active."""
    L = Layout(vq, True)
    st = random_sme_state(rng, vq)
    names = dict(zip(ins.operand_names, ops))
    st['X'][names['Rn']] = L.w0 + rng.randrange(L.win)
    if 'Rm' in names:
        st['X'][names['Rm']] = rng.randrange(16) if rng.random() < 0.8 else rng.randrange(-16, 0) & M64
    if ins.name.startswith('ld1') and names.get('V') == 1:
        st['P'][names['Pg']] |= 1 << (2 * vq * 8 - TSIZE[ins.name[3]] // 8)
    st['MEM'] = bytes(rng.getrandbits(8) for _ in range(L.win))
    return st


@pytest.mark.parametrize('vq', [v for v in VQS if v & (v - 1) == 0])
def test_sme_semantics_match_qemu(arch, machine, vq, tmp_path):
    rng = random.Random(200 + vq)
    cases, meta = [], []
    for ins in arch.instructions:
        if not is_sme(ins) or not ONLY.search(ins.name):
            continue
        for _ in range(CASES_PER_INSN):
            ops = pick_operands(machine, ins, rng)
            word = machine.encode(ins, ops)
            if is_mem(ins):
                pairs = mem_case_states(arch, rng, vq, ins, ops, word, STATES_PER_CASE,
                                        random_sme_mem_state)
            else:
                pairs = [(random_sme_state(rng, vq), None) for _ in range(STATES_PER_CASE)]
            cases.append((word, is_mem(ins), [st for st, _ in pairs]))
            meta.append((ins, ops, [exp for _, exp in pairs]))
    assert cases, 'no SME instruction selected'
    check_results(arch, vq, cases, meta, run_qemu(tmp_path, cases, vq, sme=True))
