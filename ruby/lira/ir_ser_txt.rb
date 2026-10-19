# lira/ir_ser_txt.rb
require_relative 'ir'

def serialize_shape(shape)
  "#{shape.lanes_base}#{shape.lanes_mult}"
end

def deserialize_shape(s)
  m = s.match(/^(\d+)(.*)$/)
  Shape.new(m[1].to_i, m[2].empty? ? nil : m[2])
end

def serialize_statement(stmt)
  shape_str = serialize_shape(stmt.shape)
  out_parts = stmt.outputs_types.zip(stmt.outputs).flat_map { |typ, name| [typ.to_s, name] }
  parts = [shape_str] + out_parts + ['=', stmt.kind, stmt.specifier] + stmt.inputs
  parts.join(' ')
end

def deserialize_statement(s)
  tokens = s.split
  eq = tokens.index('=')
  raise "invalid statement: #{s}: missing \"=\"" unless eq

  left = tokens[0...eq]
  right = tokens[(eq + 1)..]
  raise "invalid statement: #{s}: missing shape" if left.empty?
  raise "invalid statement: #{s}: missing kind or specifier" if right.length < 2

  shape = deserialize_shape(left[0])
  output_tokens = left[1..]
  raise "invalid statement: #{s}: outputs must be type/name pairs" if output_tokens.length.odd?

  outputs_types = output_tokens.each_slice(2).map { |typ, _name| typ.to_i }
  outputs = output_tokens.each_slice(2).map { |_typ, name| name }
  Statement.new(shape, outputs, outputs_types, right[0], right[1], right.drop(2))
end

def serialize_statement_seq(seq)
  seq.stmts.map { |s| "#{serialize_statement(s)}\n" }.join
end

def deserialize_statement_seq(s)
  stmts = s.each_line.filter_map do |raw|
    line = raw.strip
    next if line.empty? || line.start_with?('#')
    deserialize_statement(line)
  end
  StatementSeq.new(stmts)
end
