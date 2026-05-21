require_relative 'ir'

module LIRA
  class Component
    attr_reader :name, :attributes
    def initialize(name:, attributes: [])
      @name = name
      @attributes = attributes
    end

    def to_h
      { 'name' => name, 'attributes' => attributes }
    end

    def self.from_h(hash)
      new(name: hash['name'], attributes: hash['attributes'] || [])
    end

    def ==(other)
      other.is_a?(Component) && name == other.name && attributes == other.attributes
    end
  end

  class Snippet < Component
    attr_reader :seq
    def initialize(name:, attributes: [], seq:)
      super(name: name, attributes: attributes)
      @seq = seq
    end

    def to_h
      super.merge('seq' => nil)
    end

    def self.from_h(hash)
      new(name: hash['name'], attributes: hash['attributes'] || [], seq: nil)
    end

    def ==(other)
      super && seq == other.seq
    end
  end

  class Operation < Component
    attr_reader :inputs, :outputs, :semantic_base, :semantic_func, :semantic_func_128, :semantic_table
    def initialize(name:, attributes: [], inputs:, outputs:, semantic_base: nil, semantic_func: nil, semantic_func_128: nil, semantic_table: nil)
      super(name: name, attributes: attributes)
      @inputs = inputs
      @outputs = outputs
      @semantic_base = semantic_base
      @semantic_func = semantic_func
      @semantic_func_128 = semantic_func_128
      @semantic_table = semantic_table
    end

    def to_h
      super.merge({
        'inputs' => inputs,
        'outputs' => outputs,
        'semantic_base' => semantic_base,
        'semantic_func' => semantic_func,
        'semantic_func_128' => semantic_func_128,
        'semantic_table' => semantic_table
      })
    end

    def self.from_h(hash)
      new(
        name: hash['name'],
        attributes: hash['attributes'] || [],
        inputs: hash['inputs'],
        outputs: hash['outputs'],
        semantic_base: hash['semantic_base'],
        semantic_func: hash['semantic_func'],
        semantic_func_128: hash['semantic_func_128'],
        semantic_table: hash['semantic_table']
      )
    end

    def ==(other)
      super &&
        inputs == other.inputs &&
        outputs == other.outputs &&
        semantic_base == other.semantic_base &&
        semantic_func == other.semantic_func &&
        semantic_func_128 == other.semantic_func_128 &&
        semantic_table == other.semantic_table
    end
  end

  class RegisterFile < Component
    attr_reader :reg_size, :reg_names
    def initialize(name:, attributes: [], reg_size:, reg_names:)
      super(name: name, attributes: attributes)
      @reg_size = reg_size
      @reg_names = reg_names
    end

    def regs_num
      reg_names.size
    end

    def to_h
      super.merge({
        'reg_size' => { 'lanes_base' => reg_size.lanes_base, 'lanes_mult' => reg_size.lanes_mult },
        'reg_names' => reg_names
      })
    end

    def self.from_h(hash)
      reg_size_hash = hash['reg_size']
      reg_size = Shape.new(reg_size_hash['lanes_base'], reg_size_hash['lanes_mult'])
      new(
        name: hash['name'],
        attributes: hash['attributes'] || [],
        reg_size: reg_size,
        reg_names: hash['reg_names']
      )
    end

    def ==(other)
      super && reg_size == other.reg_size && reg_names == other.reg_names
    end
  end

  class EnvironmentFunction < Component
    attr_reader :inputs, :outputs
    def initialize(name:, attributes: [], inputs:, outputs:)
      super(name: name, attributes: attributes)
      @inputs = inputs
      @outputs = outputs
    end

    def to_h
      super.merge('inputs' => inputs, 'outputs' => outputs)
    end

    def self.from_h(hash)
      new(name: hash['name'], attributes: hash['attributes'] || [], inputs: hash['inputs'], outputs: hash['outputs'])
    end

    def ==(other)
      super && inputs == other.inputs && outputs == other.outputs
    end
  end

  class SystemRegisterField < Component
    attr_reader :lsb, :msb
    def initialize(name:, attributes: [], lsb:, msb:)
      super(name: name, attributes: attributes)
      @lsb = lsb
      @msb = msb
    end

    def to_h
      super.merge('lsb' => lsb, 'msb' => msb)
    end

    def self.from_h(hash)
      new(name: hash['name'], attributes: hash['attributes'] || [], lsb: hash['lsb'], msb: hash['msb'])
    end

    def ==(other)
      super && lsb == other.lsb && msb == other.msb
    end
  end

  class SystemRegister < Component
    attr_reader :size, :fields
    def initialize(name:, attributes: [], size:, fields:)
      super(name: name, attributes: attributes)
      @size = size
      @fields = fields
    end

    def to_h
      super.merge('size' => size, 'fields' => fields.map(&:to_h))
    end

    def self.from_h(hash)
      fields = hash['fields'].map { |f| SystemRegisterField.from_h(f) }
      new(name: hash['name'], attributes: hash['attributes'] || [], size: hash['size'], fields: fields)
    end

    def ==(other)
      super && size == other.size && fields == other.fields
    end
  end

  class TableInt < Component
    attr_reader :values
    def initialize(name:, attributes: [], values:)
      super(name: name, attributes: attributes)
      @values = values
    end

    def to_h
      super.merge('values' => values)
    end

    def self.from_h(hash)
      new(name: hash['name'], attributes: hash['attributes'] || [], values: hash['values'])
    end

    def ==(other)
      super && values == other.values
    end
  end

  class InstructionEncoding
    attr_reader :encoded_size, :const_encoding_part, :decode, :encode, :constraint_decode, :constraint_encode
    def initialize(encoded_size:, const_encoding_part:, decode:, encode:, constraint_decode:, constraint_encode:)
      @encoded_size = encoded_size
      @const_encoding_part = const_encoding_part
      @decode = decode
      @encode = encode
      @constraint_decode = constraint_decode
      @constraint_encode = constraint_encode
    end

    def to_h
      {
        'encoded_size' => encoded_size,
        'const_encoding_part' => const_encoding_part,
        'decode' => decode,
        'encode' => encode,
        'constraint_decode' => constraint_decode,
        'constraint_encode' => constraint_encode
      }
    end

    def self.from_h(hash)
      new(
        encoded_size: hash['encoded_size'],
        const_encoding_part: hash['const_encoding_part'],
        decode: hash['decode'],
        encode: hash['encode'],
        constraint_decode: hash['constraint_decode'],
        constraint_encode: hash['constraint_encode']
      )
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
    attr_reader :operand_sizes, :operand_names, :encoding, :semantic
    def initialize(name:, attributes: [], operand_sizes:, operand_names:, encoding:, semantic:)
      super(name: name, attributes: attributes)
      @operand_sizes = operand_sizes
      @operand_names = operand_names
      @encoding = encoding
      @semantic = semantic
    end

    def to_h
      super.merge({
        'operand_sizes' => operand_sizes,
        'operand_names' => operand_names,
        'encoding' => encoding.to_h,
        'semantic' => nil
      })
    end

    def self.from_h(hash)
      encoding = InstructionEncoding.from_h(hash['encoding'])
      new(
        name: hash['name'],
        attributes: hash['attributes'] || [],
        operand_sizes: hash['operand_sizes'],
        operand_names: hash['operand_names'],
        encoding: encoding,
        semantic: nil
      )
    end

    def ==(other)
      super &&
        operand_sizes == other.operand_sizes &&
        operand_names == other.operand_names &&
        encoding == other.encoding &&
        semantic == other.semantic
    end
  end

  class Arch < Component
    attr_reader :register_files, :system_registers, :environment_functions, :tables_int,
                :operations, :snippets, :instructions
    def initialize(name:, attributes: [], register_files:, system_registers:, environment_functions:,
                   tables_int:, operations:, snippets:, instructions:)
      super(name: name, attributes: attributes)
      @register_files = register_files
      @system_registers = system_registers
      @environment_functions = environment_functions
      @tables_int = tables_int
      @operations = operations
      @snippets = snippets
      @instructions = instructions
    end

    def to_h
      {
        'name' => name,
        'attributes' => attributes,
        'register_files' => register_files.map(&:to_h),
        'system_registers' => system_registers.map(&:to_h),
        'environment_functions' => environment_functions.map(&:to_h),
        'tables_int' => tables_int.map(&:to_h),
        'operations' => operations.map(&:to_h),
        'snippets' => snippets.map(&:to_h),
        'instructions' => instructions.map(&:to_h)
      }
    end

    def self.from_h(hash)
      new(
        name: hash['name'],
        attributes: hash['attributes'] || [],
        register_files: hash['register_files'].map { |h| RegisterFile.from_h(h) },
        system_registers: hash['system_registers'].map { |h| SystemRegister.from_h(h) },
        environment_functions: hash['environment_functions'].map { |h| EnvironmentFunction.from_h(h) },
        tables_int: hash['tables_int'].map { |h| TableInt.from_h(h) },
        operations: hash['operations'].map { |h| Operation.from_h(h) },
        snippets: hash['snippets'].map { |h| Snippet.from_h(h) },
        instructions: hash['instructions'].map { |h| Instruction.from_h(h) }
      )
    end

    def ==(other)
      other.is_a?(Arch) &&
        name == other.name &&
        attributes == other.attributes &&
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
