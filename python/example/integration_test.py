assert __name__ == '__main__'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lira.arch_ser_txt import *
from lira.ir_ser_txt import *
from lira.ir import *
from lira.arch import *


assert len(sys.argv) == 2
arch_dir = Path(sys.argv[1])

rf = RegisterFile('X', [], Shape(32, False), [f'x{i}' for i in range(32)])
ld32 = EnvironmentFunction('ld32', ['mem.read'], [32], [32])
st32 = EnvironmentFunction('st32', ['mem.write'], [32, 32], [])
pc_read = EnvironmentFunction('pc_read', ['pc.read'], [], [32])
pc_write = EnvironmentFunction('pc_write', ['pc.write'], [32], [])

ops = []
for name, inputs, output, base in [
    ('add_32', [32, 32], 32, 'add'),
    ('lsl_32', [32, 32], 32, 'lsl'),
    ('lsr_32', [32, 32], 32, 'lsr'),
    ('asr_32', [32, 32], 32, 'asr'),
    ('slt_32', [32, 32], 1, 'slt'),
    ('extract_low_5_32', [32], 5, 'extract_low'),
]:
    ops.append(Operation(name, [], inputs, [output], base))

def sem(code: list[str]):
    return StatementSeq([deserialize_statement(stmt) for stmt in code])

snippets = []
def add_snippet(name: str, code: list[str]):
    snippets.append(Snippet(name, sem(code)))

add_snippet('op_extend_sign_inner_32', [
    '1 32 input = input 0',
    '1 32 width = input 1',
    '1 32 c32 = const 32',
    '1 32 delta = sub_32 c32 width',
    '1 32 temp = lsl_32 input delta',
    '1 32 r = asr_32 temp delta',
    '1 = output r',
])
ops.append(Operation('extend_sign_inner_32', [], [32, 32], [32], None, 'op_extend_sign_inner_32'))

add_snippet('op_extract_inner_32', [
    '1 32 input = input 0',
    '1 32 lsb = input 1',
    '1 32 width = input 2',
    '1 32 new_lsb = input 3',
    '1 32 c32 = const 32',
    '1 32 t1 = sub_32 c32 lsb',
    '1 32 shift_l = sub_32 t1 width',
    '1 32 temp = lsl_32 input shift_l', # input << (32 - lsb - width)
    '1 32 shift_r = sub_32 c32 width',
    '1 32 temp2 = lsr_32 temp shift_r',     # (input >> lsb) & ((1 << width) - 1)
    '1 = output r',
])
# eii(input, lsb, width, new_lsb) extracts width bits from input at offset lsb
ops.append(Operation('extract_inner_32', [], [32, 32, 32], [32], None, 'op_extract_inner_32'))
add_snippet('op_orr_shifted_32', [
    '1 32 data = input 0',
    '1 32 lsb = input 1',
    '1 32 value = input 2',
    '1 32 insert = lsl_32 value lsb',
    '1 32 r = orr_32 data insert',
    '1 = output r',
])
ops.append(Operation('orr_shifted_32', [], [32, 32, 32], [32], None, 'op_orr_shifted_32'))


def add_snippet_extract(name: str, input: int, lsb: int, output: int):
    add_snippet(name, [
        f'1 {input} enc = input 0',
        f'1 {input} shift = const {lsb}',
        f'1 {input} shifted = op lsr_{input} enc shift',
        f'1 {output} r = op extract_low_{output}_{input} shifted',
        '1 = output r',
    ])

for i, lsb in [(1, 15), (2, 20)]:
    add_snippet_extract(f'decode_b_rs{i}', 32, lsb, 5)
# Yes, IR designed for (vector) instruction analysis doesn't look great
#   in the context of instruction encoding/decoding, that's true.
add_snippet('decode_b_imm', [
    '1 32 enc = input 0',
    '1 32 c1 = const 1',
    '1 32 c4 = const 4',
    '1 32 c5 = const 5',
    '1 32 c6 = const 6',
    '1 32 c7 = const 7',
    '1 32 c8 = const 8',
    '1 32 c11 = const 11',
    '1 32 c12 = const 12',
    '1 32 c13 = const 13',
    '1 32 c25 = const 25',
    '1 32 c31 = const 31',
    '1 32 t1 = op extract_inner_32 enc c31 c1',
    '1 32 t2 = op extract_inner_32 enc c25 c6',
    '1 32 t3 = op extract_inner_32 enc c8 c4',
    '1 32 t4 = op extract_inner_32 enc c7 c1',
    '1 32 t5 = const 0',
    '1 32 t6 = op orr_shifted_32 t5 t1 c12',
    '1 32 t7 = op orr_shifted_32 t5 t1 c11',
    '1 32 t8 = op orr_shifted_32 t5 t1 c5',
    '1 32 t9 = op orr_shifted_32 t5 t1 c1',
    '1 32 imm_sext = op extend_sign_inner_32 t9 c13',
    '1 = output imm_sext',
])
add_snippet('encode_b', [
    '1 5 rs1 = input 0',
    '1 5 rs2 = input 2',
    '1 32 imm = input 2',
    '1 32 base = dyn_const enc_base',
    '1 32 c15 = const 15',
    '1 32 c20 = const 20',
    '1 32 t1 = op orr_shifted base rs1 c15',
    '1 32 t2 = op orr_shifted t1 rs2 c20',
    '1 32 r = todo todo t2 imm', # that's a pain to write by hand..
    '1 = output r',
])

def enc_b(funct3: int, opcode: int):
    return InstructionEncoding(32, (funct3 << 12) + opcode,
        ['decode_b_rs1', 'decode_b_rs2', 'decode_b_imm'], 'encode_b', '', ''
    )

instrs = []
instrs.append(Instruction('blt', ['kind.branch.cond'],
    [5, 5, 32], ['x1', 'x2', 'offset'], enc_b(0b100, 0b1100011), sem([
        '1 5 x1 = input 0',
        '1 5 x2 = input 1',
        '1 5 offset = input 2',
        '1 32 v1 = read X x1',
        '1 32 v2 = read X x2',
        '1 1 cond = op slt_32 v1 v2',
        '1 32 base = env pc_read',
        '1 32 dest = op add_32 base offset',
        '1 = cond_env pc_write cond dest',
    ])
))

arch = Arch(
    name='test_arch',
    attributes=['attr.1', 'attr.2'],
    register_files=[rf],
    system_registers=[],
    environment_functions=[ld32, st32],
    tables_int=[],
    operations=ops,
    snippets=snippets,
    instructions=instrs,
)

write_arch(arch, arch_dir)
arch2 = read_arch(arch_dir)

assert arch.register_files == arch2.register_files
assert arch.system_registers == arch2.system_registers
assert arch.environment_functions == arch2.environment_functions
assert arch.tables_int == arch2.tables_int
assert arch.operations == arch2.operations
assert arch.snippets == arch2.snippets
assert arch.instructions == arch2.instructions
assert arch == arch2
