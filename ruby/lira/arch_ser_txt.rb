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
      else
        if obj.respond_to?(:to_h)
          obj.to_h.transform_values { |v| to_serializable(v) }
        else
          obj
        end
      end
    end

    def from_serializable(klass, data, item_class = nil)
      if klass == Array
        if item_class
          return data.map { |elem| from_serializable(item_class, elem) }
        else
          return data.map { |elem| from_serializable(Object, elem) }
        end
      end

      if klass.respond_to?(:from_h)
        # Рекурсивно преобразуем все значения хеша
        transformed = data.transform_values { |v| from_serializable(Object, v) }
        klass.from_h(transformed)
      else
        data
      end
    end

    # Вспомогательные методы для работы с JSON
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
      IrSerTxt.deserialize_statement_seq(File.read(path))
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
      from_serializable(Instruction, data.merge('semantic' => semantic.to_h))
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
