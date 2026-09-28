use anyhow::Context;

use crate::{ir_ops::BASE_OP_SIGNATURE, *};

#[derive(Debug, Clone, Copy)]
pub enum StmtSpecificStd<'a> {
    Input(Input),
    Output(Output<'a>),
    Const(Const),
    DynConst(DynConst<'a>),
    SnippetCall(SnippetCall<'a>),
    PcRead(PcRead),
    CondPcWrite(CondPcWrite<'a>),
    CondSysRegRead(CondSysRegRead<'a>),
    CondSysRegWrite(CondSysRegWrite<'a>),
    OpG(OpG<'a>),
    Op(Op<'a>),
    FOp(FOp<'a>),
    Env(Env<'a>),
    CondEnv(CondEnv<'a>),
    Read(Read<'a>),
    CondRead(CondRead<'a>),
    Write(Write<'a>),
    CondWrite(CondWrite<'a>),
    Broadcast(Broadcast<'a>),
    Index(Index),
    ExtractFirst(ExtractFirst<'a>),
    ExtendZero(ExtendZero<'a>),
    ExtendOnes(ExtendOnes<'a>),
    Gather(Gather<'a>),
    CVI(CVI<'a>),
    Fold(Fold<'a>),
    Scan(Scan<'a>),
}

#[derive(Debug, Clone, Copy)]
pub struct Input {
    pub id: usize,
}
#[derive(Debug, Clone, Copy)]
pub struct Output<'a> {
    pub id: usize,
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct Const {
    pub value: i128,
}
#[derive(Debug, Clone, Copy)]
pub struct DynConst<'a> {
    pub name: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct SnippetCall<'a> {
    pub snippet: &'a Snippet,
    pub args: &'a [String],
}
#[derive(Debug, Clone, Copy)]
pub struct PcRead {}
#[derive(Debug, Clone, Copy)]
pub struct CondPcWrite<'a> {
    pub cond: &'a str,
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct CondSysRegRead<'a> {
    pub sys_reg: &'a SystemRegister,
    pub field_id: Option<usize>,
    pub cond: &'a str,
    pub on_false: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct CondSysRegWrite<'a> {
    pub sys_reg: &'a SystemRegister,
    pub field_id: Option<usize>,
    pub cond: &'a str,
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct OpG<'a> {
    pub op: &'a str,
    pub args: &'a [String],
}
#[derive(Debug, Clone, Copy)]
pub struct Op<'a> {
    pub op: &'a Operation,
    pub args: &'a [String],
}
#[derive(Debug, Clone, Copy)]
pub struct FOp<'a> {
    pub fop: &'a str,
    pub args: &'a [String],
}
#[derive(Debug, Clone, Copy)]
pub struct Env<'a> {
    pub env: &'a EnvironmentFunction,
    pub args: &'a [String],
}
#[derive(Debug, Clone, Copy)]
pub struct CondEnv<'a> {
    pub env: &'a EnvironmentFunction,
    pub cond: &'a str,
    pub on_false: &'a [String],
    pub inputs: &'a [String],
}
#[derive(Debug, Clone, Copy)]
pub struct Read<'a> {
    pub rf: &'a RegisterFile,
    pub rsi: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct CondRead<'a> {
    pub rf: &'a RegisterFile,
    pub cond: &'a str,
    pub on_false: &'a str,
    pub rsi: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct Write<'a> {
    pub rf: &'a RegisterFile,
    pub rsi: &'a str,
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct CondWrite<'a> {
    pub rf: &'a RegisterFile,
    pub cond: &'a str,
    pub rsi: &'a str,
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct Broadcast<'a> {
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct Index {}
#[derive(Debug, Clone, Copy)]
pub struct ExtractFirst<'a> {
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct ExtendZero<'a> {
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct ExtendOnes<'a> {
    pub value: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct Gather<'a> {
    pub value: &'a str,
    pub index: &'a str,
    pub on_false: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct CVI<'a> {
    pub base: &'a str,
    pub cond: &'a str,
    pub value: &'a str,
    pub index: &'a str,
}
#[derive(Debug, Clone, Copy)]
pub struct Fold<'a> {
    pub op: &'a Operation,
    pub inputs_scalar: &'a [String],
    pub inputs_vector: &'a [String],
}
#[derive(Debug, Clone, Copy)]
pub struct Scan<'a> {
    pub op: &'a Operation,
    pub inputs_scalar: &'a [String],
    pub inputs_vector: &'a [String],
}

impl Statement {
    pub fn as_stmt_specific<'a>(
        &'a self,
        index: &'a ArchIndex<'a>,
    ) -> anyhow::Result<StmtSpecificStd<'a>> {
        self.as_stmt_specific_(index)
            .with_context(|| self.to_string())
    }
    fn as_stmt_specific_<'a>(
        &'a self,
        idx: &'a ArchIndex<'a>,
    ) -> anyhow::Result<StmtSpecificStd<'a>> {
        macro_rules! get {
            ($field:ident) => {{
                let err = || anyhow::anyhow!("no {} {}", stringify!($field), self.specifier);
                *idx.$field.get(self.specifier.as_str()).ok_or_else(err)?
            }};
        }
        Ok(match self.kind.as_str() {
            "input" => {
                anyhow::ensure!(self.inputs.len() == 0);
                anyhow::ensure!(self.outputs.len() == 1);
                let id = self.specifier.parse()?;
                StmtSpecificStd::Input(Input { id })
            }
            "output" => {
                anyhow::ensure!(self.inputs.len() == 1);
                anyhow::ensure!(self.outputs.len() == 0);
                let id = self.specifier.parse()?;
                let value = &self.inputs[0];
                StmtSpecificStd::Output(Output { id, value })
            }
            "const" => {
                anyhow::ensure!(self.inputs.len() == 0);
                anyhow::ensure!(self.outputs.len() == 1);
                let value = self.specifier.parse()?;
                StmtSpecificStd::Const(Const { value })
            }
            "dyn_const" => {
                anyhow::ensure!(self.inputs.len() == 0);
                anyhow::ensure!(self.outputs.len() == 1);
                let name = &self.specifier;
                StmtSpecificStd::DynConst(DynConst { name })
            }
            "snippet" => {
                let snippet = get!(snippet);
                let args = &self.inputs;
                StmtSpecificStd::SnippetCall(SnippetCall { snippet, args })
            }
            "pc.read" => {
                anyhow::ensure!(self.inputs.len() == 0);
                anyhow::ensure!(self.outputs.len() == 1);
                anyhow::ensure!(self.specifier == "_");
                StmtSpecificStd::PcRead(PcRead {})
            }
            "cond.pc.write" => {
                anyhow::ensure!(self.inputs.len() == 2);
                anyhow::ensure!(self.outputs.len() == 0);
                anyhow::ensure!(self.specifier == "_");
                let cond = &self.inputs[0];
                let value = &self.inputs[1];
                StmtSpecificStd::CondPcWrite(CondPcWrite { cond, value })
            }
            "cond.sys_reg.read" | "cond.sys_reg.write" => {
                anyhow::ensure!(self.specifier.chars().filter(|c| *c == '.').count() <= 1);
                let (sys_reg, field) = if let Some((reg, field)) = self.specifier.split_once('.') {
                    (reg, Some(field))
                } else {
                    (self.specifier.as_str(), None)
                };
                let err = || anyhow::anyhow!("no {} {}", stringify!(sr), self.specifier);
                let sys_reg = *idx.sr.get(sys_reg).ok_or_else(err)?;
                let field_id = field
                    .map(|field| {
                        sys_reg
                            .fields
                            .iter()
                            .position(|f| f.name == field)
                            .ok_or_else(|| anyhow::anyhow!("no field"))
                    })
                    .transpose()?;
                if self.kind == "cond.sys_reg.read" {
                    anyhow::ensure!(self.inputs.len() == 2);
                    anyhow::ensure!(self.outputs.len() == 1);
                    let cond = self.inputs[0].as_str();
                    let on_false = self.inputs[1].as_str();
                    StmtSpecificStd::CondSysRegRead(CondSysRegRead {
                        sys_reg,
                        field_id,
                        cond,
                        on_false,
                    })
                } else if self.kind == "cond.sys_reg.write" {
                    anyhow::ensure!(self.inputs.len() == 2);
                    anyhow::ensure!(self.outputs.len() == 0);
                    let cond = &self.inputs[0];
                    let value = &self.inputs[1];
                    StmtSpecificStd::CondSysRegWrite(CondSysRegWrite {
                        sys_reg,
                        field_id,
                        cond,
                        value,
                    })
                } else {
                    unreachable!()
                }
            }
            "op.g" => {
                let op = self.specifier.as_str();
                let err = || anyhow::anyhow!("no signature for {op}");
                let _parse = BASE_OP_SIGNATURE.get(op).ok_or_else(err)?;
                let args = &self.inputs;
                StmtSpecificStd::OpG(OpG { op, args })
            }
            "op" => {
                let op = get!(op);
                anyhow::ensure!(op.outputs == self.outputs_types);
                let args = &self.inputs;
                StmtSpecificStd::Op(Op { op, args })
            }
            "fop" => {
                let fop = &self.specifier;
                let args = &self.inputs;
                StmtSpecificStd::FOp(FOp { fop, args })
            }
            "env" => {
                let env = get!(env);
                anyhow::ensure!(env.outputs == self.outputs_types);
                let args = &self.inputs[..];
                StmtSpecificStd::Env(Env { env, args })
            }
            "cond_env" => {
                let env = get!(env);
                anyhow::ensure!(self.inputs.len() == 1 + env.outputs.len() + env.inputs.len());
                anyhow::ensure!(env.outputs == self.outputs_types);
                let cond = &self.inputs[0];
                let on_false = &self.inputs[1..1 + env.outputs.len()];
                let inputs = &self.inputs[1 + env.outputs.len()..];
                StmtSpecificStd::CondEnv(CondEnv {
                    env,
                    cond,
                    on_false,
                    inputs,
                })
            }
            "read" => {
                anyhow::ensure!(self.inputs.len() == 1);
                anyhow::ensure!(self.outputs.len() == 1);
                let rf = get!(rf);
                let rsi = self.inputs[0].as_str();
                StmtSpecificStd::Read(Read { rf, rsi })
            }
            "cond.read" => {
                anyhow::ensure!(self.inputs.len() == 3);
                anyhow::ensure!(self.outputs.len() == 1);
                let rf = get!(rf);
                let cond = self.inputs[0].as_str();
                let on_false = self.inputs[0].as_str();
                let rsi = self.inputs[0].as_str();
                StmtSpecificStd::CondRead(CondRead {
                    rf,
                    cond,
                    on_false,
                    rsi,
                })
            }
            "write" => {
                anyhow::ensure!(self.inputs.len() == 2);
                anyhow::ensure!(self.outputs.len() == 0);
                let rf = get!(rf);
                let rsi = &self.inputs[0];
                let value = &self.inputs[1];
                StmtSpecificStd::Write(Write { rf, rsi, value })
            }
            "cond.write" => {
                anyhow::ensure!(self.inputs.len() == 3);
                anyhow::ensure!(self.outputs.len() == 0);
                let rf = get!(rf);
                let cond = &self.inputs[0];
                let rsi = &self.inputs[1];
                let value = &self.inputs[2];
                StmtSpecificStd::CondWrite(CondWrite {
                    rf,
                    cond,
                    rsi,
                    value,
                })
            }
            "broadcast" => {
                anyhow::ensure!(self.inputs.len() == 1);
                anyhow::ensure!(self.outputs.len() == 1);
                let value = &self.inputs[0];
                StmtSpecificStd::Broadcast(Broadcast { value })
            }
            "index" => {
                anyhow::ensure!(self.inputs.len() == 0);
                anyhow::ensure!(self.outputs.len() == 1);
                StmtSpecificStd::Index(Index {})
            }
            "extract_first" => {
                anyhow::ensure!(self.inputs.len() == 1);
                anyhow::ensure!(self.outputs.len() == 1);
                let value = &self.inputs[0];
                StmtSpecificStd::ExtractFirst(ExtractFirst { value })
            }
            "extend_zero" => {
                anyhow::ensure!(self.inputs.len() == 1);
                anyhow::ensure!(self.outputs.len() == 1);
                let value = &self.inputs[0];
                StmtSpecificStd::ExtendZero(ExtendZero { value })
            }
            "extend_ones" => {
                anyhow::ensure!(self.inputs.len() == 1);
                anyhow::ensure!(self.outputs.len() == 1);
                let value = &self.inputs[0];
                StmtSpecificStd::ExtendOnes(ExtendOnes { value })
            }
            "gather" => {
                anyhow::ensure!(self.inputs.len() == 3);
                anyhow::ensure!(self.outputs.len() == 1);
                let value = &self.inputs[0];
                let index = &self.inputs[0];
                let on_false = &self.inputs[0];
                StmtSpecificStd::Gather(Gather {
                    value,
                    index,
                    on_false,
                })
            }
            "cvi" => {
                anyhow::ensure!(self.inputs.len() == 4);
                anyhow::ensure!(self.outputs.len() == 1);
                let base = &self.inputs[0];
                let cond = &self.inputs[0];
                let value = &self.inputs[0];
                let index = &self.inputs[0];
                StmtSpecificStd::CVI(CVI {
                    base,
                    cond,
                    value,
                    index,
                })
            }

            // Require inputs shapes knowledge
            "fold" => {
                let _op = get!(op);
                let _args = &self.inputs[..];
                todo!()
            }
            "scan" => {
                let _op = get!(op);
                let _args = &self.inputs[..];
                todo!()
            }

            other => anyhow::bail!("unknown statement kind: {}", other),
        })
    }
}
