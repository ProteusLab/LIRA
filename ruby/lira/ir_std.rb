module LIRA
  class StmtInput
    attr_reader :id_
    def initialize(id_); @id_ = id_; end
  end

  class StmtOutput
    attr_reader :id_, :value
    def initialize(id_, value); @id_ = id_; @value = value; end
  end

  class StmtRead
    attr_reader :rf, :rsi
    def initialize(rf, rsi); @rf = rf; @rsi = rsi; end
  end

  class StmtWrite
    attr_reader :rf, :rsi, :value
    def initialize(rf, rsi, value); @rf = rf; @rsi = rsi; @value = value; end
  end

  class StmtOp
    attr_reader :op, :args
    def initialize(op, args); @op = op; @args = args; end
  end

  class StmtEnv
    attr_reader :env, :args
    def initialize(env, args); @env = env; @args = args; end
  end

  class CondEnv
    attr_reader :env, :cond, :on_false, :inputs
    def initialize(env, cond, on_false, inputs); @env = env; @cond = cond; @on_false = on_false; @inputs = inputs; end
  end

  class StmtIndex; end

  class StmtConst
    attr_reader :value
    def initialize(value); @value = value; end
  end

  class StmtDynConst
    attr_reader :name
    def initialize(name); @name = name; end
  end

  class StmtGather
    attr_reader :value, :index, :default
    def initialize(value, index, default); @value = value; @index = index; @default = default; end
  end

  class StmtFold
    attr_reader :op, :args
    def initialize(op, args); @op = op; @args = args; end
  end

  class StmtScan
    attr_reader :op, :args
    def initialize(op, args); @op = op; @args = args; end
  end

  class StmtAlias
    attr_reader :semantic, :args
    def initialize(semantic, args); @semantic = semantic; @args = args; end
  end
end
