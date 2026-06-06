#!/usr/bin/env ruby

$LOAD_PATH.unshift(File.expand_path('lib', __dir__))

require 'optparse'

require '../lira'
include Lira

def build_test_arch
  rf = RegisterFile.new('X', [], Shape.new(32, nil), (0...32).map { |i| "x#{i}" })

  ld32 = EnvironmentFunction.new('ld32', ['mem.read'], [32], [32])
  st32 = EnvironmentFunction.new('st32', ['mem.write'], [32,32], [])
  pc_read = EnvironmentFunction.new('pc_read', ['pc.read'], [], [32])
  pc_write = EnvironmentFunction.new('pc_write', ['pc.write'], [32], [])

  # op_extend_sign_inner_32 snippet
  snip = SnippetBuilder.new('op_extend_sign_inner_32')
  input_val = snip.input(0, 32)
  width_val = snip.input(1, 32)
  c32 = snip.const(32)
  delta = snip.sub(c32, width_val)
  temp = snip.lsl(input_val, delta)
  r = snip.asr(temp, delta)
  snip.output(r, 0)
  extend_sign_inner = snip.build

  op_extend_sign = Operation.new(
    'extend_sign_inner_32', [], [32,32], [32],
    semantic_base: nil, semantic_func: 'op_extend_sign_inner_32'
  )

  # op_extract_inner_32 snippet
  snip2 = SnippetBuilder.new('op_extract_inner_32')
  inp = snip2.input(0, 32)
  lsb = snip2.input(1, 32)
  width = snip2.input(2, 32)
  c32 = snip2.const(32)
  t1 = snip2.sub(c32, lsb)
  shift_l = snip2.sub(t1, width)
  temp = snip2.lsl(inp, shift_l)
  shift_r = snip2.sub(c32, width)
  temp2 = snip2.lsr(temp, shift_r)
  snip2.output(temp2, 0)
  extract_inner_snip = snip2.build
  op_extract_inner = Operation.new(
    'extract_inner_32', [], [32,32,32], [32],
    semantic_base: nil, semantic_func: 'op_extract_inner_32'
  )

  # op_orr_shifted_32 snippet
  snip3 = SnippetBuilder.new('op_orr_shifted_32')
  data = snip3.input(0, 32)
  lsb = snip3.input(1, 32)
  value = snip3.input(2, 32)
  insert = snip3.lsl(value, lsb)
  r = snip3.orr(data, insert)
  snip3.output(r, 0)
  orr_shifted_snip = snip3.build
  op_orr_shifted = Operation.new(
    'orr_shifted_32', [], [32,32,32], [32],
    semantic_base: nil, semantic_func: 'op_orr_shifted_32'
  )

  # decode helpers
  def make_decode_extract(name, shift)
    snip = SnippetBuilder.new(name)
    enc = snip.input(0, 32)
    shift_const = snip.const(shift)
    shifted = snip.lsr(enc, shift_const)
    r = snip.extract_low(shifted, 5)
    snip.output(r, 0)
    snip.build
  end

  decode_rs1 = make_decode_extract('decode_b_rs1', 15)
  decode_rs2 = make_decode_extract('decode_b_rs2', 20)

  # decode_b_imm
  snip4 = SnippetBuilder.new('decode_b_imm')
  enc = snip4.input(0, 32)
  c1 = snip4.const(1); c4 = snip4.const(4); c5 = snip4.const(5); c6 = snip4.const(6)
  c7 = snip4.const(7); c8 = snip4.const(8); c11 = snip4.const(11); c12 = snip4.const(12)
  c13 = snip4.const(13); c25 = snip4.const(25); c31 = snip4.const(31)

  t1 = snip4.op(op_extract_inner, [enc, c31, c1])
  t2 = snip4.op(op_extract_inner, [enc, c25, c6])
  t3 = snip4.op(op_extract_inner, [enc, c8, c4])
  t4 = snip4.op(op_extract_inner, [enc, c7, c1])
  t5 = snip4.const(0)
  t6 = snip4.op(op_orr_shifted, [t5, t1, c12])
  t7 = snip4.op(op_orr_shifted, [t5, t1, c11])
  t8 = snip4.op(op_orr_shifted, [t5, t1, c5])
  t9 = snip4.op(op_orr_shifted, [t5, t1, c1])
  imm_sext = snip4.op(op_extend_sign, [t9, c13])
  snip4.output(imm_sext, 0)
  decode_imm = snip4.build

  # encode_b
  snip5 = SnippetBuilder.new('encode_b')
  rs1 = snip5.input(0, 5)
  rs2 = snip5.input(1, 5)
  imm = snip5.input(2, 32)
  base = snip5.dyn_const('enc_base', 32)
  c15 = snip5.const(15); c20 = snip5.const(20)
  t1 = snip5.op(op_orr_shifted, [base, rs1, c15])
  t2 = snip5.op(op_orr_shifted, [t1, rs2, c20])
  r = snip5.orr(t2, imm)
  snip5.output(r, 0)
  encode_b_snip = snip5.build

  # blt instruction
  enc_blt = InstructionEncoding.new(32, (0b100 << 12) + 0b1100011,
                                    ['decode_b_rs1', 'decode_b_rs2', 'decode_b_imm'],
                                    'encode_b', '', '')
  instr_builder = InstructionBuilder.new('blt', [5,5,32], ['x1','x2','offset'], enc_blt)
  x1 = instr_builder.add_input_operand(0, 5)
  x2 = instr_builder.add_input_operand(1, 5)
  offset = instr_builder.add_input_operand(2, 32)
  v1 = instr_builder.read(rf, x1)
  v2 = instr_builder.read(rf, x2)
  cond = instr_builder.slt(v1, v2)
  base = instr_builder.env(pc_read, [])[0]
  dest = instr_builder.add(base, offset)
  instr_builder.cond_env(pc_write, cond, [dest], [])
  blt_instr = instr_builder.build

  arch_builder = ArchBuilder.new('test_arch', ['attr.1', 'attr.2'])
  arch_builder.add_register_file(rf)
  arch_builder.add_env_func(ld32).add_env_func(st32).add_env_func(pc_read).add_env_func(pc_write)
  arch_builder.add_operation(op_extend_sign).add_operation(op_extract_inner).add_operation(op_orr_shifted)
  arch_builder.add_snippet(extend_sign_inner).add_snippet(extract_inner_snip).add_snippet(orr_shifted_snip)
  arch_builder.add_snippet(decode_rs1).add_snippet(decode_rs2).add_snippet(decode_imm).add_snippet(encode_b_snip)
  arch_builder.add_instruction(blt_instr)

  arch_builder.build
