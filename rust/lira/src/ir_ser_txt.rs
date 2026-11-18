use std::sync::LazyLock;

use regex::Regex;

use crate::*;

impl std::fmt::Display for Dimension {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match &self.lanes_mult {
            Some(mult) => write!(f, "{}{}", self.lanes_base, mult),
            None => write!(f, "{}", self.lanes_base),
        }
    }
}

impl Dimension {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        static RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(\d+)(.*)$").unwrap());
        let err = || anyhow::anyhow!("failed to parse {s}");
        let caps = RE.captures(s).ok_or_else(err)?;
        Ok(Self {
            lanes_base: caps[1].parse()?,
            lanes_mult: (!caps[2].is_empty()).then(|| caps[2].to_string()),
        })
    }
}

impl std::fmt::Display for Shape {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if self.is_scalar() {
            return write!(f, ".");
        }
        for (i, dimension) in self.dimensions.iter().enumerate() {
            if i > 0 {
                write!(f, ".")?;
            }
            write!(f, "{dimension}")?;
        }
        Ok(())
    }
}

impl Shape {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        if s == "." {
            return Ok(Self::default());
        }
        Ok(Self {
            dimensions: s
                .split('.')
                .map(Dimension::parse)
                .collect::<anyhow::Result<_>>()?,
        })
    }
}

impl std::fmt::Display for Statement {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if !self.shape.is_scalar() {
            write!(f, "{} ", self.shape)?;
        }
        for (typ, name) in self.outputs_types.iter().zip(&self.outputs) {
            write!(f, "{typ} {name} ")?;
        }
        write!(f, "= {} {}", self.kind, self.specifier)?;
        for input in &self.inputs {
            write!(f, " {}", input)?;
        }
        Ok(())
    }
}

impl Statement {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        let err = || anyhow::anyhow!("failed to parse {s}");
        let (left, right) = s.split_once('=').ok_or_else(err)?;
        let mut output_tokens: Vec<_> = left.split_whitespace().collect();
        let shape = if output_tokens.len() % 2 == 0 {
            Shape::default()
        } else {
            let shape = Shape::parse(output_tokens[0])?;
            output_tokens.remove(0);
            shape
        };
        let mut rhs = right.split_whitespace();
        let kind = rhs.next().ok_or_else(err)?.to_string();
        let specifier = rhs.next().ok_or_else(err)?.to_string();
        let inputs = rhs.map(str::to_string).collect();
        let mut outputs_types = Vec::new();
        let mut outputs = Vec::new();
        for chunk in output_tokens.chunks_exact(2) {
            outputs_types.push(chunk[0].parse()?);
            outputs.push(chunk[1].to_string());
        }

        Ok(Statement {
            shape,
            outputs,
            outputs_types,
            kind,
            specifier,
            inputs,
        })
    }
}

impl std::fmt::Display for StatementSeq {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        for stmt in self.iter() {
            writeln!(f, "{};", stmt)?;
        }
        Ok(())
    }
}

impl StatementSeq {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        let mut seq = StatementSeq::default();
        for raw in s.split(';').filter(|part| !part.trim().is_empty()) {
            let stmt = Statement::parse(raw.trim())?;
            seq.try_push(stmt)?;
        }
        Ok(seq)
    }
}

#[test]
fn empty_sequence() {
    assert_eq!(StatementSeq::default().to_string(), "");
}

#[test]
fn deserialize_complex_statement() {
    let stmt_txt = "8 5 x 6 y = add v1 a b c";
    let stmt_ir = Statement::parse(stmt_txt).unwrap();
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
    let ir = StatementSeq::parse(text).unwrap();
    let text2 = ir.to_string();
    assert_eq!(text2, text);
}
