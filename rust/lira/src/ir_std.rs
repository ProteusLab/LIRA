use anyhow::Context;

use crate::*;

#[derive(Debug, Clone, Copy)]
pub enum StmtSpecificStd<'a> {
    Input {
        id: i32,
    },
    Output {
        id: i32,
        value: &'a str,
    },
    Read {
        rf: &'a RegisterFile,
        rsi: &'a str,
    },
    Write {
        rf: &'a RegisterFile,
        rsi: &'a str,
        value: &'a str,
    },
    Op {
        op: &'a Operation,
        args: &'a [String],
    },
    Env {
        env: &'a EnvironmentFunction,
        args: &'a [String],
    },
    CondEnv {
        env: &'a EnvironmentFunction,
        cond: &'a str,
        on_false: &'a [String],
        inputs: &'a [String],
    },
    Index,
    Const {
        value: i32,
    },
    DynConst {
        name: &'a str,
    },
    Gather {
        value: &'a str,
        index: &'a str,
        default: &'a str,
    },
    Fold {
        op: &'a Operation,
        args: &'a [String],
    },
    Scan {
        op: &'a Operation,
        args: &'a [String],
    },
    Alias {
        semantic: &'a Snippet,
        args: &'a [String],
    },
}

impl Statement {
    pub fn as_stmt<'a>(&'a self, idx: &'a ArchIndex<'a>) -> anyhow::Result<StmtSpecificStd<'a>> {
        self.as_stmt_(idx).with_context(|| self.to_string())
    }
    pub fn as_stmt_<'a>(&'a self, idx: &'a ArchIndex<'a>) -> anyhow::Result<StmtSpecificStd<'a>> {
        macro_rules! get {
            ($field:ident) => {
                idx.$field.get(self.specifier.as_str()).ok_or_else(|| {
                    anyhow::anyhow!("no {} {}", stringify!($field), self.specifier)
                })?
            };
        }
        Ok(match self.kind.as_str() {
            "index" => {
                anyhow::ensure!(self.inputs.is_empty());
                StmtSpecificStd::Index
            }

            "const" => {
                anyhow::ensure!(self.inputs.is_empty());
                let value = self.specifier.parse()?;
                StmtSpecificStd::Const { value }
            }
            "dyn_const" => {
                anyhow::ensure!(self.inputs.is_empty());
                let name = &self.specifier;
                StmtSpecificStd::DynConst { name }
            }

            "input" => {
                anyhow::ensure!(self.inputs.is_empty());
                let id = self.specifier.parse()?;
                StmtSpecificStd::Input { id }
            }
            "output" => {
                anyhow::ensure!(self.inputs.len() == 1);
                let id = self.specifier.parse()?;
                let value = &self.inputs[0];
                StmtSpecificStd::Output { id, value }
            }

            "read" => {
                anyhow::ensure!(self.inputs.len() == 1);
                let rf = get!(rf);
                let rsi = self.inputs[0].as_str();
                StmtSpecificStd::Read { rf, rsi }
            }
            "write" => {
                anyhow::ensure!(self.inputs.len() == 2);
                let rf = get!(rf);
                let rsi = &self.inputs[0];
                let value = &self.inputs[1];
                StmtSpecificStd::Write { rf, rsi, value }
            }

            "op" => {
                let op = get!(op);
                let args = &self.inputs[..];
                StmtSpecificStd::Op { op, args }
            }
            "env" => {
                let env = get!(env);
                let args = &self.inputs[..];
                StmtSpecificStd::Env { env, args }
            }
            "cond_env" => {
                let env = get!(env);
                anyhow::ensure!(self.inputs.len() == 1 + env.outputs.len() + env.inputs.len());
                anyhow::ensure!(self.outputs.len() == env.outputs.len());
                let cond = &self.inputs[0];
                let on_false = &self.inputs[1..1 + env.outputs.len()];
                let inputs = &self.inputs[1 + env.outputs.len()..];
                StmtSpecificStd::CondEnv {
                    env,
                    cond,
                    on_false,
                    inputs,
                }
            }
            "gather" => {
                anyhow::ensure!(self.inputs.len() == 3);
                let value = self.inputs[0].as_str();
                let index = self.inputs[1].as_str();
                let default = self.inputs[2].as_str();
                StmtSpecificStd::Gather {
                    value,
                    index,
                    default,
                }
            }
            "fold" => {
                let op = get!(op);
                let args = &self.inputs[..];
                StmtSpecificStd::Fold { op, args }
            }
            "scan" => {
                let op = get!(op);
                let args = &self.inputs[..];
                StmtSpecificStd::Scan { op, args }
            }
            "alias" => {
                let semantic = get!(snippet);
                let args = &self.inputs[..];
                StmtSpecificStd::Alias { semantic, args }
            }

            other => anyhow::bail!("unknown statement kind: {}", other),
        })
    }
}
