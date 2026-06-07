# lira/ir_builder.rb
require_relative 'ir'
require_relative 'arch'
require_relative 'ir_ops'

module Lira
  class Value
    attr_accessor :name, :width

    def initialize(name, width = 32)
      @name = name
      @width = width
    end

    def to_s
      name
    end

    def inspect
      "Value(#{name}, #{width})"
    end

    def ==(other)
      other.is_a?(Value) && name == other.name && width == other.width
    end
  end

  class SeqBuilder
    attr_reader :stmts, :temp_counter, :op_cache

    def initialize
      @stmts = []
      @temp_counter = 0
      @op_cache = {}
    end

    def new_temp(width = 32)
      @temp_counter += 1
      Value.new("_t#{@temp_counter}", width)
    end

    def get_or_create_op(op_class, *args)
      key = [op_class, args]
      @op_cache[key] ||= op_class.new(*args)
    end

    def add(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Add, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def sub(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Sub, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def mul(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Mul, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def and_(a, b)
      check_width_match(a, b)
      op = get_or_create_op(And, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def orr(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Orr, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def xor(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Xor, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def lsl(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Lsl, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def lsr(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Lsr, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def asr(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Asr, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def slt(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Slt, a.width)
      out = new_temp(1)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def extend_sign(a, to_width)
      raise "extend_sign: input width #{a.width} >= output width #{to_width}" if a.width >= to_width
      op = get_or_create_op(ExtendSign, a.width, to_width)
      out = new_temp(to_width)
      add_op(op, [a.name], [out.name])
      out
    end

    def extend_zero(a, to_width)
      raise "extend_zero: input width #{a.width} >= output width #{to_width}" if a.width >= to_width
      op = get_or_create_op(ExtendZero, a.width, to_width)
      out = new_temp(to_width)
      add_op(op, [a.name], [out.name])
      out
    end

    def popcnt(a)
      op = get_or_create_op(Popcnt, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name], [out.name])
      out
    end

    def ctz(a)
      op = get_or_create_op(Ctz, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name], [out.name])
      out
    end

    def clz(a)
      op = get_or_create_op(Clz, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name], [out.name])
      out
    end

    def reverse(a)
      op = get_or_create_op(Reverse, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name], [out.name])
      out
    end

    def rem_u(a, b)
      check_width_match(a, b)
      op = get_or_create_op(RemU, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def rem_s(a, b)
      check_width_match(a, b)
      op = get_or_create_op(RemS, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def ror(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Ror, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def rol(a, b)
      check_width_match(a, b)
      op = get_or_create_op(Rol, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def add_overflow(a, b)
      check_width_match(a, b)
      op = get_or_create_op(AddOverflow, a.width)
      out = new_temp(1)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def sub_overflow(a, b)
      check_width_match(a, b)
      op = get_or_create_op(SubOverflow, a.width)
      out = new_temp(1)
      add_op(op, [a.name, b.name], [out.name])
      out
    end

    def div_u(a, b, default)
      check_width_match(a, b)
      raise "div_u: default width mismatch" if a.width != default.width
      op = get_or_create_op(DivU, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name, default.name], [out.name])
      out
    end

    def div_s(a, b, default)
      check_width_match(a, b)
      raise "div_s: default width mismatch" if a.width != default.width
      op = get_or_create_op(DivS, a.width)
      out = new_temp(a.width)
      add_op(op, [a.name, b.name, default.name], [out.name])
      out
    end

    def select(cond, true_val, false_val)
      raise "select: condition must be 1-bit" unless cond.width == 1
      raise "select: true/false widths mismatch" unless true_val.width == false_val.width
      op = get_or_create_op(Select, true_val.width)
      out = new_temp(true_val.width)
      add_op(op, [cond.name, true_val.name, false_val.name], [out.name])
      out
    end

    def concat(low, high)
      low_width = low.width
      high_width = high.width
      total_width = low_width + high_width

      high_ext = extend_zero(high, total_width)
      shift_width = (low_width.bit_length + 1) rescue 1
      shift_amount = const(low_width, shift_width)
      high_shifted = lsl(high_ext, shift_amount)
      low_ext = extend_zero(low, total_width)
      orr(low_ext, high_shifted)
    end

    def extract_low(a, out_width)
      raise "extract_low: output width #{out_width} > input width #{a.width}" if out_width > a.width
      op = get_or_create_op(ExtractLow, a.width, out_width)
      out = new_temp(out_width)
      add_op(op, [a.name], [out.name])
      out
    end

    def extract(value, start, out_width)
      start = extend_zero(start, value.width) if start.width != value.width
      shifted = lsr(value, start)
      extract_low(shifted, out_width)
    end

    # Register & memory
    def read(rf, rsi, shape = Shape.new(1, nil))
      width = rf.reg_size.lanes_base
      out = new_temp(width)
      stmt = Statement.new(shape, [out.name], [width], 'read', rf.name, [rsi.to_s])
      @stmts << stmt
      out
    end

    def write(rf, rsi, value, shape = Shape.new(1, nil))
      stmt = Statement.new(shape, [], [], 'write', rf.name, [rsi.to_s, value.to_s])
      @stmts << stmt
    end

    def const(value, width = 32)
      out = new_temp(width)
      stmt = Statement.new(Shape.new(1, nil), [out.name], [width], 'const', value.to_s, [])
      @stmts << stmt
      out
    end

    def dyn_const(name, width = 32)
      out = new_temp(width)
      stmt = Statement.new(Shape.new(1, nil), [out.name], [width], 'dyn_const', name, [])
      @stmts << stmt
      out
    end

    def env(env_func, inputs)
      outputs = env_func.outputs.map { |w| new_temp(w) }
      stmt = Statement.new(
        Shape.new(1, nil),
        outputs.map(&:name),
        env_func.outputs,
        'env',
        env_func.name,
        inputs.map(&:to_s)
      )
      @stmts << stmt
      outputs
    end

    def cond_env(env_func, cond, inputs, on_false)
      outputs = env_func.outputs.map { |w| new_temp(w) }
      all_inputs = [cond.to_s] + inputs.map(&:to_s) + on_false.map(&:to_s)
      stmt = Statement.new(
        Shape.new(1, nil),
        outputs.map(&:name),
        env_func.outputs,
        'cond_env',
        env_func.name,
        all_inputs
      )
      @stmts << stmt
      outputs
    end

    def input(idx, width = 32)
      out = new_temp(width)
      stmt = Statement.new(Shape.new(1, nil), [out.name], [width], 'input', idx.to_s, [])
      @stmts << stmt
      out
    end

    def output(value, idx)
      stmt = Statement.new(Shape.new(1, nil), [], [], 'output', idx.to_s, [value.to_s])
      @stmts << stmt
    end

    def add_op(operation, inputs, outputs, shape = Shape.new(1, nil))
      stmt = Statement.new(shape, outputs, operation.outputs, 'op', operation.name, inputs)
      @stmts << stmt
    end

    def op(operation, inputs)
      raise "Operation #{operation.name} has #{operation.outputs.size} outputs, use op_multi" if operation.outputs.size != 1
      out = new_temp(operation.outputs.first)
      add_op(operation, inputs.map(&:to_s), [out.name])
      out
    end

    def op_multi(operation, inputs)
      outputs = operation.outputs.map { |w| new_temp(w) }
      add_op(operation, inputs.map(&:to_s), outputs.map(&:name))
      outputs
    end

    def build
      StatementSeq.new(@stmts)
    end

    def +(other)
      @stmts.concat(other.stmts)
      @temp_counter = [@temp_counter, other.temp_counter].max
      self
    end

    private

    def check_width_match(a, b)
      raise "width mismatch: #{a.width} vs #{b.width}" if a.width != b.width
    end
  end

  class BaseBuilder
    attr_reader :seq

    def initialize
      @seq = SeqBuilder.new
    end

    def add(a, b) = @seq.add(a, b)
    def sub(a, b) = @seq.sub(a, b)
    def mul(a, b) = @seq.mul(a, b)
    def and_(a, b) = @seq.and_(a, b)
    def orr(a, b) = @seq.orr(a, b)
    def xor(a, b) = @seq.xor(a, b)
    def lsl(a, b) = @seq.lsl(a, b)
    def lsr(a, b) = @seq.lsr(a, b)
    def asr(a, b) = @seq.asr(a, b)
    def slt(a, b) = @seq.slt(a, b)
    def extend_sign(a, to_width) = @seq.extend_sign(a, to_width)
    def extend_zero(a, to_width) = @seq.extend_zero(a, to_width)
    def popcnt(a) = @seq.popcnt(a)
    def ctz(a) = @seq.ctz(a)
    def clz(a) = @seq.clz(a)
    def reverse(a) = @seq.reverse(a)
    def rem_u(a, b) = @seq.rem_u(a, b)
    def rem_s(a, b) = @seq.rem_s(a, b)
    def ror(a, b) = @seq.ror(a, b)
    def rol(a, b) = @seq.rol(a, b)
    def add_overflow(a, b) = @seq.add_overflow(a, b)
    def sub_overflow(a, b) = @seq.sub_overflow(a, b)
    def div_u(a, b, default) = @seq.div_u(a, b, default)
    def div_s(a, b, default) = @seq.div_s(a, b, default)
    def select(cond, true_val, false_val) = @seq.select(cond, true_val, false_val)
    def concat(low, high) = @seq.concat(low, high)
    def extract_low(a, out_width) = @seq.extract_low(a, out_width)
    def extract(value, start, out_width) = @seq.extract(value, start, out_width)

    def read(rf, rsi, shape = Shape.new(1, nil)) = @seq.read(rf, rsi, shape)
    def write(rf, rsi, value, shape = Shape.new(1, nil)) = @seq.write(rf, rsi, value, shape)
    def const(value, width = 32) = @seq.const(value, width)
    def dyn_const(name, width = 32) = @seq.dyn_const(name, width)
    def env(env_func, inputs) = @seq.env(env_func, inputs)
    def cond_env(env_func, cond, inputs, on_false) = @seq.cond_env(env_func, cond, inputs, on_false)
    def input(idx, width = 32) = @seq.input(idx, width)
    def output(value, idx) = @seq.output(value, idx)
    def op(operation, inputs) = @seq.op(operation, inputs)
    def op_multi(operation, inputs) = @seq.op_multi(operation, inputs)
  end

  class SnippetBuilder < BaseBuilder
    attr_reader :name

    def initialize(name)
      super()
      @name = name
    end

    def build
      Snippet.new(@name, @seq.build)
    end
  end

  class InstructionBuilder < BaseBuilder
    attr_reader :name, :operand_sizes, :operand_names, :encoding

    def initialize(name, operand_sizes, operand_names, encoding)
      super()
      @name = name
      @operand_sizes = operand_sizes
      @operand_names = operand_names
      @encoding = encoding
    end

    def add_input_operand(idx, width = nil)
      w = width || (@operand_sizes[idx] if idx < @operand_sizes.size) || 32
      input(idx, w)
    end

    def build
      Instruction.new(
        @name, [],
        @operand_sizes, @operand_names,
        @encoding,
        @seq.build
      )
    end
  end

  class ArchBuilder
    attr_reader :name, :attributes, :register_files, :system_registers,
                :environment_functions, :tables_int, :operations,
                :snippets, :instructions

    def initialize(name, attributes = [])
      @name = name
      @attributes = attributes
      @register_files = []
      @system_registers = []
      @environment_functions = []
      @tables_int = []
      @operations = []
      @snippets = []
      @instructions = []
    end

    def add_register_file(rf)
      @register_files << rf
      self
    end

    def add_system_register(sr)
      @system_registers << sr
      self
    end

    def add_env_func(env)
      @environment_functions << env
      self
    end

    def add_table_int(table)
      @tables_int << table
      self
    end

    def add_operation(op)
      @operations << op
      self
    end

    def add_snippet(snippet)
      @snippets << snippet
      self
    end

    def add_instruction(instr)
      @instructions << instr
      self
    end

    def build
      Arch.new(
        @name, @attributes,
        register_files: @register_files,
        system_registers: @system_registers,
        environment_functions: @environment_functions,
        tables_int: @tables_int,
        operations: @operations,
        snippets: @snippets,
        instructions: @instructions
      )
    end
  end
end
