#!/usr/bin/env ruby

$LOAD_PATH.unshift(File.expand_path('..', __dir__))

require 'pathname'
require 'lira/arch'
require 'lira/arch_ser_txt'
require 'lira/ir_ser_txt'
require 'lira/ir'
include LIRA

def main
  raise "Usage: #{$PROGRAM_NAME} <arch_dir>" unless ARGV.size == 1
  arch_dir = Pathname.new(ARGV[0])

  rf = RegisterFile.new(
    name: 'X',
    attributes: [],
    reg_size: Shape.new(32, nil),
    reg_names: (0...32).map { |i| "x#{i}" }
  )

  ld32 = EnvironmentFunction.new(name: 'ld32', attributes: ['mem.read'], inputs: [32], outputs: [32])
  st32 = EnvironmentFunction.new(name: 'st32', attributes: ['mem.write'], inputs: [32, 32], outputs: [])
  pc_read = EnvironmentFunction.new(name: 'pc_read', attributes: ['pc.read'], inputs: [], outputs: [32])
  pc_write = EnvironmentFunction.new(name: 'pc_write', attributes: ['pc.write'], inputs: [32], outputs: [])

  ops = []
  [
    ['add_32', [32, 32], 32, 'add'],
    ['lsl_32', [32, 32], 32, 'lsl'],
    ['lsr_32', [32, 32], 32, 'lsr'],
    ['asr_32', [32, 32], 32, 'asr'],
    ['slt_32', [32, 32], 1, 'slt'],
    ['extract_low_5_32', [32], 5, 'extract_low']
  ].each do |name, inputs, output, base|
    ops << Operation.new(name: name, attributes: [], inputs: inputs, outputs: [output], semantic_base: base)
  end

  def sem(code_lines)
    stmts = code_lines.map { |line| IrSerTxt.deserialize_statement(line) }
    StatementSeq.new(stmts)
  end

  snippets = []

  def add_snippet(snippets, name, code_lines)
    snippets << Snippet.new(name: name, attributes: [], seq: sem(code_lines))
  end

  # op_extend_sign_inner_32
  add_snippet(snippets, 'op_extend_sign_inner_32', [
    '1 32 input = input 0',
    '1 32 width = input 1',
    '1 32 c32 = const 32',
    '1 32 delta = sub_32 c32 width',
    '1 32 temp = lsl_32 input delta',
    '1 32 r = asr_32 temp delta',
    '1 = output r'
  ])
  ops << Operation.new(
    name: 'extend_sign_inner_32',
    attributes: [],
    inputs: [32, 32],
    outputs: [32],
    semantic_base: nil,
    semantic_func: 'op_extend_sign_inner_32'
  )

  add_snippet(snippets, 'op_extract_inner_32', [
    '1 32 input = input 0',
    '1 32 lsb = input 1',
    '1 32 width = input 2',
    '1 32 new_lsb = input 3',
    '1 32 c32 = const 32',
    '1 32 t1 = sub_32 c32 lsb',
    '1 32 shift_l = sub_32 t1 width',
    '1 32 temp = lsl_32 input shift_l',
    '1 32 shift_r = sub_32 c32 width',
    '1 32 temp2 = lsr_32 temp shift_r',
    '1 = output r'
  ])
  ops << Operation.new(
    name: 'extract_inner_32',
    attributes: [],
    inputs: [32, 32, 32],
    outputs: [32],
    semantic_base: nil,
    semantic_func: 'op_extract_inner_32'
  )

  add_snippet(snippets, 'op_orr_shifted_32', [
    '1 32 data = input 0',
    '1 32 lsb = input 1',
    '1 32 value = input 2',
    '1 32 insert = lsl_32 value lsb',
    '1 32 r = orr_32 data insert',
    '1 = output r'
  ])
  ops << Operation.new(
    name: 'orr_shifted_32',
    attributes: [],
    inputs: [32, 32, 32],
    outputs: [32],
    semantic_base: nil,
    semantic_func: 'op_orr_shifted_32'
  )

  def add_snippet_extract(snippets, name, input_width, lsb, output_width)
    add_snippet(snippets, name, [
      "1 #{input_width} enc = input 0",
      "1 #{input_width} shift = const #{lsb}",
      "1 #{input_width} shifted = op lsr_#{input_width} enc shift",
      "1 #{output_width} r = op extract_low_#{output_width}_#{input_width} shifted",
      '1 = output r'
    ])
  end

  add_snippet_extract(snippets, 'decode_b_rs1', 32, 15, 5)
  add_snippet_extract(snippets, 'decode_b_rs2', 32, 20, 5)

  add_snippet(snippets, 'decode_b_imm', [
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
    '1 = output imm_sext'
  ])

  add_snippet(snippets, 'encode_b', [
    '1 5 rs1 = input 0',
    '1 5 rs2 = input 2',
    '1 32 imm = input 2',
    '1 32 base = dyn_const enc_base',
    '1 32 c15 = const 15',
    '1 32 c20 = const 20',
    '1 32 t1 = op orr_shifted base rs1 c15',
    '1 32 t2 = op orr_shifted t1 rs2 c20',
    '1 32 r = todo todo t2 imm',
    '1 = output r'
  ])

  def enc_b(funct3, opcode)
    InstructionEncoding.new(
      encoded_size: 32,
      const_encoding_part: (funct3 << 12) + opcode,
      decode: ['decode_b_rs1', 'decode_b_rs2', 'decode_b_imm'],
      encode: 'encode_b',
      constraint_decode: '',
      constraint_encode: ''
    )
  end

  blt_semantic = sem([
    '1 5 x1 = input 0',
    '1 5 x2 = input 1',
    '1 5 offset = input 2',
    '1 32 v1 = read X x1',
    '1 32 v2 = read X x2',
    '1 1 cond = op slt_32 v1 v2',
    '1 32 base = env pc_read',
    '1 32 dest = op add_32 base offset',
    '1 = cond_env pc_write cond dest'
  ])

  blt_inst = Instruction.new(
    name: 'blt',
    attributes: ['kind.branch.cond'],
    operand_sizes: [5, 5, 32],
    operand_names: ['x1', 'x2', 'offset'],
    encoding: enc_b(0b100, 0b1100011),
    semantic: blt_semantic
  )

  instructions = [blt_inst]

  arch = Arch.new(
    name: 'test_arch',
    attributes: ['attr.1', 'attr.2'],
    register_files: [rf],
    system_registers: [],
    environment_functions: [ld32, st32, pc_read, pc_write],
    tables_int: [],
    operations: ops,
    snippets: snippets,   instructions: instructions
  )

  ArchSerTxt.write_arch(arch, arch_dir)
  arch2 = ArchSerTxt.read_arch(arch_dir)

  raise "register_files mismatch" unless arch.register_files == arch2.register_files
  raise "system_registers mismatch" unless arch.system_registers == arch2.system_registers
  raise "environment_functions mismatch" unless arch.environment_functions == arch2.environment_functions
  raise "tables_int mismatch" unless arch.tables_int == arch2.tables_int
  raise "operations mismatch" unless arch.operations == arch2.operations
  raise "snippets mismatch" unless arch.snippets == arch2.snippets
  raise "instructions mismatch" unless arch.instructions == arch2.instructions
  raise "arch equality mismatch" unless arch == arch2
end

main if __FILE__ == $PROGRAM_NAME
