import subprocess, sys
from pathlib import Path

from python.lira import arch_ser_yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
REFERENCE = PROJECT_ROOT / "tests" / "integration" / "reference.yaml"
CANONICALIZE = PROJECT_ROOT / "tools" / "yaml_canonicalize.py"


def test_integration():
    ref_arch = arch_ser_yaml.read_arch(REFERENCE)

    output = PROJECT_ROOT / "python" / "tests" / "integration" / "integration.yaml"
    raw = output.with_suffix(".raw.yaml")
    try:
        arch_ser_yaml.write_arch(ref_arch, raw)
        subprocess.run(
            [sys.executable, str(CANONICALIZE), str(raw), str(output)], check=True
        )
        raw.unlink()

        arch2 = arch_ser_yaml.read_arch(output)
        assert ref_arch == arch2, "Round-trip failed"
    finally:
        raw.unlink(missing_ok=True)
