import pytest

from python.lira.ir import Shape
from python.lira.arch import Register, RegisterFile, EnvironmentFunction
from python.lira.ir_ser_txt import serialize_statement_seq, deserialize_statement_seq
from python.lira.ir_builder import SeqBuilder, SnippetBuilder


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

    def test_no_semicolons_and_newline_separated(self):
        seq = SeqBuilder()
        seq.const(1, 32)
        seq.const(2, 32)
        text = serialize_statement_seq(seq.build())
        assert text == "1 32 _t1 = const 1\n1 32 _t2 = const 2\n"
        assert ";" not in text
        assert len(text.splitlines()) == 2

    def test_comments_blank_lines_and_trailing_whitespace(self):
        text = (
            "# comment\n"
            "\n"
            "   # indented comment\n"
            "1 32 x = const 1   \n"
            "1 32 y = const 2\t\n"
        )
        seq = deserialize_statement_seq(text)
        assert len(seq.stmts) == 2
        assert serialize_statement_seq(seq) == "1 32 x = const 1\n1 32 y = const 2\n"

    def test_flexible_whitespace_around_equals(self):
        text = "1 32 x\t=\tconst 1\n1  32  x =  const 1\n"
        seq = deserialize_statement_seq(text)
        assert len(seq.stmts) == 2
        assert serialize_statement_seq(seq) == "1 32 x = const 1\n1 32 x = const 1\n"

    def test_semicolon_is_an_ordinary_character(self):
        seq = deserialize_statement_seq("1 = const 1;\n")
        assert seq.stmts[0].specifier == "1;"

    def test_missing_equals_is_rejected(self):
        with pytest.raises(ValueError):
            deserialize_statement_seq("1 const 1\n")
        with pytest.raises(ValueError):
            deserialize_statement_seq("= const 1\n")

    def test_odd_output_tokens_are_rejected(self):
        with pytest.raises(ValueError):
            deserialize_statement_seq("1 32 x 3 = op add x x\n")
