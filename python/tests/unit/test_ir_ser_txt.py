import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lira.ir import Shape
from lira.arch import Register, RegisterFile, EnvironmentFunction
from lira.ir_ser_txt import serialize_statement_seq, deserialize_statement_seq
from lira.ir_builder import SeqBuilder, SnippetBuilder


@pytest.fixture(scope="module")
def rv32i_snippet_texts():
    return {
        "decode_0": (
            "1 32 _t1 = input 0;\n"
            "1 32 _t3 = const 7;\n"
            "1 32 _t4 = op lsr_32 _t1 _t3;\n"
            "1 5 _t5 = op extract_low_32_to_5 _t4;\n"
            "1 32 _t6 = op extend_zero_5_to_32 _t5;\n"
            "1 = output 0 _t6;\n"
        ),
        "encode_0": (
            "1 32 _t1 = input 0;\n"
            "1 32 _t2 = input 1;\n"
            "1 32 _t3 = input 2;\n"
            "1 32 _t4 = const 0;\n"
            "1 1 _t5 = const 51;\n"
            "1 32 _t6 = op extend_zero_1_to_32 _t5;\n"
            "1 32 _t7 = const 6;\n"
            "1 32 _t8 = op lsl_32 _t6 _t7;\n"
            "1 32 _t9 = op orr_32 _t4 _t8;\n"
            "1 32 _t10 = const 11;\n"
            "1 32 _t11 = op lsl_32 _t3 _t10;\n"
            "1 32 _t12 = op orr_32 _t9 _t11;\n"
            "1 1 _t13 = const 0;\n"
            "1 32 _t14 = op extend_zero_1_to_32 _t13;\n"
            "1 32 _t15 = const 14;\n"
            "1 32 _t16 = op lsl_32 _t14 _t15;\n"
            "1 32 _t17 = op orr_32 _t12 _t16;\n"
            "1 32 _t18 = const 19;\n"
            "1 32 _t19 = op lsl_32 _t2 _t18;\n"
            "1 32 _t20 = op orr_32 _t17 _t19;\n"
            "1 32 _t21 = const 24;\n"
            "1 32 _t22 = op lsl_32 _t1 _t21;\n"
            "1 32 _t23 = op orr_32 _t20 _t22;\n"
            "1 1 _t24 = const 0;\n"
            "1 32 _t25 = op extend_zero_1_to_32 _t24;\n"
            "1 32 _t26 = const 31;\n"
            "1 32 _t27 = op lsl_32 _t25 _t26;\n"
            "1 32 _t28 = op orr_32 _t23 _t27;\n"
            "1 = output 0 _t28;\n"
        ),
        "constraint_36": (
            "1 32 _t1 = input 0;\n"
            "1 32 _t2 = const 28799;\n"
            "1 32 _t3 = op and_32 _t1 _t2;\n"
            "1 32 _t4 = const 20483;\n"
            "1 1 _t5 = op eq_32 _t3 _t4;\n"
            "1 = output 0 _t5;\n"
        ),
    }


@pytest.fixture(scope="module")
def rv32i_instruction_texts():
    return {
        "ecall": "1 = env sysCall;\n",
        "add": (
            "1 32 _t3 = input 1;\n"
            "1 32 _t4 = read XRegs _t3;\n"
            "1 32 _t7 = input 0;\n"
            "1 32 _t8 = read XRegs _t7;\n"
            "1 32 _t10 = op add_32 _t4 _t8;\n"
            "1 32 _t11 = input 2;\n"
            "1 = write XRegs _t11 _t10;\n"
        ),
        "lhu": (
            "1 32 _t3 = input 1;\n"
            "1 32 _t4 = read XRegs _t3;\n"
            "1 32 _t5 = input 0;\n"
            "1 32 _t6 = op add_32 _t4 _t5;\n"
            "1 16 _t8 = env readMem16 _t6;\n"
            "1 32 _t10 = op extend_zero_16_to_32 _t8;\n"
            "1 32 _t11 = input 2;\n"
            "1 = write XRegs _t11 _t10;\n"
        ),
        "beq": (
            "1 32 _t3 = input 1;\n"
            "1 32 _t4 = read XRegs _t3;\n"
            "1 32 _t6 = input 2;\n"
            "1 32 _t7 = read XRegs _t6;\n"
            "1 1 _t8 = op eq_32 _t4 _t7;\n"
            "1 32 _t10 = env getPC;\n"
            "1 32 _t11 = input 0;\n"
            "1 32 _t12 = op add_32 _t10 _t11;\n"
            "1 32 _t14 = const 4;\n"
            "1 32 _t15 = op add_32 _t10 _t14;\n"
            "1 32 _t17 = op select_32 _t8 _t12 _t15;\n"
            "1 = env setPC _t17;\n"
        ),
    }


