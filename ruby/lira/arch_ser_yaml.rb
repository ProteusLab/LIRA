# lira/arch_ser_yaml.rb
require 'yaml'
require_relative 'ir'
require_relative 'arch'

module Lira
  module ArchSerYaml
    module_function

    def to_serializable(obj)
      case obj
      when StatementSeq
        IrSerTxt.serialize_statement_seq(obj)
      when Array
        obj.map { |item| to_serializable(item) }
      when Hash
        obj.transform_values { |v| to_serializable(v) }
      when Shape, Statement, InstructionEncoding, Arch
        hash = {}
        obj.instance_variables.each do |ivar|
          key = ivar.to_s[1..-1]
          value = obj.instance_variable_get(ivar)
          # next if key == 'attributes' && value.is_a?(Array) && value.empty?
          hash[key] = to_serializable(value)
        end
        hash
      when Component
        hash = {}
        obj.instance_variables.each do |ivar|
          key = ivar.to_s[1..-1]
          value = obj.instance_variable_get(ivar)
          # next if key == 'attributes' && value.is_a?(Array) && value.empty?
          hash[key] = to_serializable(value)
        end
        hash
      when Snippet
        { 'name' => obj.name, 'seq' => to_serializable(obj.seq) }
      else
        obj
      end
    end

    def from_serializable(klass, data)
      if klass == Arch
        return Arch.new(
          data['name'],
          data['attributes'] || [],
          register_files: data['register_files'].map { |rf| from_serializable(RegisterFile, rf) },
          system_registers: data['system_registers'].map { |sr| from_serializable(SystemRegister, sr) },
          environment_functions: data['environment_functions'].map { |ef| from_serializable(EnvironmentFunction, ef) },
          tables_int: data['tables_int'].map { |ti| from_serializable(TableInt, ti) },
          operations: data['operations'].map { |op| from_serializable(Operation, op) },
          snippets: data['snippets'].map { |sn| from_serializable(Snippet, sn) },
          instructions: data['instructions'].map { |ins| from_serializable(Instruction, ins) }
        )
      end

      if klass == Array
        return data.map { |elem| from_serializable(Object, elem) }
      end

      if klass == Shape
        lanes_mult = data['lanes_mult']
        lanes_mult = nil if lanes_mult == ''
        return Shape.new(data['lanes_base'], lanes_mult)
      elsif klass == Statement
        return Statement.new(
          from_serializable(Shape, data['shape']),
          data['outputs'],
          data['outputs_types'],
          data['kind'],
          data['specifier'],
          data['inputs']
        )
      elsif klass == StatementSeq
        return IrSerTxt.deserialize_statement_seq(data)
      elsif klass == RegisterFile
        return RegisterFile.new(
          data['name'],
          data['attributes'] || [],
          from_serializable(Shape, data['reg_size']),
          data['reg_names']
        )
      elsif klass == SystemRegister
        return SystemRegister.new(
          data['name'],
          data['attributes'] || [],
          data['size'],
          data['fields'].map { |f| from_serializable(SystemRegisterField, f) }
        )
      elsif klass == SystemRegisterField
        return SystemRegisterField.new(
          data['name'],
          data['attributes'] || [],
          data['lsb'],
          data['msb']
        )
      elsif klass == EnvironmentFunction
        return EnvironmentFunction.new(
          data['name'],
          data['attributes'] || [],
          data['inputs'],
          data['outputs']
        )
      elsif klass == TableInt
        return TableInt.new(
          data['name'],
          data['attributes'] || [],
          data['values']
        )
      elsif klass == Operation
        return Operation.new(
          data['name'],
          data['attributes'] || [],
          data['inputs'],
          data['outputs'],
          semantic_base: data['semantic_base'],
          semantic_func: data['semantic_func'],
          semantic_func_128: data['semantic_func_128'],
          semantic_table: data['semantic_table']
        )
      elsif klass == Snippet
        return Snippet.new(
          data['name'],
          from_serializable(StatementSeq, data['seq'])
        )
      elsif klass == InstructionEncoding
        return InstructionEncoding.new(
          data['encoded_size'],
          data['const_encoding_part'],
          data['decode'],
          data['encode'],
          data['constraint_decode'],
          data['constraint_encode']
        )
      elsif klass == Instruction
        return Instruction.new(
          data['name'],
          data['attributes'] || [],
          data['operand_sizes'],
          data['operand_names'],
          from_serializable(InstructionEncoding, data['encoding']),
          from_serializable(StatementSeq, data['semantic'])
        )
      else
        return data
      end
    end

    def write_arch(arch, filepath)
      data = to_serializable(arch)
      File.write(filepath, YAML.dump(data))
    end

    def read_arch(filepath)
      data = YAML.load_file(filepath)
      from_serializable(Arch, data)
    end
  end
end
