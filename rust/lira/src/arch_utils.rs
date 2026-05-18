use ahash::AHashMap;

use crate::*;

pub struct ArchIndex<'a> {
    pub rf: AHashMap<&'a str, &'a RegisterFile>,
    pub sr: AHashMap<&'a str, &'a SystemRegister>,
    pub env: AHashMap<&'a str, &'a EnvironmentFunction>,
    pub tables: AHashMap<&'a str, &'a TableInt>,
    pub op: AHashMap<&'a str, &'a Operation>,
    pub snippet: AHashMap<&'a str, &'a Snippet>,
    pub instr: AHashMap<&'a str, &'a Instruction>,
}

impl Arch {
    pub fn build_index(arch: &Arch) -> ArchIndex<'_> {
        macro_rules! collect {
            ($field:ident) => {
                arch.$field.iter().map(|v| (v.name.as_str(), v)).collect()
            };
        }
        ArchIndex {
            rf: collect!(register_files),
            sr: collect!(system_registers),
            env: collect!(environment_functions),
            tables: collect!(tables_int),
            op: collect!(operations),
            snippet: collect!(snippets),
            instr: collect!(instructions),
        }
    }
}
