use ahash::AHashMap;

use crate::*;

impl Arch {
    pub fn build_index<T: Named>(field: &Vec<T>) -> AHashMap<&str, &T> {
        field.iter().map(|f| (f.name(), f)).collect()
    }
    pub fn build_index_all(&self) -> ArchIndex<'_> {
        ArchIndex {
            rf: Self::build_index(&self.register_files),
            sr: Self::build_index(&self.system_registers),
            env: Self::build_index(&self.environment_functions),
            tables: Self::build_index(&self.tables_int),
            op: Self::build_index(&self.operations),
            snippet: Self::build_index(&self.snippets),
            instr: Self::build_index(&self.instructions),
        }
    }

    pub fn iter_stmt_seq(&self) -> impl Iterator<Item = &StatementSeq> {
        Self::iter_stmt_seq_part(&self.instructions, &self.snippets)
    }
    pub fn iter_stmt_seq_part<'a>(
        is: &'a Vec<Instruction>,
        ss: &'a Vec<Snippet>,
    ) -> impl Iterator<Item = &'a StatementSeq> {
        [].into_iter()
            .chain(is.iter().map(|i| &i.semantic))
            .chain(ss.iter().map(|s| &s.seq))
    }
    pub fn iter_stmt_seq_mut(&mut self) -> impl Iterator<Item = (&String, &mut StatementSeq)> {
        Self::iter_stmt_seq_mut_part(&mut self.instructions, &mut self.snippets)
    }
    pub fn iter_stmt_seq_mut_part<'a>(
        is: &'a mut Vec<Instruction>,
        ss: &'a mut Vec<Snippet>,
    ) -> impl Iterator<Item = (&'a String, &'a mut StatementSeq)> {
        [].into_iter()
            .chain(is.iter_mut().map(|i| (&i.name, &mut i.semantic)))
            .chain(ss.iter_mut().map(|s| (&s.name, &mut s.seq)))
    }
}

pub struct ArchIndex<'a> {
    pub rf: AHashMap<&'a str, &'a RegisterFile>,
    pub sr: AHashMap<&'a str, &'a SystemRegister>,
    pub env: AHashMap<&'a str, &'a EnvironmentFunction>,
    pub tables: AHashMap<&'a str, &'a TableInt>,
    pub op: AHashMap<&'a str, &'a Operation>,
    pub snippet: AHashMap<&'a str, &'a Snippet>,
    pub instr: AHashMap<&'a str, &'a Instruction>,
}
