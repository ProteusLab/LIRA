# lira/ir_ops.rb
require_relative 'arch'

module Lira
  class TypeCheckError < StandardError; end

  module BaseOp
    NOT = :not;
    NEG = :neg
    ADD = :add;
    SUB = :sub;
    MUL = :mul
    AND = :and;
    ORR = :orr;
    XOR = :xor
    LSL = :lsl;
    LSR = :lsr;
    ASR = :asr
    EQ = :eq;
    NE = :ne
    SLT = :slt;
    SLE = :sle;
    SGT = :sgt;
    SGE = :sge
    ULT = :ult;
    ULE = :ule;
    UGT = :ugt;
    UGE = :uge
    DIV_U = :div_u;
    DIV_S = :div_s
    REM_U = :rem_u;
    REM_S = :rem_s
    ROR = :ror;
    ROL = :rol
    ADD_OVERFLOW = :add_overflow;
    SUB_OVERFLOW = :sub_overflow
    SELECT = :select
    EXTEND_SIGN = :extend_sign;
    EXTEND_ZERO = :extend_zero
    EXTRACT_LOW = :extract_low
    POPCNT = :popcnt;
    CTZ = :ctz;
    CLZ = :clz
    REVERSE = :reverse
  end

  module StdOperation
    def base_name
      self.class.name.split('::').last.downcase.to_sym
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
      raise TypeCheckError, 'input width must be positive' unless inputs[0] > 0
      raise TypeCheckError, 'output width must be positive' unless outputs[0] > 0
      raise TypeCheckError, 'input != output' unless inputs[0] == outputs[0]
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
      raise TypeCheckError, 'input[0] must be positive' unless inputs[0] > 0
      raise TypeCheckError, 'input[1] must be positive' unless inputs[1] > 0
      raise TypeCheckError, 'output must be positive' unless outputs[0] > 0
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

    def generate_name
      "#{base_name}_#{inputs[0]}"
    end

    def check_signature
      raise TypeCheckError, 'input[0] must be positive' unless inputs[0] > 0
      raise TypeCheckError, 'input[1] must be positive' unless inputs[1] > 0
      raise TypeCheckError, 'output must be positive' unless outputs[0] > 0
      raise TypeCheckError, 'input widths differ' unless inputs[0] == inputs[1]
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
      raise TypeCheckError, 'input[0] must be positive' unless inputs[0] > 0
      raise TypeCheckError, 'input[1] must be positive' unless inputs[1] > 0
      raise TypeCheckError, 'input[2] must be positive' unless inputs[2] > 0
      raise TypeCheckError, 'output must be positive' unless outputs[0] > 0
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
      raise TypeCheckError, 'input width must be positive' unless inputs[0] > 0
      raise TypeCheckError, 'output width must be positive' unless outputs[0] > 0
      raise TypeCheckError, 'input >= output' unless inputs[0] < outputs[0]
    end

    def generate_name
      "#{semantic_base}_#{inputs[0]}_to_#{outputs[0]}"
    end
  end

  class ExtractLowOp < Operation
    include StdOperation

    def initialize(in_bits, out_bits, name: nil)
      name ||= "extract_low_#{in_bits}_to_#{out_bits}"
      super(name, [], [in_bits], [out_bits],
            semantic_base: BaseOp::EXTRACT_LOW, semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, 'input width must be positive' unless inputs[0] > 0
      raise TypeCheckError, 'output width must be positive' unless outputs[0] > 0
      raise TypeCheckError, 'output > input' unless outputs[0] <= inputs[0]
    end

    def generate_name
      "extract_low_#{inputs[0]}_to_#{outputs[0]}"
    end
  end

  class Not < UnaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::NOT); end
  end

  class Neg < UnaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::NEG); end
  end

  class Add < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::ADD); end
  end

  class Sub < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::SUB); end
  end

  class Mul < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::MUL); end
  end

  class And < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::AND); end
  end

  class Orr < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::ORR); end
  end

  class Xor < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::XOR); end
  end

  class Lsl < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::LSL); end
  end

  class Lsr < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::LSR); end
  end

  class Asr < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::ASR); end
  end

  class Eq < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::EQ); end
  end

  class Ne < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::NE); end
  end

  class Slt < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::SLT); end
  end

  class Sle < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::SLE); end
  end

  class Sgt < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::SGT); end
  end

  class Sge < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::SGE); end
  end

  class Ult < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::ULT); end
  end

  class Ule < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::ULE); end
  end

  class Ugt < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::UGT); end
  end

  class Uge < CmpOp
    def initialize(bits); super(bits, semantic_base: BaseOp::UGE); end
  end

  class ExtendSign < ExtendOp
    def initialize(in_bits, out_bits); super(in_bits, out_bits, BaseOp::EXTEND_SIGN); end
  end

  class ExtendZero < ExtendOp
    def initialize(in_bits, out_bits); super(in_bits, out_bits, BaseOp::EXTEND_ZERO); end
  end

  class ExtractLow < ExtractLowOp
    def initialize(in_bits, out_bits); super(in_bits, out_bits); end
  end

  class Popcnt < UnaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::POPCNT); end
  end

  class Ctz < UnaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::CTZ); end
  end

  class Clz < UnaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::CLZ); end
  end

  class Reverse < UnaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::REVERSE); end
  end

  class RemU < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::REM_U); end
    def base_name; BaseOp::REM_U; end
  end

  class RemS < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::REM_S); end
    def base_name; BaseOp::REM_S; end
  end

  class Ror < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::ROR); end
  end

  class Rol < BinaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::ROL); end
  end

  class AddOverflow < CmpOp
    def initialize(bits); super(bits, out_bits: 1, semantic_base: BaseOp::ADD_OVERFLOW); end
  end

  class SubOverflow < CmpOp
    def initialize(bits); super(bits, out_bits: 1, semantic_base: BaseOp::SUB_OVERFLOW); end
  end

  class DivU < TernaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::DIV_U); end
    def base_name; BaseOp::DIV_U; end
  end

  class DivS < TernaryOp
    def initialize(bits); super(bits, semantic_base: BaseOp::DIV_S); end
    def base_name; BaseOp::DIV_S; end
  end

  class Select < Operation
    include StdOperation

    def initialize(bits)
      name = "select_#{bits}"
      super(name, [], [1, bits, bits], [bits],
            semantic_base: BaseOp::SELECT, semantic_func: nil, semantic_table: nil)
      check_signature
    end

    def check_signature
      raise TypeCheckError, 'true/false branches mismatch' unless inputs[1] == inputs[2] && inputs[1] == outputs[0]
    end
  end
end
