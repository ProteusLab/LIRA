require_relative 'ir'

module LIRA
  module IrSerTxt
    def self.serialize_shape(shape)
      "#{shape.lanes_base}#{shape.lanes_mult || ''}"
    end

    def self.deserialize_shape(str)
      if str =~ /^(\d+)(.*)$/
        Shape.new($1.to_i, $2.empty? ? nil : $2)
      else
        raise "Invalid shape string: #{str}"
      end
    end

    def self.serialize_statement(stmt)
      shape_str = serialize_shape(stmt.shape)
      outputs_parts = stmt.outputs_types.zip(stmt.outputs).flat_map { |typ, name| [typ.to_s, name] }
      parts = [shape_str] + outputs_parts + ["=", stmt.kind, stmt.specifier] + stmt.inputs
      parts.join(" ")
    end

    def self.deserialize_statement(str)
      match = str.match(/^(\w+)\s+(.*?)\s*=\s*(\w+)\s+(\S+)\s*(.*)$/)
      raise "Invalid statement: #{str}" unless match
      shape_str, outputs_str, kind, specifier, inputs_str = match.captures
      shape = deserialize_shape(shape_str)
      output_parts = outputs_str.split
      outputs_types = output_parts.each_slice(2).map { |typ, _| typ.to_i }
      outputs = output_parts.each_slice(2).map { |_, name| name }
      inputs = inputs_str.empty? ? [] : inputs_str.split
      Statement.new(shape: shape, outputs: outputs, outputs_types: outputs_types,
                    kind: kind, specifier: specifier, inputs: inputs)
    end

    def self.serialize_statement_seq(seq)
      seq.stmts.map { |s| serialize_statement(s) + ";" }.join("\n")
    end

    def self.deserialize_statement_seq(str)
      raw_stmts = str.split(";").map(&:strip).reject(&:empty?)
      stmts = raw_stmts.map { |raw| deserialize_statement(raw) }
      StatementSeq.new(stmts)
    end
  end
end
