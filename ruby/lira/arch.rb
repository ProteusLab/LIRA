# lira/arch.rb
require 'set'

module Lira
  class Component
    attr_accessor :name, :attributes

    def initialize(name, attributes = [])
      @name = name
      @attributes = attributes
    end

    def ==(other)
      other.is_a?(Component) && name == other.name && attributes == other.attributes
    end
  end

  class Snippet
    attr_accessor :name, :seq

    def initialize(name, seq)
      @name = name
      @seq = seq
    end

    def ==(other)
      other.is_a?(Snippet) && name == other.name && seq == other.seq
    end
  end

  class Operation < Component
    attr_accessor :inputs, :outputs, :semantic_base, :semantic_func, :semantic_func_128, :semantic_table

    def initialize(name, attributes, inputs, outputs,
                   semantic_base: nil, semantic_func: nil, semantic_func_128: nil, semantic_table: nil)
      super(name, attributes)
      @inputs = inputs
      @outputs = outputs
      @semantic_base = semantic_base
      @semantic_func = semantic_func
      @semantic_func_128 = semantic_func_128
      @semantic_table = semantic_table
    end

    def ==(other)
      super(other) &&
        other.is_a?(Operation) &&
        inputs == other.inputs &&
        outputs == other.outputs &&
        semantic_base == other.semantic_base &&
        semantic_func == other.semantic_func &&
        semantic_func_128 == other.semantic_func_128 &&
        semantic_table == other.semantic_table
    end
  end

  class RegisterFile < Component
    attr_accessor :reg_size, :reg_names

    def initialize(name, attributes, reg_size, reg_names)
      super(name, attributes)
      @reg_size = reg_size
      @reg_names = reg_names
    end

    def regs_num
      reg_names.length
    end

    def ==(other)
      super(other) &&
        other.is_a?(RegisterFile) &&
        reg_size == other.reg_size &&
        reg_names == other.reg_names
    end
  end

  class EnvironmentFunction < Component
    attr_accessor :inputs, :outputs

    def initialize(name, attributes, inputs, outputs)
      super(name, attributes)
      @inputs = inputs
      @outputs = outputs
    end

    def ==(other)
      super(other) &&
        other.is_a?(EnvironmentFunction) &&
        inputs == other.inputs &&
        outputs == other.outputs
    end
  end

  class SystemRegisterField < Component
    attr_accessor :lsb, :msb

    def initialize(name, attributes, lsb, msb)
      super(name, attributes)
      @lsb = lsb
      @msb = msb
    end

    def ==(other)
      super(other) &&
        other.is_a?(SystemRegisterField) &&
        lsb == other.lsb &&
        msb == other.msb
    end
  end

  class SystemRegister < Component
    attr_accessor :size, :fields

    def initialize(name, attributes, size, fields)
      super(name, attributes)
      @size = size
      @fields = fields
    end

    def ==(other)
      super(other) &&
        other.is_a?(SystemRegister) &&
        size == other.size &&
        fields == other.fields
    end
  end

  class TableInt < Component
    attr_accessor :values

    def initialize(name, attributes, values)
      super(name, attributes)
      @values = values
    end

    def ==(other)
      super(other) &&
        other.is_a?(TableInt) &&
        values == other.values
    end
  end

  class InstructionEncoding
    attr_accessor :encoded_size, :const_encoding_part, :decode, :encode,
                  :constraint_decode, :constraint_encode

    def initialize(encoded_size, const_encoding_part, decode, encode, constraint_decode, constraint_encode)
      @encoded_size = encoded_size
      @const_encoding_part = const_encoding_part
      @decode = decode
      @encode = encode
      @constraint_decode = constraint_decode
      @constraint_encode = constraint_encode
    end

    def ==(other)
      other.is_a?(InstructionEncoding) &&
        encoded_size == other.encoded_size &&
        const_encoding_part == other.const_encoding_part &&
        decode == other.decode &&
        encode == other.encode &&
        constraint_decode == other.constraint_decode &&
        constraint_encode == other.constraint_encode
    end
  end

  class Instruction < Component
    attr_accessor :operand_sizes, :operand_names, :encoding, :semantic

    def initialize(name, attributes, operand_sizes, operand_names, encoding, semantic)
      super(name, attributes)
      @operand_sizes = operand_sizes
      @operand_names = operand_names
      @encoding = encoding
      @semantic = semantic
    end

    def ==(other)
      super(other) &&
        other.is_a?(Instruction) &&
        operand_sizes == other.operand_sizes &&
        operand_names == other.operand_names &&
        encoding == other.encoding &&
        semantic == other.semantic
    end
  end

  class Arch < Component
    attr_accessor :register_files, :system_registers, :environment_functions,
                  :tables_int, :operations, :snippets, :instructions

    def initialize(name, attributes,
                   register_files: [],
                   system_registers: [],
                   environment_functions: [],
                   tables_int: [],
                   operations: [],
                   snippets: [],
                   instructions: [])
      super(name, attributes)
      @register_files = register_files
      @system_registers = system_registers
      @environment_functions = environment_functions
      @tables_int = tables_int
      @operations = operations
      @snippets = snippets
      @instructions = instructions
    end

    def ==(other)
      super(other) &&
        other.is_a?(Arch) &&
        register_files == other.register_files &&
        system_registers == other.system_registers &&
        environment_functions == other.environment_functions &&
        tables_int == other.tables_int &&
        operations == other.operations &&
        snippets == other.snippets &&
        instructions == other.instructions
    end
  end
end
