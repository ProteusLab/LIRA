"""Symbolic comparison of LIRA semantics with the Sail Arm model (Isla).

isla_oracle.py proves, per instruction and choice of register numbers, that
LIRA and the Sail model agree for all values of the other encoding fields, the
registers, PC and memory, or finds a counterexample. The instructions are those
lira_smt.py models: integer A64 without SIMD&FP, SVE/SME, system registers,
exclusives, PAuth and MOPS. $LIRA_ISLA_ONLY (a regex) restricts them.

Differences that are not LIRA bugs are listed in KNOWN_DIFFERENCES with the
reason, checked against the 2026-06 ASL (the Sail model is from the 2023-03
ASL).
"""
import copy
import os
import re

import pytest

z3 = pytest.importorskip('z3')

from . import isla_oracle as O                     # noqa: E402

pytestmark = pytest.mark.skipif(not O.available(),
                                reason='needs isla-footprint ($ISLA_FOOTPRINT) and the prepared model ($LIRA_ISLA_ARCH)')
ONLY = re.compile(os.environ['LIRA_ISLA_ONLY']) if os.environ.get('LIRA_ISLA_ONLY') else None

# instruction -> why LIRA and Sail differ
KNOWN_DIFFERENCES = {}


def test_semantics_match_sail(arch):
    O.check_prepared()
    results = O.compare_all(arch, ONLY)
    failures = [r for r in results if r.status not in O.PASS and r.name not in KNOWN_DIFFERENCES]
    summary = {}
    for r in results:
        summary[r.status] = summary.get(r.status, 0) + 1
    assert not failures, '\n'.join(f'{r.name} {r.fixed}: {r.status}\n    ' + '\n    '.join(r.detail[:8])
                                   for r in failures[:30]) + f'\n({len(failures)} failing; {summary})'


def mutated(arch, name, old_op, new_op):
    """A copy of instruction `name` whose first `op old_op` is `op new_op`."""
    ins = copy.deepcopy(next(i for i in arch.instructions if i.name == name))
    st = next(s for s in ins.semantic.stmts if s.kind == 'op' and s.specifier == old_op)
    st.specifier = new_op
    return ins


@pytest.mark.parametrize('name, old_op, new_op', [
    ('LDR_64_ldst_immpre', 'add_64', 'sub_64'),          # address
    ('B_only_condbranch', 'add_64', 'sub_64'),           # branch target
])
def test_planted_bug_is_found(arch, name, old_op, new_op):
    """The comparison is not vacuous: a wrong semantics gives a counterexample."""
    O.check_prepared()
    ins = mutated(arch, name, old_op, new_op)
    [r] = O.run_cases([O.make_case(arch, ins, O.combos(ins)[0])])
    assert r.status == 'mismatch', (r.status, r.detail)
    assert any('LIRA replay: agrees' in d for d in r.detail), r.detail
    assert 'confirmed by a concrete Isla run' in r.detail, r.detail
