assert __name__ == '__main__'

import sys
from pathlib import Path

from lira import arch_ser_yaml

assert len(sys.argv) == 3, 'copy.py <INPUT> <OUTPUT>'

path_input = Path(sys.argv[1])
path_output = Path(sys.argv[2])

ref_arch = arch_ser_yaml.read_arch(path_input)
arch_ser_yaml.write_arch(ref_arch, path_output)
