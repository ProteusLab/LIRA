use std::ops::Deref;

use ahash::AHashMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct Shape {
    pub lanes_base: usize,
    pub lanes_mult: Option<String>,
}
#[cfg(feature = "lira_dateg")]
impl dateg::BaseValue for Shape {}

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
pub struct StatementSeq(pub Vec<Statement>);
#[derive(Debug, Clone, Default)]
pub struct StatementSeqBuilder {
    stmts: Vec<Statement>,
    stmts_index: AHashMap<String, usize>,
    tmp_prefix: String,
    tmp_counter: usize,
}

impl Shape {
    pub fn new(lanes_base: usize, lanes_mult: Option<String>) -> Self {
        Self {
            lanes_base,
            lanes_mult,
        }
    }
    pub fn new_scalar() -> Self {
        Self::new(1, None)
    }
    pub fn new_dyn(base: usize, mult: impl ToString) -> Self {
        Self::new(base, Some(mult.to_string()))
    }
    pub fn is_scalar(&self) -> bool {
        self.lanes_base == 1 && self.lanes_mult.is_none()
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

impl StatementSeqBuilder {
    /// Note: writing bad value can lead to error in [`Self::try_push`] and nothing more
    pub fn set_tmp_prefix(&mut self, prefix: impl ToString) {
        self.tmp_prefix = prefix.to_string();
    }
    pub fn update_tmp_prefix<'a, 's: 'a>(
        &'s mut self,
        base: &str,
        names_to_avoid: impl Iterator<Item = &'a String> + Clone,
    ) {
        let names_to_avoid = || {
            names_to_avoid
                .clone()
                .chain(self.stmts.iter().flat_map(|stmt| stmt.outputs.iter()))
        };
        for i in 0..names_to_avoid().count() + 1 {
            let prefix = format!("{base}{i}");
            if names_to_avoid().all(|name| !name.starts_with(&prefix)) {
                self.tmp_counter = 0;
                self.tmp_prefix = prefix;
                return;
            }
        }
        unreachable!("names_to_avoid len + 1 prefixes should've been enough")
    }
    pub fn gen_temp_name(&mut self) -> String {
        self.tmp_counter += 1;
        format!("{}{}", self.tmp_prefix, self.tmp_counter)
    }

    pub fn try_push_str(&mut self, s: &str) -> anyhow::Result<()> {
        self.try_push(Statement::parse(s)?)
    }
    pub fn try_push_gen_temp_names(&mut self, mut stmt: Statement) -> anyhow::Result<()> {
        assert!(stmt.outputs.is_empty());
        assert!(!stmt.outputs_types.is_empty());
        stmt.outputs = (0..stmt.outputs_types.len())
            .map(|_| self.gen_temp_name())
            .collect();
        self.try_push(stmt)
    }
    pub fn try_push(&mut self, stmt: Statement) -> anyhow::Result<()> {
        anyhow::ensure!(stmt.outputs.len() == stmt.outputs_types.len());
        for name in &stmt.outputs {
            anyhow::ensure!(
                !self.stmts_index.contains_key(name),
                "output name {name:?} already defined",
            );
            anyhow::ensure!(
                stmt.outputs.iter().filter(|&out| out == name).count() == 1,
                "duplicate output name {name:?} within statement",
            );
        }
        for name in &stmt.inputs {
            anyhow::ensure!(
                self.stmts_index.contains_key(name),
                "input name {name:?} wasn't defined",
            );
        }

        let idx = self.stmts.len();
        for name in &stmt.outputs {
            self.stmts_index.insert(name.clone(), idx);
        }
        self.stmts.push(stmt);
        Ok(())
    }

    pub fn finish(self) -> StatementSeq {
        StatementSeq(self.stmts)
    }
}

impl StatementSeq {
    pub fn iter_with_ext_inputs(&self) -> impl Iterator<Item = (&Statement, Vec<(&Shape, usize)>)> {
        struct Iter<'a> {
            s: &'a [Statement],
            index: AHashMap<&'a String, (&'a Shape, usize)>,
        }
        impl<'a> Iterator for Iter<'a> {
            type Item = (&'a Statement, Vec<(&'a Shape, usize)>);
            fn next(&mut self) -> Option<Self::Item> {
                let stmt = self.s.get(0)?;
                self.s = &self.s[1..];
                let inputs = stmt.inputs.iter().map(|i| self.index[i]).collect();
                for (name, ty) in stmt.outputs.iter().zip(stmt.outputs_types.iter().copied()) {
                    self.index.insert(name, (&stmt.shape, ty));
                }
                Some((stmt, inputs))
            }
        }
        Iter {
            s: self,
            index: Default::default(),
        }
    }
}

impl Deref for StatementSeqBuilder {
    type Target = [Statement];
    fn deref(&self) -> &Self::Target {
        &self.stmts
    }
}
impl Deref for StatementSeq {
    type Target = [Statement];
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}
