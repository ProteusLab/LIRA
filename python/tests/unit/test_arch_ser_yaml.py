import sys, tempfile
from pathlib import Path

import pytest

from python.lira.ir import Shape
from python.lira.arch import (
    Register,
    RegisterFile,
    EnvironmentFunction,
    InstructionEncoding,
    SystemRegister,
    SystemRegisterField,
    TableInt,
)
from python.lira.ir_builder import ArchBuilder, SnippetBuilder, InstructionBuilder
from python.lira.ir_ops import (
    Add,
    Lsl,
    Lsr,
    Orr,
    And,
    Eq,
    Select,
    ExtractLow,
    ExtendZero,
    ExtendSign,
)
from python.lira import arch_ser_yaml


@pytest.fixture
def tmp_yaml():
    tmp = Path(tempfile.mktemp(suffix=".yaml"))
    yield tmp
    tmp.unlink(missing_ok=True)


def _build_decode_0_snippet():
    sb = SnippetBuilder("decode_0")
    enc = sb.input(0, 32)
    c7 = sb.const(7, 32)
    shifted = sb.lsr(enc, c7)
    low5 = sb.extract_low(shifted, 5)
    extended = sb.extend_zero(low5, 32)
    sb.output(extended, 0)
    return sb.build()


def _build_decode_4_snippet():
    sb = SnippetBuilder("decode_4")
    enc = sb.input(0, 32)
    c20 = sb.const(20, 32)
    shifted = sb.lsr(enc, c20)
    low12 = sb.extract_low(shifted, 12)
    extended = sb.extend_sign(low12, 32)
    sb.output(extended, 0)
    return sb.build()


def _build_constraint_36_snippet():
    sb = SnippetBuilder("constraint_36")
    enc = sb.input(0, 32)
    mask = sb.const(28799, 32)
    masked = sb.and_(enc, mask)
    expected = sb.const(20483, 32)
    ok = sb.eq(masked, expected)
    sb.output(ok, 0)
    return sb.build()


@pytest.fixture(scope="module")
def rv32i_arch_lite():
    rf = RegisterFile(
        "XRegs",
        [],
        Shape(32, None),
        [Register("x0", ["zero"])] + [Register(f"x{i}") for i in range(1, 32)],
    )

    ab = ArchBuilder("rv32i_lite", [])
    ab.add_register_file(rf)

    syscall = EnvironmentFunction("sysCall", [], [], [])
    read_mem = EnvironmentFunction("readMem16", [], [32], [16])
    get_pc = EnvironmentFunction("getPC", [], [], [32])
    set_pc = EnvironmentFunction("setPC", [], [32], [])
    ab.add_env_func(syscall)
    ab.add_env_func(read_mem)
    ab.add_env_func(get_pc)
    ab.add_env_func(set_pc)

    ab.add_operation(Add(32))
    ab.add_operation(Lsr(32))
    ab.add_operation(Lsl(32))
    ab.add_operation(Orr(32))
    ab.add_operation(And(32))
    ab.add_operation(Eq(32))
    ab.add_operation(Select(32))
    ab.add_operation(ExtractLow(32, 5))
    ab.add_operation(ExtractLow(32, 12))
    ab.add_operation(ExtendZero(5, 32))
    ab.add_operation(ExtendZero(16, 32))
    ab.add_operation(ExtendZero(1, 32))
    ab.add_operation(ExtendSign(12, 32))

    ab.add_snippet(_build_decode_0_snippet())
    ab.add_snippet(_build_decode_4_snippet())
    ab.add_snippet(_build_constraint_36_snippet())

    # add instruction
    enc = InstructionEncoding(32, 51, 4261441663, ["decode_0"], "", "", "")
    ib = InstructionBuilder("add", [32, 32, 32], ["rs2", "rs1", "rd"], enc)
    rs2 = ib.add_input_operand(0, 32)
    rs1 = ib.add_input_operand(1, 32)
    rd = ib.add_input_operand(2, 32)
    v1 = ib.read(rf, rs1)
    v2 = ib.read(rf, rs2)
    r = ib.add(v1, v2)
    ib.write(rf, rd, r)
    ab.add_instruction(ib.build())

    # lhu instruction
    enc = InstructionEncoding(32, 20483, 28799, ["decode_4"], "", "", "")
    ib = InstructionBuilder("lhu", [32, 32, 32], ["imm", "rs1", "rd"], enc)
    imm = ib.add_input_operand(0, 32)
    rs1 = ib.add_input_operand(1, 32)
    rd = ib.add_input_operand(2, 32)
    v = ib.read(rf, rs1)
    addr = ib.add(v, imm)
    val16 = ib.env(read_mem, [addr])
    r = ib.extend_zero(val16[0], 32)
    ib.write(rf, rd, r)
    ab.add_instruction(ib.build())

    # beq instruction
    enc = InstructionEncoding(32, 99, 28799, ["decode_0"], "", "", "")
    ib = InstructionBuilder("beq", [32, 32, 32], ["imm", "rs1", "rs2"], enc)
    imm = ib.add_input_operand(0, 32)
    rs1 = ib.add_input_operand(1, 32)
    rs2 = ib.add_input_operand(2, 32)
    v1 = ib.read(rf, rs1)
    v2 = ib.read(rf, rs2)
    eq = ib.eq(v1, v2)
    base = ib.env(get_pc, [])
    dest = ib.add(base[0], imm)
    c4 = ib.const(4, 32)
    fallback = ib.add(base[0], c4)
    ib.cond_env(set_pc, eq, [dest], [fallback])
    ab.add_instruction(ib.build())

    # ecall instruction
    enc = InstructionEncoding(32, 115, 0xFFFFFFFF, [], "", "", "")
    ib = InstructionBuilder("ecall", [], [], enc)
    ib.env(syscall, [])
    ab.add_instruction(ib.build())

    return ab.build()


