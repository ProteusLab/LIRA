from typing import Optional
from dataclasses import dataclass, field

from lira.ir import *

@dataclass
class Component:
    name: str
    # Common interpretation of an argument: `$(<part>).*`
    #  e.g. `pc.read`, `pc.write`, `kind.float`, `kind.mem.read`
    attributes: list[str] # = field(default_factory=list)

@dataclass
class Snippet:
    name: str
    seq: StatementSeq

@dataclass
class Operation(Component):
    inputs: list[int]
    outputs: list[int]
    semantic_base: Optional[str] = None
    semantic_func: Optional[str] = None # Snippet
    semantic_func_128: Optional[str] = None # Snippet
    semantic_table: Optional[str] = None # TableInt

    def __eq__(self, other):
        if not isinstance(other, Operation):
            return NotImplemented
        return (self.name, self.attributes, self.inputs, self.outputs,
                self.semantic_base, self.semantic_func,
                self.semantic_func_128, self.semantic_table) == \
               (other.name, other.attributes, other.inputs, other.outputs,
                other.semantic_base, other.semantic_func,
                other.semantic_func_128, other.semantic_table)


@dataclass
class Register(Component):
    def __init__(self, name, attributes: list[str] = []):
        super().__init__(name=name, attributes=attributes)

@dataclass
class RegisterFile(Component):
    reg_size: Shape
    regs: list[Register]

    def reg_names(self) -> list[str]:
        return [r.name for r in self.regs]

    def regs_num(self) -> int:
        return len(self.regs)

@dataclass
class EnvironmentFunction(Component):
    inputs: list[int]
    outputs: list[int]

@dataclass
class SystemRegisterField(Component):
    lsb: int
    msb: int
@dataclass
class SystemRegister(Component):
    size: int
    fields: list[SystemRegisterField]

@dataclass
class TableInt(Component):
    values: list[int]

@dataclass
class InstructionEncoding:
    encoded_size: int
    # Used to reuse same encode/constraint_decode for multiple instructions
    const_encoding_part: int
    const_mask: int
    # `[encoding_size -> operand_size]`
    decode: list[str] # Snippet
    # `[operand_size] -> encoding_size`
    encode: str # Snippet
    # `[encoding_size -> 1]`
    constraint_decode: str # Snippet
    # `[operand_size] -> 1`
    constraint_encode: str # Snippet

@dataclass
class Instruction(Component):
    operand_sizes: list[int]
    operand_names: list[str]

    encoding: InstructionEncoding
    # disassemble is relatively simple, but defining assembling...
    # syntax: InstructionSyntax

    semantic: StatementSeq

@dataclass
class Arch(Component):
    # Constant Architecture part
    register_files: list[RegisterFile]
    system_registers: list[SystemRegister]
    environment_functions: list[EnvironmentFunction]

    # Variable Architecture part
    # Same architecture can be defined with different instruction grouping
    tables_int: list[TableInt]
    operations: list[Operation]
    snippets: list[Snippet]
    instructions: list[Instruction]