end

def main
  options = {}
  opt_parser = OptionParser.new do |opts|
    opts.banner = "Usage: #{$0} [options]"

    opts.on("--output PATH", "Output file or directory (required)") do |path|
      options[:output] = path
    end

    opts.on("--format FORMAT", [:txt, :yaml], "Serialization format (txt or yaml, default: yaml)") do |fmt|
      options[:format] = fmt
    end

    opts.on("--help", "Show this help message") do
      puts opts
      exit
    end
  end

  begin
    opt_parser.parse!
  rescue OptionParser::InvalidOption => e
    puts e
    puts opt_parser
    exit 1
  end

  if options[:output].nil?
    puts "Error: --output is required"
    puts opt_parser
    exit 1
  end

  output_path = options[:output]
  format = options[:format] || :yaml

  arch = build_test_arch

  if format == :txt
    ArchSerTxt.write_arch(arch, output_path)
    arch2 = ArchSerTxt.read_arch(output_path)
  elsif format == :yaml
    ArchSerYaml.write_arch(arch, output_path)
    arch2 = ArchSerYaml.read_arch(output_path)
  else
    raise "Unknown format: #{format}"
  end

  if arch == arch2
    puts "Integration test passed"
  else
    puts "Integration test failed"
    exit 1
  end
end

main if __FILE__ == $0
