use std::path::Path;

impl crate::Arch {
    pub fn write_yaml(&self, path: impl AsRef<Path>) -> anyhow::Result<()> {
        Ok(std::fs::write(path, expand(&serde_yaml::to_string(self)?))?)
    }

    pub fn read_yaml(path: impl AsRef<Path>) -> anyhow::Result<Self> {
        Ok(serde_yaml::from_str(&std::fs::read_to_string(path)?)?)
    }
}

// Make output easier to read
fn expand(yaml: &str) -> String {
    use std::fmt::Write;
    let mut result = String::new();
    for line in yaml.lines() {
        let l = line.trim_start();
        if let Some(start) = ["seq:", "semantic:"].iter().find(|s| l.starts_with(*s)) {
            let prefix = &line[..line.len() - l.len()];
            writeln!(result, "{prefix}{start} |").unwrap();
            for part in l[start.len() + 2..l.len() - 3].split("\\n") {
                writeln!(result, "{prefix}  {part}").unwrap();
            }
        } else {
            writeln!(result, "{line}").unwrap();
        }
    }
    result
}
