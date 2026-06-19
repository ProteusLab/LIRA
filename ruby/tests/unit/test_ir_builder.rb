$LOAD_PATH.unshift(File.expand_path('../..', __dir__))
require 'lira'
require 'minitest/autorun'

include Lira

class TestSeqBuilder < Minitest::Test
  def test_const
    seq = SeqBuilder.new
    v = seq.const(42, 32)
    assert_equal 32, v.width
    assert v.name.start_with?('_t')
  end

  def test_add_sub_mul
    seq = SeqBuilder.new
    a = seq.const(3, 32)
    b = seq.const(2, 32)
    assert_equal 32, seq.add(a, b).width
    assert_equal 32, seq.sub(a, b).width
    assert_equal 32, seq.mul(a, b).width
  end

  def test_bitwise_ops
    seq = SeqBuilder.new
    a = seq.const(0xFF, 32)
    b = seq.const(0x0F, 32)
    assert_equal 32, seq.and_(a, b).width
    assert_equal 32, seq.orr(a, b).width
    assert_equal 32, seq.xor(a, b).width
  end

  def test_shift_ops
    seq = SeqBuilder.new
    a = seq.const(1, 32)
    b = seq.const(4, 32)
    assert_equal 32, seq.lsl(a, b).width
    assert_equal 32, seq.lsr(a, b).width
    assert_equal 32, seq.asr(a, b).width
  end

  def test_slt
    seq = SeqBuilder.new
    a = seq.const(10, 32)
    b = seq.const(20, 32)
    r = seq.slt(a, b)
    assert_equal 1, r.width
  end

  def test_extract_low
    seq = SeqBuilder.new
    a = seq.const(0xFF, 32)
    r = seq.extract_low(a, 8)
    assert_equal 8, r.width
  end

  def test_extend_sign
    seq = SeqBuilder.new
    a = seq.const(1, 8)
    r = seq.extend_sign(a, 32)
    assert_equal 32, r.width
  end

  def test_extend_zero
    seq = SeqBuilder.new
    a = seq.const(1, 8)
    r = seq.extend_zero(a, 32)
    assert_equal 32, r.width
  end

  def test_input_output
    seq = SeqBuilder.new
    inp = seq.input(0, 32)
    seq.output(inp, 0)
    s = seq.build
    assert_equal 'input', s.stmts[0].kind
    assert_equal 'output', s.stmts[1].kind
  end

  def test_operations_map
    snip = SnippetBuilder.new('test')
    a = snip.const(1, 32)
    b = snip.const(2, 32)
    snip.add(a, b)
    snip.sub(a, b)
    snip.slt(a, b)
    omap = snip.operations_map
    assert omap.key?('add_32')
    assert omap.key?('slt_32')
  end

  def test_read_write
    rf = RegisterFile.new('XRegs', [], Shape.new(32, nil), [Register.new('x0')])
    seq = SeqBuilder.new
    reg = seq.input(0, 5)
    v = seq.read(rf, reg)
    assert_equal 32, v.width
    seq.write(rf, reg, v)
    s = seq.build
    kinds = s.stmts.map(&:kind)
    assert kinds.include?('read')
    assert kinds.include?('write')
  end

  def test_env
    get_pc = EnvironmentFunction.new('getPC', [], [], [32])
    seq = SeqBuilder.new
    result = seq.env(get_pc, [])
    assert_equal 1, result.length
    assert_equal 32, result[0].width
  end

  def test_cond_env
    write_mem = EnvironmentFunction.new('writeMem32', [], [32, 32], [])
    seq = SeqBuilder.new
    cond = seq.const(1, 1)
    addr = seq.const(100, 32)
    fallback = seq.const(200, 32)
    result = seq.cond_env(write_mem, cond, [addr], [fallback])
    assert_equal 0, result.length
  end
end

class TestSnippetBuilder < Minitest::Test
  def test_build_snippet
    sb = SnippetBuilder.new('test')
    a = sb.input(0, 32)
    sb.output(a, 0)
    snip = sb.build
    assert_equal 'test', snip.name
    assert_equal 2, snip.seq.stmts.length
  end

  def test_build_decode
    sb = SnippetBuilder.new('decode_rs2')
    enc = sb.input(0, 32)
    shift = sb.const(20, 32)
    shifted = sb.lsr(enc, shift)
    r = sb.extract_low(shifted, 5)
    sb.output(r, 0)
    snip = sb.build
    assert_equal 5, snip.seq.stmts.length
  end

  def test_build_constraint
    sb = SnippetBuilder.new('constraint')
    enc = sb.input(0, 32)
    mask = sb.const(0xFF, 32)
    masked = sb.and_(enc, mask)
    expected = sb.const(0x33, 32)
    ok = sb.slt(masked, expected)
    sb.output(ok, 0)
    snip = sb.build
    assert_equal 6, snip.seq.stmts.length
  end
end

class TestInstructionBuilder < Minitest::Test
  def setup
    @rf = RegisterFile.new('XRegs', [], Shape.new(32, nil),
                           (0...32).map { |i| Register.new("x#{i}") })
    @get_pc = EnvironmentFunction.new('getPC', [], [], [32])
    @set_pc = EnvironmentFunction.new('setPC', [], [32], [])
    @read_mem = EnvironmentFunction.new('readMem16', [], [32], [16])
    @syscall = EnvironmentFunction.new('sysCall', [], [], [])
  end

  def test_build_add
    enc = InstructionEncoding.new(32, 51, 0, [], '', '', '')
    ib = InstructionBuilder.new('add', [5, 5, 5], ['rd', 'rs1', 'rs2'], enc)
    rd = ib.add_input_operand(0, 5)
    rs1 = ib.add_input_operand(1, 5)
    rs2 = ib.add_input_operand(2, 5)
    v1 = ib.read(@rf, rs1)
    v2 = ib.read(@rf, rs2)
    r = ib.add(v1, v2)
    ib.write(@rf, rd, r)
    instr = ib.build
    assert_equal 'add', instr.name
    assert_equal 7, instr.semantic.stmts.length
  end

  def test_build_ecall
    enc = InstructionEncoding.new(32, 115, 0, [], '', '', '')
    ib = InstructionBuilder.new('ecall', [], [], enc)
    ib.env(@syscall, [])
    instr = ib.build
    assert_equal 'ecall', instr.name
    assert_equal 'env', instr.semantic.stmts[0].kind
  end
end

class TestArchBuilder < Minitest::Test
  def test_build_arch
    rf = RegisterFile.new('XRegs', [], Shape.new(32, nil), [Register.new('x0')])
    ab = ArchBuilder.new('test', ['attr'])
    ab.add_register_file(rf)
    arch = ab.build
    assert_equal 'test', arch.name
    assert_equal 1, arch.register_files.length
  end

  def test_add_env_operation_snippet
    ab = ArchBuilder.new('test', [])
    env = EnvironmentFunction.new('ld', ['mem'], [32], [32])
    op = Add.new(32)
    sb = SnippetBuilder.new('s1')
    a = sb.input(0, 32)
    sb.output(a, 0)
    snip = sb.build
    ab.add_env_func(env).add_operation(op).add_snippet(snip)
    arch = ab.build
    assert_equal 1, arch.environment_functions.length
    assert_equal 1, arch.operations.length
    assert_equal 1, arch.snippets.length
  end
end
