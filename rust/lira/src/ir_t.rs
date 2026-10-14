use std::ops::Deref;

use ahash::AHashMap;
use serde::{Deserialize, Serialize};

use crate::*;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum MaybeTemplate<T> {
    Template(String),
    Concrete(T),
}
impl<T: Clone> MaybeTemplate<T> {
    pub fn as_template(&self) -> Option<&String> {
        match self {
            Self::Template(t) => Some(t),
            Self::Concrete(_) => None,
        }
    }
    pub fn as_concrete(&self) -> Option<&T> {
        match self {
            Self::Template(_) => None,
            Self::Concrete(v) => Some(v),
        }
    }

    pub fn concretize(self, map: &AHashMap<String, T>) -> T {
        match self {
            Self::Template(t) => map[&t].clone(),
            Self::Concrete(v) => v,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StatementT {
    pub shape: MaybeTemplate<Shape>,
    pub outputs: Vec<String>,
    pub outputs_types: Vec<MaybeTemplate<usize>>,
    pub kind: String,
    pub specifier: MaybeTemplate<String>,
    pub inputs: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct StatementSeqT {
    stmts: Vec<StatementT>,
    stmts_index: AHashMap<String, usize>,
}

impl StatementT {
    pub fn input<'a>(&self, id: usize, ss: &'a StatementSeqT) -> anyhow::Result<&'a StatementT> {
        let err = || anyhow::anyhow!("id {id} out of range");
        let name = self.inputs.get(id).ok_or_else(err)?;
        let err = || anyhow::anyhow!("name {name} wasn't defined");
        ss.stmts_index
            .get(name)
            .map(|&n| &ss.stmts[n])
            .ok_or_else(err)
    }

    pub fn concretize(
        self,
        shapes: &AHashMap<String, Shape>,
        types: &AHashMap<String, usize>,
        strings: &AHashMap<String, String>,
    ) -> Statement {
        Statement {
            shape: self.shape.concretize(shapes),
            outputs: self.outputs,
            outputs_types: self
                .outputs_types
                .into_iter()
                .map(|o| o.concretize(types))
                .collect(),
            kind: self.kind,
            specifier: self.specifier.concretize(strings),
            inputs: self.inputs,
        }
    }

    pub fn from_stmt(stmt: Statement) -> Self {
        Self {
            shape: MaybeTemplate::Concrete(stmt.shape),
            outputs: stmt.outputs,
            outputs_types: stmt
                .outputs_types
                .into_iter()
                .map(MaybeTemplate::Concrete)
                .collect(),
            kind: stmt.kind,
            specifier: MaybeTemplate::Concrete(stmt.specifier),
            inputs: stmt.inputs,
        }
    }
}

impl StatementSeqT {
    pub fn try_push(&mut self, stmt: StatementT) -> anyhow::Result<()> {
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

    pub fn concretize(
        self,
        shapes: &AHashMap<String, Shape>,
        types: &AHashMap<String, usize>,
        strings: &AHashMap<String, String>,
    ) -> StatementSeq {
        let mut r = StatementSeqBuilder::default();
        for stmt in self.stmts {
            r.try_push(stmt.concretize(shapes, types, strings)).unwrap();
        }
        r.finish()
    }
}

impl Deref for StatementSeqT {
    type Target = [StatementT];

    fn deref(&self) -> &Self::Target {
        &self.stmts
    }
}

impl Serialize for StatementSeqT {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for StatementSeqT {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        StatementSeqT::parse(&s).map_err(serde::de::Error::custom)
    }
}
