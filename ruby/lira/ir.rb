# lira/ir.rb
require 'set'

module Lira
  class Shape
    attr_accessor :lanes_base, :lanes_mult

    def initialize(lanes_base, lanes_mult)
      @lanes_base = lanes_base
      @lanes_mult = lanes_mult
    end

    def to_h
      { lanes_base: lanes_base, lanes_mult: lanes_mult }
    end

    def self.from_h(hash)
      lanes_base = hash[:lanes_base] || hash['lanes_base']
      lanes_mult = hash[:lanes_mult] || hash['lanes_mult']
      lanes_mult = nil if lanes_mult == {}
      new(lanes_base, lanes_mult)
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

    def to_h
      {
        shape: shape.to_h,
        outputs: outputs,
        outputs_types: outputs_types,
        kind: kind,
        specifier: specifier,
        inputs: inputs
      }
    end

    def self.from_h(hash)
      shape = Shape.from_h(hash[:shape] || hash['shape'])
      new(shape,
          hash[:outputs] || hash['outputs'],
          hash[:outputs_types] || hash['outputs_types'],
          hash[:kind] || hash['kind'],
          hash[:specifier] || hash['specifier'],
          hash[:inputs] || hash['inputs'])
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

    def to_h
      { stmts: stmts.map(&:to_h) }
    end

    def self.from_h(data)
      if data.is_a?(String)
        IrSerTxt.deserialize_statement_seq(data)
      else
        stmts_data = data[:stmts] || data['stmts']
        stmts = stmts_data.map { |stmt_h| Statement.from_h(stmt_h) }
        new(stmts)
      end
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

    def self.serialize_statement_seq(seq)
      seq.stmts.map { |s| serialize_statement(s) + "\n" }.join
    end

    def self.deserialize_statement_seq(s)
      stmts = s.each_line.filter_map do |raw|
        line = raw.strip
        next if line.empty? || line.start_with?('#')
        deserialize_statement(line)
      end
      StatementSeq.new(stmts)
    end
  end
end
