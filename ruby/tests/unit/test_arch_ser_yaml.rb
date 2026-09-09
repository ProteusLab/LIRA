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

  def test_typed_operation_reconstruction
    ab = ArchBuilder.new('typed_ops', [])
    ab.add_operation(Lsr.new(32))
    ab.add_operation(ExtractLow.new(32, 5))
    ab.add_operation(ExtendSign.new(12, 32))
    ab.add_operation(ExtendZero.new(5, 32))
    ab.add_operation(Add.new(32))
    arch = ab.build
    ArchSerYaml.write_arch(arch, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)

    ops = arch2.operations.to_h { |op| [op.name, op] }
    assert_instance_of Lsr, ops['lsr_32']
    assert_instance_of ExtractLow, ops['extract_low_32_to_5']
    assert_instance_of ExtendSign, ops['extend_sign_12_to_32']
    assert_instance_of ExtendZero, ops['extend_zero_5_to_32']
    assert_instance_of Add, ops['add_32']
    assert_equal 'add', ops['add_32'].semantic_base
    assert_equal 'lsr', ops['lsr_32'].semantic_base
  end

  def test_typed_ops_registry
    assert_same Add, Operation.typed_ops[BaseOp::ADD]
    assert_same Lsr, Operation.typed_ops[BaseOp::LSR]
    assert_same Select, Operation.typed_ops[BaseOp::SELECT]
    assert_same ExtendSign, Operation.typed_ops[BaseOp::EXTEND_SIGN]

    Operation.typed_ops.each do |op_base, cls|
      assert_operator cls, :<, Operation
      assert_equal op_base, cls.op_base
    end

    expected = BaseOp.constants.map { |c| BaseOp.const_get(c) }.sort
    assert_equal expected, Operation.typed_ops.keys.sort
  end

  def test_from_operation_restores_fields
    op = Operation.new('custom_add', ['volatile'], [32, 32], [32],
                       semantic_base: 'add', semantic_func: 'add_func',
                       semantic_func_128: 'add_func_128', semantic_table: 'add_table')
    typed = Add.from_operation(op)
    assert_instance_of Add, typed
    assert_equal 'custom_add', typed.name
    assert_equal ['volatile'], typed.attributes
    assert_equal 'add', typed.semantic_base
    assert_equal 'add_func', typed.semantic_func
    assert_equal 'add_func_128', typed.semantic_func_128
    assert_equal 'add_table', typed.semantic_table
  end

  def test_typed_operation_roundtrip_preserves_fields
    op = Operation.new('custom_add', ['volatile'], [32, 32], [32],
                       semantic_base: 'add', semantic_func: 'add_func',
                       semantic_table: 'add_table')
    ab = ArchBuilder.new('fields', [])
    ab.add_operation(op)
    ArchSerYaml.write_arch(ab.build, @tmp.path)
    arch2 = ArchSerYaml.read_arch(@tmp.path)

    op2 = arch2.operations[0]
    assert_instance_of Add, op2
    assert_equal 'custom_add', op2.name
    assert_equal ['volatile'], op2.attributes
    assert_equal 'add_func', op2.semantic_func
    assert_equal 'add_table', op2.semantic_table
  end
end
