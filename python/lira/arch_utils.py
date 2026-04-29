from lira.arch import *

from typing import Dict

@dataclass
class ArchIndex:
    rf: Dict[str, RegisterFile]
    sr: Dict[str, SystemRegister]
    env: Dict[str, EnvironmentFunction]
    tables: Dict[str, TableInt]
    op: Dict[str, Operation]
    snippet: Dict[str, Snippet]
    instr: Dict[str, Instruction]

def build_arch_index(arch: Arch) -> ArchIndex:
    """Build index dictionaries from an Arch."""
    return ArchIndex(
        rf={rf.name: rf for rf in arch.register_files},
        sr={sr.name: sr for sr in arch.system_registers},
        env={ef.name: ef for ef in arch.environment_functions},
        tables={ti.name: ti for ti in arch.tables_int},
        op={op.name: op for op in arch.operations},
        snippet={sn.name: sn for sn in arch.snippets},
        instr={ins.name: ins for ins in arch.instructions},
    )