class TestIrSerTxt:
    def test_empty_sequence(self):
        seq = SeqBuilder().build()
        text = serialize_statement_seq(seq)
        assert text == ""

    def test_built_sequence_roundtrip(self):
        seq = SeqBuilder()
        a = seq.input(0, 32)
        b = seq.const(42, 32)
        r = seq.add(a, b)
        seq.output(r, 0)
        stmts = seq.build()
        text = serialize_statement_seq(stmts)
        seq2 = deserialize_statement_seq(text)
        assert seq2 == stmts

    def test_shape_with_mult(self):
        seq = SeqBuilder()
        a = seq.input(0, 32)
        r = seq.add(a, a)
        seq.output(r, 0)
        stmts = seq.build()
        stmts.stmts[0].shape = Shape(4, "c")
        text = serialize_statement_seq(stmts)
        assert "4c" in text
        seq2 = deserialize_statement_seq(text)
        assert seq2.stmts[0].shape.lanes_mult == "c"

    def test_read_write(self):
        rf = RegisterFile("XRegs", [], Shape(32, None), [Register("x0")])
        seq = SeqBuilder()
        reg = seq.input(0, 5)
        v = seq.read(rf, reg)
        seq.write(rf, reg, v)
        stmts = seq.build()
        text = serialize_statement_seq(stmts)
        seq2 = deserialize_statement_seq(text)
        assert seq2.stmts[1].kind == "read"
        assert seq2.stmts[2].kind == "write"

    def test_env_and_cond_env(self):
        get_pc = EnvironmentFunction("getPC", [], [], [32])
        write_mem = EnvironmentFunction("writeMem16", [], [32, 16], [])
        seq = SeqBuilder()
        seq.env(get_pc, [])
        cond = seq.input(0, 1)
        addr = seq.input(1, 32)
        fallback = seq.input(2, 32)
        seq.cond_env(write_mem, cond, [addr], [fallback])
        stmts = seq.build()
        text = serialize_statement_seq(stmts)
        seq2 = deserialize_statement_seq(text)
        assert seq2.stmts[0].kind == "env"
        assert seq2.stmts[-1].kind == "cond_env"

    def test_builder_decode_snippet(self):
        sb = SnippetBuilder("decode_0")
        enc = sb.input(0, 32)
        c7 = sb.const(7, 32)
        shifted = sb.lsr(enc, c7)
        low5 = sb.extract_low(shifted, 5)
        extended = sb.extend_zero(low5, 32)
        sb.output(extended, 0)
        snip = sb.build()
        text = serialize_statement_seq(snip.seq)
        seq2 = deserialize_statement_seq(text)
        assert len(seq2.stmts) == 6

    def test_builder_constraint_snippet(self):
        sb = SnippetBuilder("constraint_36")
        enc = sb.input(0, 32)
        mask = sb.const(28799, 32)
        masked = sb.and_(enc, mask)
        expected = sb.const(20483, 32)
        ok = sb.eq(masked, expected)
        sb.output(ok, 0)
        snip = sb.build()
        text = serialize_statement_seq(snip.seq)
        seq2 = deserialize_statement_seq(text)
        assert len(seq2.stmts) == 6

    @pytest.mark.parametrize("name", ["decode_0", "encode_0", "constraint_36"])
    def test_rv32i_snippet_text_roundtrip(self, rv32i_snippet_texts, name):
        text = rv32i_snippet_texts[name]
        seq = deserialize_statement_seq(text)
        text2 = serialize_statement_seq(seq)
        assert text.strip() == text2.strip()

    @pytest.mark.parametrize("name", ["lhu", "ecall", "add", "beq"])
    def test_rv32i_instruction_text_roundtrip(self, rv32i_instruction_texts, name):
        text = rv32i_instruction_texts[name]
        seq = deserialize_statement_seq(text)
        text2 = serialize_statement_seq(seq)
        assert text.strip() == text2.strip()
