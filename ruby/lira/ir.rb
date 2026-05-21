module LIRA
  class Shape
    attr_reader :lanes_base, :lanes_mult
    def initialize(lanes_base, lanes_mult)
      @lanes_base = lanes_base
      @lanes_mult = lanes_mult
    end

    def ==(other)
      other.is_a?(Shape) && lanes_base == other.lanes_base && lanes_mult == other.lanes_mult
    end
  end

  class Statement
    attr_reader :shape, :outputs, :outputs_types, :kind, :specifier, :inputs
    def initialize(shape:, outputs:, outputs_types:, kind:, specifier:, inputs:)
      @shape = shape
      @outputs = outputs
      @outputs_types = outputs_types
      @kind = kind
      @specifier = specifier
      @inputs = inputs
    end

    def input(id, stmt_seq)
      target = @inputs[id]
      stmt_seq.stmts.each do |stmt|
        return stmt if stmt.outputs.include?(target)
      end
      raise "input #{target} not found"
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
  end

  class StatementSeq
    attr_reader :stmts
    def initialize(stmts)
      @stmts = stmts
    end

    def ==(other)
      other.is_a?(StatementSeq) && stmts == other.stmts
    end
  end
end
