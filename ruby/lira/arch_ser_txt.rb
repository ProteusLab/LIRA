require 'json'
require 'fileutils'
require 'pathname'
require_relative 'arch'
require_relative 'ir_ser_txt'

module LIRA
  module ArchSerTxt
    def self.write_arch(arch, folder_path)
      folder_path = Pathname.new(folder_path)
      FileUtils.rm_rf(folder_path) if folder_path.exist?
      folder_path.mkpath

      File.write(folder_path / 'arch.json', JSON.pretty_generate({ 'name' => arch.name, 'attributes' => arch.attributes }))

      File.write(folder_path / 'register_files.json', JSON.pretty_generate(arch.register_files.map(&:to_h)))
      File.write(folder_path / 'system_registers.json', JSON.pretty_generate(arch.system_registers.map(&:to_h)))
      File.write(folder_path / 'environment_functions.json', JSON.pretty_generate(arch.environment_functions.map(&:to_h)))
      File.write(folder_path / 'tables_int.json', JSON.pretty_generate(arch.tables_int.map(&:to_h)))

      index = {
        'operations' => arch.operations.map(&:name),
        'snippets' => arch.snippets.map(&:name),
        'instructions' => arch.instructions.map(&:name)
      }
      File.write(folder_path / 'index.json', JSON.pretty_generate(index))

      ops_dir = folder_path / 'operations'
      ops_dir.mkpath
      arch.operations.each do |op|
        File.write(ops_dir / "#{op.name}.json", JSON.pretty_generate(op.to_h))
      end

      snippets_dir = folder_path / 'snippets'
      snippets_dir.mkpath
      arch.snippets.each do |snip|
        File.write(snippets_dir / "#{snip.name}.lira.txt", IrSerTxt.serialize_statement_seq(snip.seq))
      end

      instr_dir = folder_path / 'instructions'
      instr_dir.mkpath
      arch.instructions.each do |instr|
        instr_hash = instr.to_h
        instr_hash.delete('semantic')
        File.write(instr_dir / "#{instr.name}.json", JSON.pretty_generate(instr_hash))
        File.write(instr_dir / "#{instr.name}.lira.txt", IrSerTxt.serialize_statement_seq(instr.semantic))
      end
    end

    def self.read_arch(folder_path)
      folder_path = Pathname.new(folder_path)

      load_json = ->(path) { JSON.parse(File.read(path)) }

      arch_info = load_json.call(folder_path / 'arch.json')
      name = arch_info['name']
      attributes = arch_info['attributes']

      register_files = load_json.call(folder_path / 'register_files.json').map { |h| RegisterFile.from_h(h) }
      system_registers = load_json.call(folder_path / 'system_registers.json').map { |h| SystemRegister.from_h(h) }
      environment_functions = load_json.call(folder_path / 'environment_functions.json').map { |h| EnvironmentFunction.from_h(h) }
      tables_int = load_json.call(folder_path / 'tables_int.json').map { |h| TableInt.from_h(h) }

      index = load_json.call(folder_path / 'index.json')
      op_names = index['operations']
      snippet_names = index['snippets']
      instr_names = index['instructions']

      operations = op_names.map do |name|
        data = load_json.call(folder_path / 'operations' / "#{name}.json")
        Operation.from_h(data)
      end

      snippets = snippet_names.map do |name|
        seq = IrSerTxt.deserialize_statement_seq(File.read(folder_path / 'snippets' / "#{name}.lira.txt"))
        Snippet.new(name: name, attributes: [], seq: seq)
      end

      instructions = instr_names.map do |name|
        instr_data = load_json.call(folder_path / 'instructions' / "#{name}.json")
        semantic = IrSerTxt.deserialize_statement_seq(File.read(folder_path / 'instructions' / "#{name}.lira.txt"))
        instr = Instruction.from_h(instr_data)
        Instruction.new(
          name: instr.name,
          attributes: instr.attributes,
          operand_sizes: instr.operand_sizes,
          operand_names: instr.operand_names,
          encoding: instr.encoding,
          semantic: semantic
        )
      end

      Arch.new(
        name: name,
        attributes: attributes,
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
