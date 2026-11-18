use std::ops::Deref;

use ahash::AHashMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct Dimension {
    pub lanes_base: usize,
    pub lanes_mult: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(transparent)]
pub struct Shape {
    pub dimensions: Vec<Dimension>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Statement {
    pub shape: Shape,
    pub outputs: Vec<String>,
    pub outputs_types: Vec<usize>,
    pub kind: String,
    pub specifier: String,
    pub inputs: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct StatementSeq {
    stmts: Vec<Statement>,
    stmts_index: AHashMap<String, usize>,
}

impl Dimension {
    pub fn new(lanes_base: usize, lanes_mult: Option<String>) -> Self {
        Self {
            lanes_base,
            lanes_mult,
        }
    }
    pub fn new_dyn(base: usize, mult: impl ToString) -> Self {
        Self::new(base, Some(mult.to_string()))
    }
}

impl Shape {
    pub fn new(dimensions: impl IntoIterator<Item = Dimension>) -> Self {
        Self {
            dimensions: dimensions.into_iter().collect(),
        }
    }
    pub fn new_scalar() -> Self {
        Self::default()
    }
    pub fn is_scalar(&self) -> bool {
        self.dimensions.is_empty()
    }
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

impl Serialize for StatementSeq {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for StatementSeq {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        StatementSeq::parse(&s).map_err(serde::de::Error::custom)
    }
}
