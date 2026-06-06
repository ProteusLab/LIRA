# lira/arch_ser_txt.rb
require 'json'
require 'pathname'
require 'fileutils'
require_relative 'ir'
require_relative 'arch'

module Lira
  module ArchSerTxt
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

    def from_serializable(klass, data, item_class = nil)
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
        if item_class
          return data.map { |elem| from_serializable(item_class, elem) }
        else
          return data.map { |elem| from_serializable(Object, elem) }
        end
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
          from_serializable(Array, data['fields'], SystemRegisterField)
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

    def write_json(data, path)
      File.write(path, JSON.pretty_generate(data))
    end

    def write_component_list(list, path)
      write_json(list.map { |obj| to_serializable(obj) }, path)
    end

    def write_arch(arch, folder_path)
      folder_path = Pathname.new(folder_path)
      FileUtils.rm_rf(folder_path) if folder_path.exist?
      FileUtils.mkdir_p(folder_path)

      write_json({ 'name' => arch.name, 'attributes' => arch.attributes }, folder_path / 'arch.json')

      write_component_list(arch.register_files, folder_path / 'register_files.json')
      write_component_list(arch.system_registers, folder_path / 'system_registers.json')
      write_component_list(arch.environment_functions, folder_path / 'environment_functions.json')
      write_component_list(arch.tables_int, folder_path / 'tables_int.json')

      index = {
        'operations' => arch.operations.map(&:name),
        'snippets' => arch.snippets.map(&:name),
        'instructions' => arch.instructions.map(&:name)
      }
      write_json(index, folder_path / 'index.json')

      ops_dir = folder_path / 'operations'
      FileUtils.mkdir_p(ops_dir)
      arch.operations.each do |op|
        write_json(to_serializable(op), ops_dir / "#{op.name}.json")
      end

      snippets_dir = folder_path / 'snippets'
      FileUtils.mkdir_p(snippets_dir)
      arch.snippets.each do |snip|
        File.write(snippets_dir / "#{snip.name}.lira", IrSerTxt.serialize_statement_seq(snip.seq))
      end

      instr_dir = folder_path / 'instructions'
      FileUtils.mkdir_p(instr_dir)
      arch.instructions.each do |instr|
        instr_dict = to_serializable(instr)
        instr_dict.delete('semantic')
        write_json(instr_dict, instr_dir / "#{instr.name}.json")
        File.write(instr_dir / "#{instr.name}.lira", IrSerTxt.serialize_statement_seq(instr.semantic))
      end
    end

    def load_json(path)
      JSON.parse(File.read(path))
    end

    def load_lira(path)
      content = File.read(path)
      IrSerTxt.deserialize_statement_seq(content)
    end

    def load_operation(folder, name)
      data = load_json(folder / 'operations' / "#{name}.json")
      from_serializable(Operation, data)
    end

    def load_snippet(folder, name)
      seq = load_lira(folder / 'snippets' / "#{name}.lira")
      Snippet.new(name, seq)
    end

    def load_instruction(folder, name)
      data = load_json(folder / 'instructions' / "#{name}.json")
      semantic = load_lira(folder / 'instructions' / "#{name}.lira")
      from_serializable(Instruction, data.merge('semantic' => IrSerTxt.serialize_statement_seq(semantic)))
    end

    def read_arch(folder_path)
      folder_path = Pathname.new(folder_path)

      arch_info = load_json(folder_path / 'arch.json')
      name = arch_info['name']
      attributes = arch_info['attributes']

      register_files = from_serializable(Array, load_json(folder_path / 'register_files.json'), RegisterFile)
      system_registers = from_serializable(Array, load_json(folder_path / 'system_registers.json'), SystemRegister)
      environment_functions = from_serializable(Array, load_json(folder_path / 'environment_functions.json'), EnvironmentFunction)
      tables_int = from_serializable(Array, load_json(folder_path / 'tables_int.json'), TableInt)

      index = load_json(folder_path / 'index.json')
      op_names = index['operations']
      snippet_names = index['snippets']
      instr_names = index['instructions']

      operations = op_names.map { |n| load_operation(folder_path, n) }
      snippets = snippet_names.map { |n| load_snippet(folder_path, n) }
      instructions = instr_names.map { |n| load_instruction(folder_path, n) }

      Arch.new(
        name,
        attributes,
        register_files: register_files,
        system_registers: system_registers,
        environment_functions: environment_functions,
        tables_int: tables_int,
        operations: operations,
        snippets: snippets,
        instructions: instructions
      )
    end
  end
end
