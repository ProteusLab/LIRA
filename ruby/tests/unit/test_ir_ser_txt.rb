$LOAD_PATH.unshift(File.expand_path('../..', __dir__))
require 'lira'
require 'minitest/autorun'

include Lira

class TestIrSerTxt < Minitest::Test
  def test_empty_sequence
    seq = SeqBuilder.new.build
    text = IrSerTxt.serialize_statement_seq(seq)
    assert_equal '', text
  end

  def test_built_sequence_roundtrip
    seq = SeqBuilder.new
    a = seq.input(0, 32)
    b = seq.const(42, 32)
    r = seq.add(a, b)
    seq.output(r, 0)
    stmts = seq.build
    text = IrSerTxt.serialize_statement_seq(stmts)
    seq2 = IrSerTxt.deserialize_statement_seq(text)
    assert_equal stmts, seq2
  end

  def test_shape_with_mult
    seq = SeqBuilder.new
    a = seq.input(0, 32)
    r = seq.add(a, a)
    seq.output(r, 0)
    stmts = seq.build
    stmts.stmts[0].shape = Shape.new(4, 'c')
    text = IrSerTxt.serialize_statement_seq(stmts)
    assert text.include?('4c')
    seq2 = IrSerTxt.deserialize_statement_seq(text)
    assert_equal 'c', seq2.stmts[0].shape.lanes_mult
  end

  def test_read_write
    rf = RegisterFile.new('XRegs', [], Shape.new(32, nil), [Register.new('x0')])
    seq = SeqBuilder.new
    reg = seq.input(0, 5)
    v = seq.read(rf, reg)
    seq.write(rf, reg, v)
    stmts = seq.build
    text = IrSerTxt.serialize_statement_seq(stmts)
    seq2 = IrSerTxt.deserialize_statement_seq(text)
    assert_equal 'read', seq2.stmts[1].kind
    assert_equal 'write', seq2.stmts[2].kind
  end

  def test_env_and_cond_env
    get_pc = EnvironmentFunction.new('getPC', [], [], [32])
    write_mem = EnvironmentFunction.new('writeMem16', [], [32, 16], [])
    seq = SeqBuilder.new
    seq.env(get_pc, [])
    cond = seq.input(0, 1)
    addr = seq.input(1, 32)
    fallback = seq.input(2, 32)
    seq.cond_env(write_mem, cond, [addr], [fallback])
    stmts = seq.build
    text = IrSerTxt.serialize_statement_seq(stmts)
    seq2 = IrSerTxt.deserialize_statement_seq(text)
    assert_equal 'env', seq2.stmts[0].kind
    assert_equal 'cond_env', seq2.stmts[-1].kind
  end

  def test_builder_decode_snippet
    sb = SnippetBuilder.new('decode_0')
    enc = sb.input(0, 32)
    c7 = sb.const(7, 32)
    shifted = sb.lsr(enc, c7)
    low5 = sb.extract_low(shifted, 5)
    extended = sb.extend_zero(low5, 32)
    sb.output(extended, 0)
    snip = sb.build
    text = IrSerTxt.serialize_statement_seq(snip.seq)
    seq2 = IrSerTxt.deserialize_statement_seq(text)
    assert_equal 6, seq2.stmts.length
  end

  def test_builder_constraint_snippet
    sb = SnippetBuilder.new('constraint_36')
    enc = sb.input(0, 32)
    mask = sb.const(28_799, 32)
    masked = sb.and_(enc, mask)
    expected = sb.const(20_483, 32)
    ok = sb.eq(masked, expected)
    sb.output(ok, 0)
    snip = sb.build
    text = IrSerTxt.serialize_statement_seq(snip.seq)
    seq2 = IrSerTxt.deserialize_statement_seq(text)
    assert_equal 6, seq2.stmts.length
  end
end
