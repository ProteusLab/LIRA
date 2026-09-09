import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.lira.arch_ser_yaml import copy_arch


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('Usage: copy_.py <INPUT> <OUTPUT>')
    copy_arch(Path(sys.argv[1]), Path(sys.argv[2]))
