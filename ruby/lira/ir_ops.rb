# lira/ir_ops.rb
require_relative 'arch'

module Lira
  class TypeCheckError < StandardError; end

  module StdOperation
    def base_name
      self.class.name.split('::').last.downcase
    end

    def generate_name
      if outputs.size == 1
        "#{base_name}_#{outputs.first}"
      else
        "#{base_name}_#{outputs.join('_')}"
      end
    end
  end

  class UnaryOp < Operation
    include StdOperation

    def initialize(out_bits, name: nil, semantic_base: nil)
      name ||= "#{base_name}_#{out_bits}"
      semantic_base ||= base_name
      super(name, [], [out_bits], [out_bits],
            semantic_base: semantic_base, semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, "input width must be positive" unless inputs[0] > 0
      raise TypeCheckError, "output width must be positive" unless outputs[0] > 0
      raise TypeCheckError, "input != output" unless inputs[0] == outputs[0]
    end
  end

  class BinaryOp < Operation
    include StdOperation

    def initialize(bits, name: nil, semantic_base: nil)
      name ||= "#{base_name}_#{bits}"
      semantic_base ||= base_name
      super(name, [], [bits, bits], [bits],
            semantic_base: semantic_base, semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, "input[0] must be positive" unless inputs[0] > 0
      raise TypeCheckError, "input[1] must be positive" unless inputs[1] > 0
      raise TypeCheckError, "output must be positive" unless outputs[0] > 0
      unless inputs[0] == inputs[1] && inputs[0] == outputs[0]
        raise TypeCheckError, "mismatched widths: #{inputs} -> #{outputs[0]}"
      end
    end
  end

  class CmpOp < Operation
    include StdOperation

    def initialize(bits, out_bits = 1, name: nil, semantic_base: nil)
      name ||= "#{base_name}_#{bits}"
      semantic_base ||= base_name
      super(name, [], [bits, bits], [out_bits],
            semantic_base: semantic_base, semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, "input[0] must be positive" unless inputs[0] > 0
      raise TypeCheckError, "input[1] must be positive" unless inputs[1] > 0
      raise TypeCheckError, "output must be positive" unless outputs[0] > 0
      raise TypeCheckError, "input widths differ" unless inputs[0] == inputs[1]
    end
  end

  class TernaryOp < Operation
    include StdOperation

    def initialize(bits, name: nil, semantic_base: nil)
      name ||= "#{base_name}_#{bits}"
      semantic_base ||= base_name
      super(name, [], [bits, bits, bits], [bits],
            semantic_base: semantic_base, semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, "input[0] must be positive" unless inputs[0] > 0
      raise TypeCheckError, "input[1] must be positive" unless inputs[1] > 0
      raise TypeCheckError, "input[2] must be positive" unless inputs[2] > 0
      raise TypeCheckError, "output must be positive" unless outputs[0] > 0
      unless inputs[0] == inputs[1] && inputs[0] == inputs[2] && inputs[0] == outputs[0]
        raise TypeCheckError, "mismatched widths: #{inputs} -> #{outputs[0]}"
      end
    end
  end

  class ExtendOp < Operation
    include StdOperation

    def initialize(in_bits, out_bits, kind, name: nil)
      name ||= "#{kind}_#{in_bits}_to_#{out_bits}"
      super(name, [], [in_bits], [out_bits],
            semantic_base: kind, semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, "input width must be positive" unless inputs[0] > 0
      raise TypeCheckError, "output width must be positive" unless outputs[0] > 0
      raise TypeCheckError, "input >= output" unless inputs[0] < outputs[0]
    end
  end

  class ExtractLowOp < Operation
    include StdOperation

    def initialize(in_bits, out_bits, name: nil)
      name ||= "extract_low_#{in_bits}_to_#{out_bits}"
      super(name, [], [in_bits], [out_bits],
            semantic_base: 'extract_low', semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, "input width must be positive" unless inputs[0] > 0
      raise TypeCheckError, "output width must be positive" unless outputs[0] > 0
      raise TypeCheckError, "output > input" unless outputs[0] <= inputs[0]
    end
  end

  class Not < UnaryOp; def initialize(bits); super(bits, semantic_base: 'not'); end; end
  class Neg < UnaryOp; def initialize(bits); super(bits, semantic_base: 'neg'); end; end
  class Add < BinaryOp; def initialize(bits); super(bits, semantic_base: 'add'); end; end
  class Sub < BinaryOp; def initialize(bits); super(bits, semantic_base: 'sub'); end; end
  class Mul < BinaryOp; def initialize(bits); super(bits, semantic_base: 'mul'); end; end
  class And < BinaryOp; def initialize(bits); super(bits, semantic_base: 'and'); end; end
  class Orr < BinaryOp; def initialize(bits); super(bits, semantic_base: 'orr'); end; end
  class Xor < BinaryOp; def initialize(bits); super(bits, semantic_base: 'xor'); end; end
  class Lsl < BinaryOp; def initialize(bits); super(bits, semantic_base: 'lsl'); end; end
  class Lsr < BinaryOp; def initialize(bits); super(bits, semantic_base: 'lsr'); end; end
  class Asr < BinaryOp; def initialize(bits); super(bits, semantic_base: 'asr'); end; end
  class Eq < CmpOp; def initialize(bits); super(bits, semantic_base: 'eq'); end; end
  class Ne < CmpOp; def initialize(bits); super(bits, semantic_base: 'ne'); end; end
  class Slt < CmpOp; def initialize(bits); super(bits, semantic_base: 'slt'); end; end
  class Sle < CmpOp; def initialize(bits); super(bits, semantic_base: 'sle'); end; end
  class Sgt < CmpOp; def initialize(bits); super(bits, semantic_base: 'sgt'); end; end
  class Sge < CmpOp; def initialize(bits); super(bits, semantic_base: 'sge'); end; end
  class Ult < CmpOp; def initialize(bits); super(bits, semantic_base: 'ult'); end; end
  class Ule < CmpOp; def initialize(bits); super(bits, semantic_base: 'ule'); end; end
  class Ugt < CmpOp; def initialize(bits); super(bits, semantic_base: 'ugt'); end; end
  class Uge < CmpOp; def initialize(bits); super(bits, semantic_base: 'uge'); end; end
  class ExtendSign < ExtendOp; def initialize(in_bits, out_bits); super(in_bits, out_bits, 'extend_sign'); end; end
  class ExtendZero < ExtendOp; def initialize(in_bits, out_bits); super(in_bits, out_bits, 'extend_zero'); end; end
  class ExtractLow < ExtractLowOp; def initialize(in_bits, out_bits); super(in_bits, out_bits); end; end

  class Popcnt < UnaryOp
    def initialize(bits); super(bits, semantic_base: 'popcnt'); end
  end

  class Ctz < UnaryOp
    def initialize(bits); super(bits, semantic_base: 'ctz'); end
  end

  class Clz < UnaryOp
    def initialize(bits); super(bits, semantic_base: 'clz'); end
  end

  class Reverse < UnaryOp
    def initialize(bits); super(bits, semantic_base: 'reverse'); end
  end

  class RemU < BinaryOp
    def initialize(bits); super(bits, semantic_base: 'rem_u'); end
  end

  class RemS < BinaryOp
    def initialize(bits); super(bits, semantic_base: 'rem_s'); end
  end

  class Ror < BinaryOp
    def initialize(bits); super(bits, semantic_base: 'ror'); end
  end

  class Rol < BinaryOp
    def initialize(bits); super(bits, semantic_base: 'rol'); end
  end

  class AddOverflow < CmpOp
    def initialize(bits); super(bits, out_bits: 1, semantic_base: 'add_overflow'); end
  end

  class SubOverflow < CmpOp
    def initialize(bits); super(bits, out_bits: 1, semantic_base: 'sub_overflow'); end
  end

  class DivU < TernaryOp
    def initialize(bits); super(bits, semantic_base: 'div_u'); end
  end

  class DivS < TernaryOp
    def initialize(bits); super(bits, semantic_base: 'div_s'); end
  end

  class Select < Operation
    include StdOperation
    def initialize(bits)
      name = "select_#{bits}"
      super(name, [], [1, bits, bits], [bits],
            semantic_base: 'select', semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, "true/false branches mismatch" unless inputs[1] == inputs[2] && inputs[1] == outputs[0]
    end
  end
end
