use serde::{Deserialize, Serialize};

use crate::*;

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Snippet {
    pub name: String,
    pub seq: StatementSeq,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Operation {
    pub name: String,
    pub attributes: Vec<String>,
    pub inputs: Vec<usize>,
    pub outputs: Vec<usize>,
    pub semantic_base: Option<String>,
    pub semantic_func: Option<String>,
    pub semantic_func_128: Option<String>,
    pub semantic_table: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Register {
    pub name: String,
    #[serde(default)]
    pub attributes: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct RegisterFile {
    pub name: String,
    pub attributes: Vec<String>,
    pub reg_size: Shape,
    pub regs: Vec<Register>,
}

impl RegisterFile {
    pub fn reg_names(&self) -> Vec<&str> {
        self.regs.iter().map(|r| r.name.as_str()).collect()
    }

    pub fn regs_num(&self) -> usize {
        self.regs.len()
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct EnvironmentFunction {
    pub name: String,
    pub attributes: Vec<String>,
    pub inputs: Vec<usize>,
    pub outputs: Vec<usize>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct SystemRegisterField {
    pub name: String,
    pub attributes: Vec<String>,
    pub lsb: usize,
    pub msb: usize,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct SystemRegister {
    pub name: String,
    pub attributes: Vec<String>,
    pub size: usize,
    pub fields: Vec<SystemRegisterField>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct TableInt {
    pub name: String,
    pub attributes: Vec<String>,
    pub values: Vec<usize>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct InstructionEncoding {
    pub encoded_size: usize,
    pub const_encoding_part: usize,
    pub const_mask: usize,
    /// Names of snippets
    ///
    /// `[encoding_size -> operand_size]`
    pub decode: Vec<String>,
    /// Name of snippet
    ///
    /// `[operand_size] -> encoding_size`
    pub encode: String,
    /// Name of snippet
    ///
    /// `[encoding_size -> 1]`
    pub constraint_decode: String,
    /// Name of snippet
    ///
    /// `[operand_size] -> 1`
    pub constraint_encode: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Instruction {
    pub name: String,
    pub attributes: Vec<String>,
    pub operand_sizes: Vec<usize>,
    pub operand_names: Vec<String>,
    pub encoding: InstructionEncoding,
    #[serde(skip)]
    pub semantic: StatementSeq,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Arch {
    pub name: String,
    pub attributes: Vec<String>,
    pub register_files: Vec<RegisterFile>,
    pub system_registers: Vec<SystemRegister>,
    pub environment_functions: Vec<EnvironmentFunction>,
    pub tables_int: Vec<TableInt>,
    pub operations: Vec<Operation>,
    pub snippets: Vec<Snippet>,
    pub instructions: Vec<Instruction>,
}
