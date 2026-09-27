import random
from pathlib import Path

import pytest

from python.lira.arch_ser_yaml import read_arch

from .lira_interp import Machine

YAML = Path(__file__).resolve().parents[1] / 'aarch64.yaml'


@pytest.fixture(scope='session')
def arch():
    return read_arch(YAML)


@pytest.fixture
def machine(arch):
    return Machine(arch)


def sample_operands(machine, ins, rng: random.Random, fixed=None):
    """Random operand values accepted by the instruction's constraint_encode."""
    fixed = fixed or {}
    for _ in range(10000):
        ops = [fixed.get(n, rng.getrandbits(w)) for n, w in zip(ins.operand_names, ins.operand_sizes)]
        if machine.valid_operands(ins, ops):
            return ops
    raise AssertionError(f'no valid operands for {ins.name} with {fixed}')
