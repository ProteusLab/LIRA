import pytest

from python.lira.ir import Shape
from python.lira.arch import (
    Register,
    RegisterFile,
    EnvironmentFunction,
    InstructionEncoding,
)
from python.lira.ir_builder import (
    SeqBuilder,
    SnippetBuilder,
    InstructionBuilder,
    ArchBuilder,
)
from python.lira.ir_ops import Add


@pytest.fixture(scope="module")
def rv32i_rf():
    return RegisterFile(
        "XRegs",
        [],
        Shape(32, None),
        [Register("x0", ["zero"])] + [Register(f"x{i}") for i in range(1, 32)],
    )


@pytest.fixture(scope="module")
def rv32i_envs():
    return {
        "sysCall": EnvironmentFunction("sysCall", [], [], []),
        "readMem16": EnvironmentFunction("readMem16", [], [32], [16]),
        "getPC": EnvironmentFunction("getPC", [], [], [32]),
        "setPC": EnvironmentFunction("setPC", [], [32], []),
        "writeMem32": EnvironmentFunction("writeMem32", [], [32, 32], []),
    }


class TestSeqBuilder:
    def test_const(self):
        seq = SeqBuilder()
        v = seq.const(42, 32)
        assert v.width == 32
        assert v.name.startswith("_t")

    def test_add_sub_mul(self):
        seq = SeqBuilder()
        a = seq.const(3, 32)
        b = seq.const(2, 32)
        assert seq.add(a, b).width == 32
        assert seq.sub(a, b).width == 32
        assert seq.mul(a, b).width == 32

    def test_bitwise_ops(self):
        seq = SeqBuilder()
        a = seq.const(0xFF, 32)
        b = seq.const(0x0F, 32)
        assert seq.and_(a, b).width == 32
        assert seq.orr(a, b).width == 32
        assert seq.xor(a, b).width == 32

    def test_shift_ops(self):
        seq = SeqBuilder()
        a = seq.const(1, 32)
        b = seq.const(4, 32)
        assert seq.lsl(a, b).width == 32
        assert seq.lsr(a, b).width == 32
        assert seq.asr(a, b).width == 32

    def test_slt(self):
        seq = SeqBuilder()
        a = seq.const(10, 32)
        b = seq.const(20, 32)
        r = seq.slt(a, b)
        assert r.width == 1

    def test_extract_low(self):
        seq = SeqBuilder()
        a = seq.const(0xFF, 32)
        r = seq.extract_low(a, 8)
        assert r.width == 8

    def test_extend_sign(self):
        seq = SeqBuilder()
        a = seq.const(1, 8)
        r = seq.extend_sign(a, 32)
        assert r.width == 32

    def test_extend_zero(self):
        seq = SeqBuilder()
        a = seq.const(1, 8)
        r = seq.extend_zero(a, 32)
        assert r.width == 32

    def test_input_output(self):
        seq = SeqBuilder()
        inp = seq.input(0, 32)
        seq.output(inp, 0)
        s = seq.build()
        assert s.stmts[0].kind == "input"
        assert s.stmts[1].kind == "output"

    def test_operations_map(self):
        snip = SnippetBuilder("test")
        a = snip.const(1, 32)
        b = snip.const(2, 32)
        snip.add(a, b)
        snip.sub(a, b)
        snip.slt(a, b)
        omap = snip.operations_map
        assert "add_32" in omap
        assert "slt_32" in omap

    def test_read_write(self, rv32i_rf):
        seq = SeqBuilder()
        reg = seq.input(0, 5)
        v = seq.read(rv32i_rf, reg)
        assert v.width == 32
        seq.write(rv32i_rf, reg, v)
        kinds = {stmt.kind for stmt in seq.build().stmts}
        assert "read" in kinds
        assert "write" in kinds

    def test_env(self, rv32i_envs):
        seq = SeqBuilder()
        pc_read = rv32i_envs["getPC"]
        result = seq.env(pc_read, [])
        assert len(result) == 1
        assert result[0].width == 32

    def test_cond_env(self, rv32i_envs):
        seq = SeqBuilder()
        cond = seq.const(1, 1)
        addr = seq.const(100, 32)
        fallback = seq.const(200, 32)
        write_mem = rv32i_envs["writeMem32"]
        result = seq.cond_env(write_mem, cond, [addr], [fallback])
        assert len(result) == 0


