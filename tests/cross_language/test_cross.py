import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from python.lira import arch_ser_yaml

CROSS_DIR = Path(__file__).parent
REFERENCE = CROSS_DIR.parent / "integration" / "reference.yaml"
TMP_DIR = ROOT / "tmp"
TMP_DIR.mkdir(exist_ok=True)

PY_OUT = TMP_DIR / "py_native.yaml"
RB_OUT = TMP_DIR / "rb_native.yaml"
RS_OUT = TMP_DIR / "rs_native.yaml"


def test_python_write_and_self_read():
    arch = arch_ser_yaml.read_arch(REFERENCE)
    arch_ser_yaml.copy_arch(REFERENCE, PY_OUT)
    arch2 = arch_ser_yaml.read_arch(PY_OUT)
    assert arch == arch2


def test_python_reads_ruby():
    if not RB_OUT.exists():
        pytest.skip("rb_native.yaml not found")
    arch = arch_ser_yaml.read_arch(RB_OUT)
    arch_ser_yaml.copy_arch(RB_OUT, TMP_DIR / "py_from_rb.yaml")
    arch2 = arch_ser_yaml.read_arch(TMP_DIR / "py_from_rb.yaml")
    assert arch == arch2


def test_python_reads_rust():
    if not RS_OUT.exists():
        pytest.skip("rs_native.yaml not found")
    arch = arch_ser_yaml.read_arch(RS_OUT)
    arch_ser_yaml.copy_arch(RS_OUT, TMP_DIR / "py_from_rs.yaml")
    arch2 = arch_ser_yaml.read_arch(TMP_DIR / "py_from_rs.yaml")
    assert arch == arch2
