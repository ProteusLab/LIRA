require_relative 'arch'

module LIRA
  ArchIndex = Struct.new(:rf, :sr, :env, :tables, :op, :snippet, :instr, keyword_init: true)

  def self.build_arch_index(arch)
    ArchIndex.new(
      rf: arch.register_files.to_h { |rf| [rf.name, rf] },
      sr: arch.system_registers.to_h { |sr| [sr.name, sr] },
      env: arch.environment_functions.to_h { |env| [env.name, env] },
      tables: arch.tables_int.to_h { |t| [t.name, t] },
      op: arch.operations.to_h { |op| [op.name, op] },
      snippet: arch.snippets.to_h { |sn| [sn.name, sn] },
      instr: arch.instructions.to_h { |ins| [ins.name, ins] }
    )
  end
end