class TestSnippetBuilder:
    def test_build_snippet(self):
        sb = SnippetBuilder("test")
        a = sb.input(0, 32)
        sb.output(a, 0)
        snip = sb.build()
        assert snip.name == "test"
        assert len(snip.seq.stmts) == 2

    def test_build_decode(self):
        sb = SnippetBuilder("decode_rs2")
        enc = sb.input(0, 32)
        shift = sb.const(20, 32)
        shifted = sb.lsr(enc, shift)
        r = sb.extract_low(shifted, 5)
        sb.output(r, 0)
        snip = sb.build()
        assert len(snip.seq.stmts) == 5

    def test_build_constraint(self):
        sb = SnippetBuilder("constraint")
        enc = sb.input(0, 32)
        mask = sb.const(0xFF, 32)
        masked = sb.and_(enc, mask)
        expected = sb.const(0x33, 32)
        ok = sb.slt(masked, expected)
        sb.output(ok, 0)
        snip = sb.build()
        assert len(snip.seq.stmts) == 6


class TestInstructionBuilder:
    def test_build_add(self, rv32i_rf):
        enc = InstructionEncoding(32, 51, 4261441663, [], "", "", "")
        ib = InstructionBuilder("add", [5, 5, 5], ["rd", "rs1", "rs2"], enc)
        rd = ib.add_input_operand(0, 5)
        rs1 = ib.add_input_operand(1, 5)
        rs2 = ib.add_input_operand(2, 5)
        v1 = ib.read(rv32i_rf, rs1)
        v2 = ib.read(rv32i_rf, rs2)
        r = ib.add(v1, v2)
        ib.write(rv32i_rf, rd, r)
        instr = ib.build()
        assert instr.name == "add"
        assert len(instr.semantic.stmts) == 7

    def test_build_lhu(self, rv32i_rf, rv32i_envs):
        enc = InstructionEncoding(32, 20483, 28799, [], "", "", "")
        ib = InstructionBuilder("lhu", [32, 32, 32], ["imm", "rs1", "rd"], enc)
        imm = ib.add_input_operand(0, 32)
        rs1 = ib.add_input_operand(1, 32)
        rd = ib.add_input_operand(2, 32)
        v = ib.read(rv32i_rf, rs1)
        addr = ib.add(v, imm)
        val16 = ib.env(rv32i_envs["readMem16"], [addr])
        r = ib.extend_zero(val16[0], 32)
        ib.write(rv32i_rf, rd, r)
        instr = ib.build()
        assert instr.name == "lhu"

    def test_build_beq(self, rv32i_rf, rv32i_envs):
        enc = InstructionEncoding(32, 99, 28799, [], "", "", "")
        ib = InstructionBuilder("beq", [32, 32, 32], ["imm", "rs1", "rs2"], enc)
        imm = ib.add_input_operand(0, 32)
        rs1 = ib.add_input_operand(1, 32)
        rs2 = ib.add_input_operand(2, 32)
        v1 = ib.read(rv32i_rf, rs1)
        v2 = ib.read(rv32i_rf, rs2)
        eq = ib.eq(v1, v2)
        base = ib.env(rv32i_envs["getPC"], [])
        dest = ib.add(base[0], imm)
        c4 = ib.const(4, 32)
        fallback = ib.add(base[0], c4)
        ib.cond_env(rv32i_envs["setPC"], eq, [dest], [fallback])
        instr = ib.build()
        assert instr.name == "beq"

    def test_build_ecall(self, rv32i_envs):
        enc = InstructionEncoding(32, 115, 0xFFFFFFFF, [], "", "", "")
        ib = InstructionBuilder("ecall", [], [], enc)
        ib.env(rv32i_envs["sysCall"], [])
        instr = ib.build()
        assert instr.name == "ecall"
        assert instr.semantic.stmts[0].kind == "env"


class TestArchBuilder:
    def test_build_arch(self, rv32i_rf):
        ab = ArchBuilder("test", ["attr"])
        ab.add_register_file(rv32i_rf)
        arch = ab.build()
        assert arch.name == "test"
        assert len(arch.register_files) == 1

    def test_add_env_operation_snippet(self):
        ab = ArchBuilder("test", [])
        env = EnvironmentFunction("ld", ["mem"], [32], [32])
        op = Add(32)
        sb = SnippetBuilder("s1")
        a = sb.input(0, 32)
        sb.output(a, 0)
        snip = sb.build()
        ab.add_env_func(env).add_operation(op).add_snippet(snip)
        arch = ab.build()
        assert len(arch.environment_functions) == 1
        assert len(arch.operations) == 1
        assert len(arch.snippets) == 1
