use crate::*;

pub mod base_op {
    pub const NOT: &str = "not";
    pub const NEG: &str = "neg";
    pub const ADD: &str = "add";
    pub const SUB: &str = "sub";
    pub const MUL: &str = "mul";
    pub const AND: &str = "and";
    pub const ORR: &str = "orr";
    pub const XOR: &str = "xor";
    pub const LSL: &str = "lsl";
    pub const LSR: &str = "lsr";
    pub const ASR: &str = "asr";
    pub const EQ: &str = "eq";
    pub const NE: &str = "ne";
    pub const SLT: &str = "slt";
    pub const SLE: &str = "sle";
    pub const SGT: &str = "sgt";
    pub const SGE: &str = "sge";
    pub const ULT: &str = "ult";
    pub const ULE: &str = "ule";
    pub const UGT: &str = "ugt";
    pub const UGE: &str = "uge";
    pub const EXTEND_SIGN: &str = "extend_sign";
    pub const EXTEND_ZERO: &str = "extend_zero";
    pub const EXTRACT_LOW: &str = "extract_low";
    pub const SELECT: &str = "select";
    pub const POPCNT: &str = "popcnt";
    pub const CTZ: &str = "ctz";
    pub const CLZ: &str = "clz";
    pub const REVERSE: &str = "reverse";
    pub const DIV_U: &str = "div_u";
    pub const DIV_S: &str = "div_s";
    pub const REM_U: &str = "rem_u";
    pub const REM_S: &str = "rem_s";
    pub const ROR: &str = "ror";
    pub const ROL: &str = "rol";
    pub const ADD_OVERFLOW: &str = "add_overflow";
    pub const SUB_OVERFLOW: &str = "sub_overflow";
}

fn unary_op(_name: &str, base: &str, bits: usize) -> Operation {
    Operation {
        name: format!("{}_{}", base, bits),
        inputs: vec![bits],
        outputs: vec![bits],
        semantic_base: Some(base.to_string()),
        ..Default::default()
    }
}

fn binary_op(_name: &str, base: &str, bits: usize) -> Operation {
    Operation {
        name: format!("{}_{}", base, bits),
        inputs: vec![bits, bits],
        outputs: vec![bits],
        semantic_base: Some(base.to_string()),
        ..Default::default()
    }
}

fn cmp_op(_name: &str, base: &str, bits: usize) -> Operation {
    Operation {
        name: format!("{}_{}", base, bits),
        inputs: vec![bits, bits],
        outputs: vec![1],
        semantic_base: Some(base.to_string()),
        ..Default::default()
    }
}

pub fn extract_low_op(in_bits: usize, out_bits: usize) -> Operation {
    Operation {
        name: format!("extract_low_{}_to_{}", in_bits, out_bits),
        inputs: vec![in_bits],
        outputs: vec![out_bits],
        semantic_base: Some(base_op::EXTRACT_LOW.to_string()),
        ..Default::default()
    }
}

pub fn not_op(bits: usize) -> Operation {
    unary_op("not", base_op::NOT, bits)
}
pub fn neg_op(bits: usize) -> Operation {
    unary_op("neg", base_op::NEG, bits)
}
pub fn add_op(bits: usize) -> Operation {
    binary_op("add", base_op::ADD, bits)
}
pub fn sub_op(bits: usize) -> Operation {
    binary_op("sub", base_op::SUB, bits)
}
pub fn mul_op(bits: usize) -> Operation {
    binary_op("mul", base_op::MUL, bits)
}
pub fn and_op(bits: usize) -> Operation {
    binary_op("and", base_op::AND, bits)
}
pub fn orr_op(bits: usize) -> Operation {
    binary_op("orr", base_op::ORR, bits)
}
pub fn xor_op(bits: usize) -> Operation {
    binary_op("xor", base_op::XOR, bits)
}
pub fn lsl_op(bits: usize) -> Operation {
    binary_op("lsl", base_op::LSL, bits)
}
pub fn lsr_op(bits: usize) -> Operation {
    binary_op("lsr", base_op::LSR, bits)
}
pub fn asr_op(bits: usize) -> Operation {
    binary_op("asr", base_op::ASR, bits)
}
pub fn eq_op(bits: usize) -> Operation {
    cmp_op("eq", base_op::EQ, bits)
}
pub fn ne_op(bits: usize) -> Operation {
    cmp_op("ne", base_op::NE, bits)
}
pub fn slt_op(bits: usize) -> Operation {
    cmp_op("slt", base_op::SLT, bits)
}
pub fn sle_op(bits: usize) -> Operation {
    cmp_op("sle", base_op::SLE, bits)
}
pub fn sgt_op(bits: usize) -> Operation {
    cmp_op("sgt", base_op::SGT, bits)
}
pub fn sge_op(bits: usize) -> Operation {
    cmp_op("sge", base_op::SGE, bits)
}
pub fn ult_op(bits: usize) -> Operation {
    cmp_op("ult", base_op::ULT, bits)
}
pub fn ule_op(bits: usize) -> Operation {
    cmp_op("ule", base_op::ULE, bits)
}
pub fn ugt_op(bits: usize) -> Operation {
    cmp_op("ugt", base_op::UGT, bits)
}
pub fn uge_op(bits: usize) -> Operation {
    cmp_op("uge", base_op::UGE, bits)
}

pub fn extend_sign_op(in_bits: usize, out_bits: usize) -> Operation {
    Operation {
        name: format!("extend_sign_{}_to_{}", in_bits, out_bits),
        inputs: vec![in_bits],
        outputs: vec![out_bits],
        semantic_base: Some(base_op::EXTEND_SIGN.to_string()),
        ..Default::default()
    }
}

pub fn extend_zero_op(in_bits: usize, out_bits: usize) -> Operation {
    Operation {
        name: format!("extend_zero_{}_to_{}", in_bits, out_bits),
        inputs: vec![in_bits],
        outputs: vec![out_bits],
        semantic_base: Some(base_op::EXTEND_ZERO.to_string()),
        ..Default::default()
    }
}

pub fn select_op(bits: usize) -> Operation {
    Operation {
        name: format!("select_{}", bits),
        inputs: vec![1, bits, bits],
        outputs: vec![bits],
        semantic_base: Some(base_op::SELECT.to_string()),
        ..Default::default()
    }
}
