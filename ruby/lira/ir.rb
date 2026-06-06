# lira/ir.rb
require 'set'

module Lira
  class Shape
    attr_accessor :lanes_base, :lanes_mult

    def initialize(lanes_base, lanes_mult)
      @lanes_base = lanes_base
      @lanes_mult = lanes_mult
    end

    def ==(other)
      other.is_a?(Shape) && lanes_base == other.lanes_base && lanes_mult == other.lanes_mult
    end
  end

  class Statement
    attr_accessor :shape, :outputs, :outputs_types, :kind, :specifier, :inputs

    def initialize(shape, outputs, outputs_types, kind, specifier, inputs)
      @shape = shape
      @outputs = outputs
      @outputs_types = outputs_types
      @kind = kind
      @specifier = specifier
      @inputs = inputs
    end

    def ==(other)
      other.is_a?(Statement) &&
        shape == other.shape &&
        outputs == other.outputs &&
        outputs_types == other.outputs_types &&
        kind == other.kind &&
        specifier == other.specifier &&
        inputs == other.inputs
    end

    def input(id, seq)
      target = @inputs[id]
      seq.stmts.each do |stmt|
        return stmt if stmt.outputs.include?(target)
      end
      raise "input #{target} not found"
    end
  end

  class StatementSeq
    attr_accessor :stmts

    def initialize(stmts)
      @stmts = stmts
    end

    def ==(other)
      other.is_a?(StatementSeq) && stmts == other.stmts
    end
  end

  module IrSerTxt
    def self.serialize_shape(shape)
      "#{shape.lanes_base}#{shape.lanes_mult || ''}"
    end

    def self.deserialize_shape(s)
      m = s.match(/\A(\d+)(.*)\z/)
      raise "invalid shape: #{s}" unless m
      Shape.new(m[1].to_i, m[2].empty? ? nil : m[2])
    end

    def self.serialize_statement(stmt)
      shape_str = serialize_shape(stmt.shape)
      out_parts = stmt.outputs_types.zip(stmt.outputs).flat_map { |typ, name| [typ.to_s, name] }
      parts = [shape_str] + out_parts + ['=', stmt.kind, stmt.specifier] + stmt.inputs
      parts.join(' ')
    end

    def self.deserialize_statement(s)
      m = s.match(/\A(\w+)\s+(.*?)\s*=\s*(\w+)\s+(\S+)\s*(.*)\z/)
      raise "invalid statement: #{s}" unless m
      shape_str, outputs_str, kind, specifier, inputs_str = m.captures
      shape = deserialize_shape(shape_str)
      pairs = outputs_str.split
      outputs_types = (0...pairs.length).step(2).map { |i| pairs[i].to_i }
      outputs = (0...pairs.length).step(2).map { |i| pairs[i+1] }
      inputs = inputs_str.empty? ? [] : inputs_str.split
      Statement.new(shape, outputs, outputs_types, kind, specifier, inputs)
    end

    def self.serialize_statement_seq(seq)
      seq.stmts.map { |s| serialize_statement(s) + ";\n" }.join
    end

    def self.deserialize_statement_seq(s)
      raw_stmts = s.split(';').map(&:strip).reject(&:empty?)
      stmts = raw_stmts.map { |raw| deserialize_statement(raw) }
      StatementSeq.new(stmts)
    end
  end
end
