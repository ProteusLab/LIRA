use crate::*;

impl std::fmt::Display for Shape {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match &self.lanes_mult {
            Some(mult) => write!(f, "{}{}", self.lanes_base, mult),
            None => write!(f, "{}", self.lanes_base),
        }
    }
}

impl Shape {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        let digits = s.bytes().take_while(|b| b.is_ascii_digit()).count();
        anyhow::ensure!(digits > 0, "failed to parse shape {s:?}");
        let lanes_base = s[..digits].parse()?;
        let lanes_mult = (!s[digits..].is_empty()).then(|| s[digits..].to_string());
        Ok(Self {
            lanes_base,
            lanes_mult,
        })
    }
}

impl std::fmt::Display for Statement {
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

impl Statement {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        let tokens: Vec<_> = s.split_whitespace().collect();
        let eq = tokens
            .iter()
            .position(|t| *t == "=")
            .ok_or_else(|| anyhow::anyhow!("failed to parse {s:?}: missing `=`"))?;
        let (left, after_eq) = tokens.split_at(eq);
        let right = &after_eq[1..];

        anyhow::ensure!(!left.is_empty(), "failed to parse {s:?}: missing shape");
        anyhow::ensure!(
            right.len() >= 2,
            "failed to parse {s:?}: missing kind or specifier"
        );

        let shape = Shape::parse(left[0])?;
        let output_tokens = &left[1..];
        anyhow::ensure!(
            output_tokens.len() % 2 == 0,
            "failed to parse {s:?}: outputs must be type/name pairs"
        );
        let mut outputs_types = Vec::new();
        let mut outputs = Vec::new();
        for chunk in output_tokens.chunks_exact(2) {
            outputs_types.push(chunk[0].parse()?);
            outputs.push(chunk[1].to_string());
        }

        let kind = right[0].to_string();
        let specifier = right[1].to_string();
        let inputs = right[2..].iter().map(|s| s.to_string()).collect();

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
            writeln!(f, "{}", stmt)?;
        }
        Ok(())
    }
}

impl StatementSeq {
    pub fn parse(s: &str) -> anyhow::Result<Self> {
        let mut seq = StatementSeq::default();
        for raw in s.lines() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let stmt = Statement::parse(line)?;
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
fn shape_parse() {
    assert_eq!(Shape::parse("1").unwrap(), Shape::new_scalar());
    assert_eq!(Shape::parse("4c").unwrap(), Shape::new(4, Some("c".into())));
    assert_eq!(
        Shape::parse("32*2").unwrap(),
        Shape::new(32, Some("*2".into()))
    );
    assert!(Shape::parse("").is_err());
    assert!(Shape::parse("c4").is_err());
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
4 1 a 2 x 3 y 4 z = env load
2c 3 b = env store x y z
2c 3 e = env store x y z
";
    let ir = StatementSeq::parse(text).unwrap();
    let text2 = ir.to_string();
    assert_eq!(text2, text);
}

#[test]
fn no_semicolons_in_output() {
    let text = "1 32 x = const 1\n1 32 y = const 2\n";
    let ir = StatementSeq::parse(text).unwrap();
    let out = ir.to_string();
    assert_eq!(out, text);
    assert!(!out.contains(';'));
}

#[test]
fn comments_blank_lines_and_trailing_whitespace() {
    let text = "\
# comment

   # indented comment
4 1 a = env load   \n\
2c 3 b = env store a\t
";
    let expected = "4 1 a = env load\n2c 3 b = env store a\n";
    let ir = StatementSeq::parse(text).unwrap();
    assert_eq!(ir.to_string(), expected);
}

#[test]
fn flexible_whitespace_around_equals() {
    let text = "4 1 a\t=\tconst 1\n4  1  b =  const 1\n";
    let ir = StatementSeq::parse(text).unwrap();
    assert_eq!(ir.len(), 2);
    assert_eq!(ir.to_string(), "4 1 a = const 1\n4 1 b = const 1\n");
}

#[test]
fn semicolon_is_an_ordinary_character() {
    let stmt = Statement::parse("1 = const 1;").unwrap();
    assert_eq!(stmt.specifier, "1;");
}

#[test]
fn missing_equals_is_rejected() {
    assert!(Statement::parse("1 = const 1").is_ok());
    assert!(Statement::parse("1 const 1").is_err());
    assert!(Statement::parse("= const 1").is_err());
}

#[test]
fn odd_output_tokens_are_rejected() {
    assert!(Statement::parse("1 32 x 3 = op add x x").is_err());
}