class TestArchSerYaml:
    def test_minimal_arch_with_builder(self, tmp_yaml):
        rf = RegisterFile("X", [], Shape(32, None), [Register("x0"), Register("x1")])
        ab = ArchBuilder("minimal", [])
        ab.add_register_file(rf)
        sb = SnippetBuilder("s")
        a = sb.input(0, 32)
        sb.output(a, 0)
        ab.add_snippet(sb.build())
        arch = ab.build()
        arch_ser_yaml.write_arch(arch, tmp_yaml)
        arch2 = arch_ser_yaml.read_arch(tmp_yaml)
        assert arch == arch2

    def test_instruction_via_builder(self, tmp_yaml):
        rf = RegisterFile("X", [], Shape(32, None), [Register("x0")])
        enc = InstructionEncoding(32, 0, 0, [], "", "", "")
        ib = InstructionBuilder("test", [5, 5], ["rs1", "rs2"], enc)
        rs1 = ib.add_input_operand(0, 5)
        rs2 = ib.add_input_operand(1, 5)
        v = ib.read(rf, rs1)
        ib.write(rf, rs2, v)
        instr = ib.build()
        ab = ArchBuilder("w_instr", [])
        ab.add_register_file(rf)
        ab.add_instruction(instr)
        arch = ab.build()
        arch_ser_yaml.write_arch(arch, tmp_yaml)
        arch2 = arch_ser_yaml.read_arch(tmp_yaml)
        assert arch == arch2

    def test_null_fields_roundtrip(self, tmp_yaml):
        op = Add(32)
        op.semantic_base = None
        op.semantic_func = None
        ab = ArchBuilder("null_test", [])
        ab.add_operation(op)
        arch = ab.build()
        arch_ser_yaml.write_arch(arch, tmp_yaml)
        arch2 = arch_ser_yaml.read_arch(tmp_yaml)
        assert arch2.operations[0].semantic_base is None

    def test_register_attributes(self, tmp_yaml):
        rf = RegisterFile(
            "R", [], Shape(32, None), [Register("x0", ["zero"]), Register("x1", [])]
        )
        ab = ArchBuilder("attrs", [])
        ab.add_register_file(rf)
        arch = ab.build()
        arch_ser_yaml.write_arch(arch, tmp_yaml)
        arch2 = arch_ser_yaml.read_arch(tmp_yaml)
        assert arch2.register_files[0].regs[0].attributes == ["zero"]

    def test_system_register(self, tmp_yaml):
        field = SystemRegisterField("f", [], 0, 7)
        sr = SystemRegister("csr", [], 32, [field])
        ab = ArchBuilder("sysreg", [])
        ab.add_system_register(sr)
        arch = ab.build()
        arch_ser_yaml.write_arch(arch, tmp_yaml)
        arch2 = arch_ser_yaml.read_arch(tmp_yaml)
        assert arch2.system_registers[0].fields[0].lsb == 0

    def test_table_int(self, tmp_yaml):
        table = TableInt("t", [], [1, 2, 3])
        ab = ArchBuilder("tbl", [])
        ab.add_table_int(table)
        arch = ab.build()
        arch_ser_yaml.write_arch(arch, tmp_yaml)
        arch2 = arch_ser_yaml.read_arch(tmp_yaml)
        assert arch2.tables_int[0].values == [1, 2, 3]

    def test_rv32i_lite_roundtrip(self, rv32i_arch_lite, tmp_yaml):
        arch_ser_yaml.write_arch(rv32i_arch_lite, tmp_yaml)
        arch2 = arch_ser_yaml.read_arch(tmp_yaml)
        assert rv32i_arch_lite == arch2
        assert arch2.instructions[0].name == "add"
        assert arch2.instructions[1].name == "lhu"
        assert arch2.instructions[2].name == "beq"
        assert arch2.instructions[3].name == "ecall"
