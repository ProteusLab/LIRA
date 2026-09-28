use std::fmt::Display;
use std::sync::LazyLock;

use regex::Regex;

use crate::Shape;
use crate::ir_t::*;

impl<T: Display> Display for MaybeTemplate<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Template(t) => f.write_fmt(format_args!("?{t}")),
            Self::Concrete(v) => f.write_fmt(format_args!("{v}")),
        }
    }
}

impl MaybeTemplate<Shape> {
    fn parse(s: &str) -> anyhow::Result<Self> {
        match s.chars().next().ok_or_else(|| anyhow::anyhow!("empty"))? {
            '?' => Ok(MaybeTemplate::Template(s[1..].to_string())),
            _ => Ok(MaybeTemplate::Concrete(Shape::parse(s)?)),
        }
    }
}
impl MaybeTemplate<String> {
    fn parse(s: &str) -> anyhow::Result<Self> {
        match s.chars().next().ok_or_else(|| anyhow::anyhow!("empty"))? {
            '?' => Ok(MaybeTemplate::Template(s[1..].to_string())),
            _ => Ok(MaybeTemplate::Concrete(s.to_string())),
        }
    }
}
impl MaybeTemplate<usize> {
    fn parse(s: &str) -> anyhow::Result<Self> {
        match s.chars().next().ok_or_else(|| anyhow::anyhow!("empty"))? {
            '?' => Ok(MaybeTemplate::Template(s[1..].to_string())),
            _ => Ok(MaybeTemplate::Concrete(s.parse()?)),
        }
    }
}

impl std::fmt::Display for StatementT {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.shape)?;
        for (typ, name) in self.outputs_types.iter().zip(&self.outputs) {
            write!(f, " {} {}", typ, name)?;
        }
        write!(f, " = {} {}", self.kind, self.specifier)?;
        for input in &self.inputs {
            write!(f, " {}", input)?;
        }
        Ok(())
    }
}

impl StatementT {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        static RE: LazyLock<Regex> =
            LazyLock::new(|| Regex::new(r"^(\S+)\s+(.*?)\s*=\s*(\S+)\s+(\S+)\s*(.*)$").unwrap());
        let err = || anyhow::anyhow!("failed to parse {s}");
        let caps = RE.captures(s).ok_or_else(err)?;

        let shape = MaybeTemplate::<Shape>::parse(&caps[1])?;
        let kind = caps[3].to_string();
        let specifier = MaybeTemplate::<String>::parse(&caps[4])?;
        let inputs = caps[5].split_whitespace().map(|s| s.to_string()).collect();

        let output_tokens: Vec<_> = caps[2].split_whitespace().collect();
        anyhow::ensure!(output_tokens.len() % 2 == 0);
        let mut outputs_types = Vec::new();
        let mut outputs = Vec::new();
        for chunk in output_tokens.chunks_exact(2) {
            outputs_types.push(MaybeTemplate::<usize>::parse(chunk[0])?);
            outputs.push(chunk[1].to_string());
        }

        Ok(StatementT {
            shape,
            outputs,
            outputs_types,
            kind,
            specifier,
            inputs,
        })
    }
}

impl std::fmt::Display for StatementSeqT {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        for stmt in self.iter() {
            writeln!(f, "{};", stmt)?;
        }
        Ok(())
    }
}

impl StatementSeqT {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        let mut seq = Self::default();
        for raw in s.lines() {
            if raw.is_empty() {
            } else if raw.starts_with("#") {
            } else {
                anyhow::ensure!(raw.ends_with(";"));
                let stmt = StatementT::parse(raw.trim_end_matches(";").trim())?;
                seq.try_push(stmt)?;
            }
        }
        Ok(seq)
    }
}

#[test]
fn empty_sequence() {
    assert_eq!(StatementSeqT::default().to_string(), "");
}

#[test]
fn deserialize_complex_statement() {
    let stmt_txt = "8 5 x 6 y = add v1 a b c";
    let stmt_ir = StatementT::parse(stmt_txt).unwrap();
    let stmt_txt2 = stmt_ir.to_string();
    assert_eq!(stmt_txt, stmt_txt2);
}

#[test]
fn stmt_seq() {
    let text = "\
4 1 a 2 x 3 y 4 z = env load;
2c 3 b = env store x y z;
2c 3 e = env store x y z;
";
    let ir = StatementSeqT::parse(text).unwrap();
    let text2 = ir.to_string();
    assert_eq!(text2, text);
}

#[test]
fn stmt_seq_t() {
    let text = "\
?shape 1 a 2 x 3 y 4 z = env load;
2c ?3 b = env store x y z;
2c 3 e = env ?store x y z;
";
    let ir = StatementSeqT::parse(text).unwrap();
    assert!(matches!(ir[0].shape, MaybeTemplate::Template(_)));
    assert!(matches!(ir[0].outputs_types[2], MaybeTemplate::Concrete(_)));
    assert!(matches!(ir[1].shape, MaybeTemplate::Concrete(_)));
    assert!(matches!(ir[1].outputs_types[0], MaybeTemplate::Template(_)));
    assert!(matches!(ir[2].shape, MaybeTemplate::Concrete(_)));
    assert!(matches!(ir[2].specifier, MaybeTemplate::Template(_)));
    let text2 = ir.to_string();
    assert_eq!(text2, text);

    let expected = "\
1y 1 a 2 x 3 y 4 z = env load;
2c 8 b = env store x y z;
2c 3 e = env xxx x y z;
";

    let ir = ir.concretize(
        &[("shape".to_string(), Shape::new(1, Some("y".to_string())))]
            .into_iter()
            .collect(),
        &[("3".to_string(), 8)].into_iter().collect(),
        &[("store".to_string(), "xxx".to_string())]
            .into_iter()
            .collect(),
    );

    assert_eq!(ir.to_string(), expected);
}
