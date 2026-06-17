use std::path::Path;

use regex::Regex;
use serde::Deserialize;
use yaml_rust::{Yaml, YamlEmitter};
use yaml_rust::yaml::Hash;

use crate::*;

fn blockify_yaml(yaml: &str) -> String {
    let re = Regex::new(r#"(?m)^(\s*)(seq|semantic):\s*"(.*)"$"#).unwrap();
    let mut result = yaml.to_string();
    let mut offset: isize = 0;

    let caps: Vec<_> = re.captures_iter(yaml).collect();
    for cap in caps {
        let indent = cap.get(1).unwrap().as_str();
        let key = cap.get(2).unwrap().as_str();
        let body = cap.get(3).unwrap().as_str().replace("\\n", "\n");
        let body_indent = format!("{}  ", indent);

        let mut replacement = format!("{}{}: |\n", indent, key);
        for line in body.lines() {
            replacement.push_str(&body_indent);
            replacement.push_str(line);
            replacement.push('\n');
        }
        if body.ends_with('\n') {
            replacement.push('\n');
        }

        let cap_start = cap.get(0).unwrap().start() as isize + offset;
        let cap_end = cap.get(0).unwrap().end() as isize + offset;
        let old_len = (cap_end - cap_start) as usize;
        result.replace_range(cap_start as usize..cap_end as usize, &replacement);
        offset += replacement.len() as isize - old_len as isize;
    }

    result
}

fn arch_to_yaml(arch: &Arch) -> anyhow::Result<String> {
    let snippets: Vec<Yaml> = arch
        .snippets
        .iter()
        .map(|s| {
            let mut map = Hash::new();
            map.insert(Yaml::String("name".into()), Yaml::String(s.name.clone()));
            map.insert(Yaml::String("seq".into()), Yaml::String(s.seq.to_string()));
            Yaml::Hash(map)
        })
        .collect();

    let instructions: Vec<Yaml> = arch
        .instructions
        .iter()
        .map(|i| {
            let mut map = Hash::new();
            map.insert(Yaml::String("name".into()), Yaml::String(i.name.clone()));
            map.insert(Yaml::String("attributes".into()), Yaml::Array(i.attributes.iter().map(|a| Yaml::String(a.clone())).collect()));
            map.insert(
                Yaml::String("operand_sizes".into()),
                Yaml::Array(i.operand_sizes.iter().map(|&sz| Yaml::Integer(sz as i64)).collect()),
            );
            map.insert(
                Yaml::String("operand_names".into()),
                Yaml::Array(i.operand_names.iter().map(|n| Yaml::String(n.clone())).collect()),
            );
            {
                let mut enc_map = Hash::new();
                enc_map.insert(
                    Yaml::String("encoded_size".into()),
                    Yaml::Integer(i.encoding.encoded_size as i64),
                );
                enc_map.insert(
                    Yaml::String("const_encoding_part".into()),
                    Yaml::Integer(i.encoding.const_encoding_part as i64),
                );
                enc_map.insert(
                    Yaml::String("const_mask".into()),
                    Yaml::Integer(i.encoding.const_mask as i64),
                );
                enc_map.insert(
                    Yaml::String("decode".into()),
                    Yaml::Array(
                        i.encoding.decode.iter().map(|d| Yaml::String(d.clone())).collect(),
                    ),
                );
                enc_map.insert(Yaml::String("encode".into()), Yaml::String(i.encoding.encode.clone()));
                enc_map.insert(
                    Yaml::String("constraint_decode".into()),
                    Yaml::String(i.encoding.constraint_decode.clone()),
                );
                enc_map.insert(
                    Yaml::String("constraint_encode".into()),
                    Yaml::String(i.encoding.constraint_encode.clone()),
                );
                map.insert(Yaml::String("encoding".into()), Yaml::Hash(enc_map));
            }
            map.insert(
                Yaml::String("semantic".into()),
                Yaml::String(i.semantic.to_string()),
            );
            Yaml::Hash(map)
        })
        .collect();

    let register_files: Vec<Yaml> = arch
        .register_files
        .iter()
        .map(|rf| {
            let mut map = Hash::new();
            map.insert(Yaml::String("name".into()), Yaml::String(rf.name.clone()));
            map.insert(Yaml::String("attributes".into()), Yaml::Array(rf.attributes.iter().map(|a| Yaml::String(a.clone())).collect()));
            {
                let mut shape = Hash::new();
                shape.insert(
                    Yaml::String("lanes_base".into()),
                    Yaml::Integer(rf.reg_size.lanes_base as i64),
                );
                shape.insert(
                    Yaml::String("lanes_mult".into()),
                    match &rf.reg_size.lanes_mult {
                        Some(m) => Yaml::String(m.clone()),
                        None => Yaml::Null,
                    },
                );
                map.insert(Yaml::String("reg_size".into()), Yaml::Hash(shape));
            }
            map.insert(
                Yaml::String("regs".into()),
                Yaml::Array(
                    rf.regs
                        .iter()
                        .map(|r| {
                            let mut rm = Hash::new();
                            rm.insert(Yaml::String("name".into()), Yaml::String(r.name.clone()));
                            rm.insert(Yaml::String("attributes".into()), Yaml::Array(r.attributes.iter().map(|a| Yaml::String(a.clone())).collect()));
                            Yaml::Hash(rm)
                        })
                        .collect(),
                ),
            );
            Yaml::Hash(map)
        })
        .collect();

    let env_funcs: Vec<Yaml> = arch
        .environment_functions
        .iter()
        .map(|ef| {
            let mut map = Hash::new();
            map.insert(Yaml::String("name".into()), Yaml::String(ef.name.clone()));
            map.insert(
                Yaml::String("attributes".into()),
                Yaml::Array(ef.attributes.iter().map(|a| Yaml::String(a.clone())).collect()),
            );
            map.insert(
                Yaml::String("inputs".into()),
                Yaml::Array(ef.inputs.iter().map(|&sz| Yaml::Integer(sz as i64)).collect()),
            );
            map.insert(
                Yaml::String("outputs".into()),
                Yaml::Array(ef.outputs.iter().map(|&sz| Yaml::Integer(sz as i64)).collect()),
            );
            Yaml::Hash(map)
        })
        .collect();

    let operations: Vec<Yaml> = arch
        .operations
        .iter()
        .map(|op| {
            let mut map = Hash::new();
            map.insert(Yaml::String("name".into()), Yaml::String(op.name.clone()));
            map.insert(Yaml::String("attributes".into()), Yaml::Array(op.attributes.iter().map(|a| Yaml::String(a.clone())).collect()));
            map.insert(
                Yaml::String("inputs".into()),
                Yaml::Array(op.inputs.iter().map(|&sz| Yaml::Integer(sz as i64)).collect()),
            );
            map.insert(
                Yaml::String("outputs".into()),
                Yaml::Array(op.outputs.iter().map(|&sz| Yaml::Integer(sz as i64)).collect()),
            );
            if let Some(ref base) = op.semantic_base {
                map.insert(Yaml::String("semantic_base".into()), Yaml::String(base.clone()));
            } else {
                map.insert(Yaml::String("semantic_base".into()), Yaml::Null);
            }
            if let Some(ref func) = op.semantic_func {
                map.insert(Yaml::String("semantic_func".into()), Yaml::String(func.clone()));
            } else {
                map.insert(Yaml::String("semantic_func".into()), Yaml::Null);
            }
            map.insert(Yaml::String("semantic_func_128".into()), Yaml::Null);
            map.insert(Yaml::String("semantic_table".into()), Yaml::Null);
            Yaml::Hash(map)
        })
        .collect();

    let system_registers: Vec<Yaml> = arch
        .system_registers
        .iter()
        .map(|sr| {
            let mut map = Hash::new();
            map.insert(Yaml::String("name".into()), Yaml::String(sr.name.clone()));
            map.insert(Yaml::String("attributes".into()), Yaml::Array(sr.attributes.iter().map(|a| Yaml::String(a.clone())).collect()));
            map.insert(Yaml::String("size".into()), Yaml::Integer(sr.size as i64));
            map.insert(
                Yaml::String("fields".into()),
                Yaml::Array(
                    sr.fields
                        .iter()
                        .map(|f| {
                            let mut fm = Hash::new();
                            fm.insert(Yaml::String("name".into()), Yaml::String(f.name.clone()));
                            fm.insert(Yaml::String("attributes".into()), Yaml::Array(f.attributes.iter().map(|a| Yaml::String(a.clone())).collect()));
                            fm.insert(Yaml::String("lsb".into()), Yaml::Integer(f.lsb as i64));
                            fm.insert(Yaml::String("msb".into()), Yaml::Integer(f.msb as i64));
                            Yaml::Hash(fm)
                        })
                        .collect(),
                ),
            );
            Yaml::Hash(map)
        })
        .collect();

    let tables_int: Vec<Yaml> = arch
        .tables_int
        .iter()
        .map(|t| {
            let mut map = Hash::new();
            map.insert(Yaml::String("name".into()), Yaml::String(t.name.clone()));
            map.insert(Yaml::String("attributes".into()), Yaml::Array(t.attributes.iter().map(|a| Yaml::String(a.clone())).collect()));
            map.insert(
                Yaml::String("values".into()),
                Yaml::Array(t.values.iter().map(|&v| Yaml::Integer(v as i64)).collect()),
            );
            Yaml::Hash(map)
        })
        .collect();

    let mut root = Hash::new();
    root.insert(Yaml::String("name".into()), Yaml::String(arch.name.clone()));
    root.insert(
        Yaml::String("attributes".into()),
        Yaml::Array(arch.attributes.iter().map(|a| Yaml::String(a.clone())).collect()),
    );
    root.insert(Yaml::String("register_files".into()), Yaml::Array(register_files));
    root.insert(Yaml::String("system_registers".into()), Yaml::Array(system_registers));
    root.insert(Yaml::String("environment_functions".into()), Yaml::Array(env_funcs));
    root.insert(Yaml::String("tables_int".into()), Yaml::Array(tables_int));
    root.insert(Yaml::String("operations".into()), Yaml::Array(operations));
    root.insert(Yaml::String("snippets".into()), Yaml::Array(snippets));
    root.insert(Yaml::String("instructions".into()), Yaml::Array(instructions));

    let doc = Yaml::Hash(root);
    let mut out = String::new();
    let mut emitter = YamlEmitter::new(&mut out);
    emitter.dump(&doc)?;

    Ok(out)
}

#[derive(Debug, Clone, Deserialize)]
struct SerializableSnippet {
    name: String,
    seq: String,
}

#[derive(Debug, Clone, Deserialize)]
struct SerializableInstruction {
    name: String,
    attributes: Vec<String>,
    operand_sizes: Vec<usize>,
    operand_names: Vec<String>,
    encoding: InstructionEncoding,
    semantic: String,
}

#[derive(Debug, Clone, Deserialize)]
struct SerializableArch {
    name: String,
    attributes: Vec<String>,
    register_files: Vec<RegisterFile>,
    system_registers: Vec<SystemRegister>,
    environment_functions: Vec<EnvironmentFunction>,
    tables_int: Vec<TableInt>,
    operations: Vec<Operation>,
    snippets: Vec<SerializableSnippet>,
    instructions: Vec<SerializableInstruction>,
}

impl SerializableArch {
    fn into_arch(self) -> anyhow::Result<Arch> {
        let snippets = self
            .snippets
            .into_iter()
            .map(|s| {
                Ok(Snippet {
                    name: s.name,
                    seq: StatementSeq::parse(&s.seq)?,
                })
            })
            .collect::<anyhow::Result<Vec<_>>>()?;

        let instructions = self
            .instructions
            .into_iter()
            .map(|i| {
                Ok(Instruction {
                    name: i.name,
                    attributes: i.attributes,
                    operand_sizes: i.operand_sizes,
                    operand_names: i.operand_names,
                    encoding: i.encoding,
                    semantic: StatementSeq::parse(&i.semantic)?,
                })
            })
            .collect::<anyhow::Result<Vec<_>>>()?;

        Ok(Arch {
            name: self.name,
            attributes: self.attributes,
            register_files: self.register_files,
            system_registers: self.system_registers,
            environment_functions: self.environment_functions,
            tables_int: self.tables_int,
            operations: self.operations,
            snippets,
            instructions,
        })
    }
}

impl Arch {
    pub fn write_yaml(&self, path: impl AsRef<Path>) -> anyhow::Result<()> {
        let yaml = arch_to_yaml(self)?;
        let yaml = blockify_yaml(&yaml);
        std::fs::write(path, yaml)?;
        Ok(())
    }

    pub fn read_yaml(path: impl AsRef<Path>) -> anyhow::Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let serializable: SerializableArch = serde_yaml::from_str(&content)?;
        serializable.into_arch()
    }
}
