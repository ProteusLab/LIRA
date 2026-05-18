use std::ops::Deref;

use ahash::AHashMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Shape {
    pub lanes_base: usize,
    pub lanes_mult: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Statement {
    pub shape: Shape,
    pub outputs: Vec<String>,
    pub outputs_types: Vec<usize>,
    pub kind: String,
    pub specifier: String,
    pub inputs: Vec<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct StatementSeq {
    stmts: Vec<Statement>,
    stmts_index: AHashMap<String, usize>,
}

impl Statement {
    pub fn input<'a>(&self, id: usize, ss: &'a StatementSeq) -> anyhow::Result<&'a Statement> {
        let err = || anyhow::anyhow!("id {id} out of range");
        let name = self.inputs.get(id).ok_or_else(err)?;
        let err = || anyhow::anyhow!("name {name} wasn't defined");
        ss.stmts_index
            .get(name)
            .map(|&n| &ss.stmts[n])
            .ok_or_else(err)
    }
}

impl StatementSeq {
    pub fn try_push(&mut self, stmt: Statement) -> anyhow::Result<()> {
        assert_eq!(stmt.outputs.len(), stmt.outputs_types.len());
        for name in &stmt.outputs {
            anyhow::ensure!(!self.stmts_index.contains_key(name));
            anyhow::ensure!(stmt.outputs.iter().filter(|&out| out == name).count() == 1);
        }
        for name in &stmt.inputs {
            anyhow::ensure!(self.stmts_index.contains_key(name));
        }

        let idx = self.stmts.len();
        self.stmts.push(stmt);
        for name in &self.stmts[idx].outputs {
            self.stmts_index.insert(name.clone(), idx);
        }
        Ok(())
    }
}

impl Deref for StatementSeq {
    type Target = [Statement];

    fn deref(&self) -> &Self::Target {
        &self.stmts
    }
}
