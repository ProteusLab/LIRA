import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "python"))

from lira import arch_ser_yaml

CROSS_DIR = Path(__file__).parent
REFERENCE = Path(__file__).parent.parent / "integration" / "reference.yaml"

PY_OUT = CROSS_DIR / "py_native.yaml"
RB_OUT = CROSS_DIR / "rb_native.yaml"
RS_OUT = CROSS_DIR / "rs_native.yaml"


def test_python_write_and_self_read():
    arch = arch_ser_yaml.read_arch(REFERENCE)
    arch_ser_yaml.write_arch(arch, PY_OUT)
    arch2 = arch_ser_yaml.read_arch(PY_OUT)
    assert arch == arch2


def test_python_reads_ruby():
    if not RB_OUT.exists():
        pytest.skip("rb_native.yaml not found")
    arch = arch_ser_yaml.read_arch(RB_OUT)
    arch_ser_yaml.write_arch(arch, CROSS_DIR / "py_from_rb.yaml")
    arch2 = arch_ser_yaml.read_arch(CROSS_DIR / "py_from_rb.yaml")
    assert arch == arch2


def test_python_reads_rust():
    if not RS_OUT.exists():
        pytest.skip("rs_native.yaml not found")
    arch = arch_ser_yaml.read_arch(RS_OUT)
    arch_ser_yaml.write_arch(arch, CROSS_DIR / "py_from_rs.yaml")
    arch2 = arch_ser_yaml.read_arch(CROSS_DIR / "py_from_rs.yaml")
    assert arch == arch2
