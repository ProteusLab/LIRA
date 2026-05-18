use std::path::Path;

use anyhow::Context;
use serde_json::json;

use crate::*;

impl Arch {
    pub fn write_to_file(&self, folder_path: &Path) -> anyhow::Result<()> {
        if folder_path.exists() {
            std::fs::remove_dir_all(folder_path)?;
        }
        std::fs::create_dir_all(folder_path)
            .with_context(|| anyhow::anyhow!("failed to create dir to {folder_path:?}"))?;

        macro_rules! write_json {
            ($data:expr, $path:literal $(, $($arg:tt)*)?) => {
                let path = folder_path.join(format!($path $(, $($arg)*)?));
                let content = serde_json::to_string($data)?;
                std::fs::write(&path, content)?;
            };
        }

        let arch = json!({ "name": self.name, "attributes": self.attributes, });
        write_json!(&arch, "arch.json");

        write_json!(&self.register_files, "register_files.json");
        write_json!(&self.system_registers, "system_registers.json");
        write_json!(&self.environment_functions, "environment_functions.json");
        write_json!(&self.tables_int, "tables_int.json");

        let index = json!({
            "operations": self.operations.iter().map(|op| &op.name).collect::<Vec<_>>(),
            "snippets": self.snippets.iter().map(|s| &s.name).collect::<Vec<_>>(),
            "instructions": self.instructions.iter().map(|i| &i.name).collect::<Vec<_>>(),
        });
        write_json!(&index, "index.json");

        let ops_dir = folder_path.join("operations");
        std::fs::create_dir(&ops_dir)?;
        for op in &self.operations {
            let path = ops_dir.join(format!("{}.json", op.name));
            std::fs::write(&path, serde_json::to_string(op)?)?;
        }

        let snippets_dir = folder_path.join("snippets");
        std::fs::create_dir(&snippets_dir)?;
        for snippet in &self.snippets {
            let path = snippets_dir.join(format!("{}.lira", snippet.name));
            std::fs::write(&path, snippet.seq.to_string())?;
        }

        let instr_dir = folder_path.join("instructions");
        std::fs::create_dir(&instr_dir)?;
        for instr in &self.instructions {
            let json_path = instr_dir.join(format!("{}.json", instr.name));
            std::fs::write(&json_path, serde_json::to_string(&instr)?)?;
            let lira_path = instr_dir.join(format!("{}.lira", instr.name));
            std::fs::write(&lira_path, instr.semantic.to_string())?;
        }

        Ok(())
    }

    pub fn read_from_file(folder_path: &Path) -> anyhow::Result<Self> {
        macro_rules! read_json {
            ($path:literal $(, $($arg:tt)*)?) => {{
                let path = folder_path.join(format!($path $(, $($arg)*)?));
                let content = std::fs::read_to_string(&path)
                    .with_context(|| format!("failed to read {:?}", path))?;
                serde_json::from_str(&content)
                    .with_context(|| format!("invalid JSON in {:?}", path))?
            }};
        }

        let arch_info: serde_json::Value = read_json!("arch.json");
        let name = arch_info["name"].as_str().unwrap().to_string();
        let attributes: Vec<String> = serde_json::from_value(arch_info["attributes"].clone())?;

        let register_files = read_json!("register_files.json");
        let system_registers = read_json!("system_registers.json");
        let environment_functions = read_json!("environment_functions.json");
        let tables_int = read_json!("tables_int.json");

        let index: serde_json::Value = read_json!("index.json");
        let op_names: Vec<String> = serde_json::from_value(index["operations"].clone())?;
        let snippet_names: Vec<String> = serde_json::from_value(index["snippets"].clone())?;
        let instr_names: Vec<String> = serde_json::from_value(index["instructions"].clone())?;

        let mut operations = Vec::new();
        for op_name in &op_names {
            let op: Operation = read_json!("operations/{}.json", op_name);
            operations.push(op);
        }

        let mut snippets = Vec::new();
        for name in snippet_names {
            let lira_path = folder_path.join(format!("snippets/{}.lira", name));
            let content = std::fs::read_to_string(&lira_path)?;
            let seq = StatementSeq::parse(&content)?;
            snippets.push(Snippet { name, seq });
        }

        let mut instructions = Vec::new();
        for instr_name in &instr_names {
            let mut instr: Instruction = read_json!("instructions/{}.json", instr_name);
            let lira_path = folder_path.join(format!("instructions/{}.lira", instr_name));
            let lira_content = std::fs::read_to_string(&lira_path)?;
            instr.semantic = StatementSeq::parse(&lira_content)?;
            instructions.push(instr);
        }

        Ok(Self {
            name,
            attributes,
            register_files,
            system_registers,
            environment_functions,
            tables_int,
            operations,
            snippets,
            instructions,
        })
    }
}
