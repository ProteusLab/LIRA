$LOAD_PATH.unshift(File.expand_path('../..', __dir__))
require 'lira'
require 'minitest/autorun'
require 'tempfile'

include Lira

class TestArchSerYaml < Minitest::Test
  def setup
    @tmp = Tempfile.new(['lira_test', '.yaml'])
  end

  def teardown
    @tmp.close
    @tmp.unlink
  end

  def test_minimal_arch_with_builder
    rf = RegisterFile.new('X', [], Shape.new(32, nil), [Register.new('x0'), Register.new('x1')])
    ab = ArchBuilder.new('minimal', [])
    ab.add_register_file(rf)
    sb = SnippetBuilder.new('s')
    a = sb.input(0, 32)
    sb.output(a, 0)
    ab.add_snippet(sb.build)
    arch = ab.build
    ArchSerYaml.write_arch(arch, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)
    assert_equal arch, arch2
  end

  def test_instruction_via_builder
    rf = RegisterFile.new('X', [], Shape.new(32, nil), [Register.new('x0')])
    enc = InstructionEncoding.new(32, 0, 0, [], '', '', '')
    ib = InstructionBuilder.new('test', [5, 5], ['rs1', 'rs2'], enc)
    rs1 = ib.add_input_operand(0, 5)
    rs2 = ib.add_input_operand(1, 5)
    v = ib.read(rf, rs1)
    ib.write(rf, rs2, v)
    instr = ib.build
    ab = ArchBuilder.new('w_instr', [])
    ab.add_register_file(rf)
    ab.add_instruction(instr)
    arch = ab.build
    ArchSerYaml.write_arch(arch, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)
    assert_equal arch, arch2
  end

  def test_null_fields_roundtrip
    op = Add.new(32)
    op.semantic_base = nil
    op.semantic_func = nil
    ab = ArchBuilder.new('null_test', [])
    ab.add_operation(op)
    arch = ab.build
    ArchSerYaml.write_arch(arch, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)
    assert_nil arch2.operations[0].semantic_base
  end

  def test_register_attributes
    rf = RegisterFile.new('R', [], Shape.new(32, nil), [Register.new('x0', ['zero']), Register.new('x1', [])])
    ab = ArchBuilder.new('attrs', [])
    ab.add_register_file(rf)
    arch = ab.build
    ArchSerYaml.write_arch(arch, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)
    assert_equal ['zero'], arch2.register_files[0].regs[0].attributes
  end

  def test_system_register
    field = SystemRegisterField.new('f', [], 0, 7)
    sr = SystemRegister.new('csr', [], 32, [field])
    ab = ArchBuilder.new('sysreg', [])
    ab.add_system_register(sr)
    arch = ab.build
    ArchSerYaml.write_arch(arch, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)
    assert_equal 0, arch2.system_registers[0].fields[0].lsb
  end

  def test_table_int
    table = TableInt.new('t', [], [1, 2, 3])
    ab = ArchBuilder.new('tbl', [])
    ab.add_table_int(table)
    arch = ab.build
    ArchSerYaml.write_arch(arch, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)
    assert_equal [1, 2, 3], arch2.tables_int[0].values
  end

  def test_rv32i_lite_roundtrip
    rf = RegisterFile.new('XRegs', [], Shape.new(32, nil),
                          [Register.new('x0', ['zero'])] + (1...32).map { |i| Register.new("x#{i}") })

    ab = ArchBuilder.new('rv32i_lite', [])
    ab.add_register_file(rf)

    syscall = EnvironmentFunction.new('sysCall', [], [], [])
    read_mem = EnvironmentFunction.new('readMem16', [], [32], [16])
    get_pc = EnvironmentFunction.new('getPC', [], [], [32])
    set_pc = EnvironmentFunction.new('setPC', [], [32], [])
    ab.add_env_func(syscall).add_env_func(read_mem).add_env_func(get_pc).add_env_func(set_pc)

    ab.add_operation(Add.new(32))
    ab.add_operation(Lsr.new(32))
    ab.add_operation(Lsl.new(32))

    # decode_0 snippet
    sb = SnippetBuilder.new('decode_0')
    enc = sb.input(0, 32)
    c7 = sb.const(7, 32)
    shifted = sb.lsr(enc, c7)
    low5 = sb.extract_low(shifted, 5)
    extended = sb.extend_zero(low5, 32)
    sb.output(extended, 0)
    ab.add_snippet(sb.build)

    # add instruction
    enc = InstructionEncoding.new(32, 51, 0, [], '', '', '')
    ib = InstructionBuilder.new('add', [32, 32, 32], ['rs2', 'rs1', 'rd'], enc)
    rs2 = ib.add_input_operand(0, 32)
    rs1 = ib.add_input_operand(1, 32)
    rd = ib.add_input_operand(2, 32)
    v1 = ib.read(rf, rs1)
    v2 = ib.read(rf, rs2)
    r = ib.add(v1, v2)
    ib.write(rf, rd, r)
    ab.add_instruction(ib.build)

    # ecall
    enc = InstructionEncoding.new(32, 115, 0, [], '', '', '')
    ib = InstructionBuilder.new('ecall', [], [], enc)
    ib.env(syscall, [])
    ab.add_instruction(ib.build)

    arch = ab.build
    ArchSerYaml.write_arch(arch, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)
    assert_equal arch, arch2
  end
end
