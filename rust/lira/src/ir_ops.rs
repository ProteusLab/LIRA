use std::sync::LazyLock;

use ahash::AHashMap;
use anyhow::{Result, bail, ensure};

pub fn parse_signature_unary(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 1]> {
    let &[n] = outputs else {
        bail!("unary: expected 1 output, got {}", outputs.len())
    };
    let &[m] = inputs else {
        bail!("unary: expected 1 input, got {}", inputs.len())
    };
    ensure!(n == m, "unary: output {n} != input {m}");
    Ok([n])
}

pub fn parse_signature_binary(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 1]> {
    let &[n] = outputs else {
        bail!("binary: expected 1 output, got {}", outputs.len())
    };
    let &[a, b] = inputs else {
        bail!("binary: expected 2 inputs, got {}", inputs.len())
    };
    ensure!(a == n && b == n, "binary: inputs {a},{b} != output {n}");
    Ok([n])
}

pub fn parse_signature_ternary(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 1]> {
    let &[n] = outputs else {
        bail!("ternary: expected 1 output, got {}", outputs.len())
    };
    let &[a, b, c] = inputs else {
        bail!("ternary: expected 3 inputs, got {}", inputs.len())
    };
    ensure!(
        a == n && b == n && c == n,
        "ternary: inputs {a},{b},{c} != output {n}"
    );
    Ok([n])
}

pub fn parse_signature_cmp(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 1]> {
    let &[o] = outputs else {
        bail!("cmp: expected 1 output, got {}", outputs.len())
    };
    let &[a, b] = inputs else {
        bail!("cmp: expected 2 inputs, got {}", inputs.len())
    };
    ensure!(o == 1, "cmp: output must be 1, got {o}");
    ensure!(a == b, "cmp: input widths differ: {a} vs {b}");
    Ok([a])
}

pub fn parse_signature_select(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 1]> {
    let &[n] = outputs else {
        bail!("select: expected 1 output, got {}", outputs.len())
    };
    let &[s, a, b] = inputs else {
        bail!("select: expected 3 inputs, got {}", inputs.len())
    };
    ensure!(s == 1, "select: selector width must be 1, got {s}");
    ensure!(a == n && b == n, "select: inputs {a},{b} != output {n}");
    Ok([n])
}

pub fn parse_signature_extract_low(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 2]> {
    let &[a] = outputs else {
        bail!("extract_low: expected 1 output, got {}", outputs.len())
    };
    let &[b] = inputs else {
        bail!("extract_low: expected 1 input, got {}", inputs.len())
    };
    ensure!(a <= b, "extract_low: output {a} > input {b}");
    Ok([a, b])
}

pub fn parse_signature_extend(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 2]> {
    let &[a] = outputs else {
        bail!("extend: expected 1 output, got {}", outputs.len())
    };
    let &[b] = inputs else {
        bail!("extend: expected 1 input, got {}", inputs.len())
    };
    ensure!(a >= b, "extend: output {a} < input {b}");
    Ok([a, b])
}

pub fn parse_signature_insert(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 2]> {
    let &[a] = outputs else {
        bail!("insert: expected 1 output, got {}", outputs.len())
    };
    let &[a1, b, a2] = inputs else {
        bail!("insert: expected 3 inputs, got {}", inputs.len())
    };
    ensure!(
        a1 == a && a2 == a,
        "insert: outer inputs {a1},{a2} != output {a}"
    );
    ensure!(a >= b, "insert: output {a} < inserted {b}");
    Ok([a, b])
}

pub fn parse_signature_extract(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 2]> {
    let &[a] = outputs else {
        bail!("extract: expected 1 output, got {}", outputs.len())
    };
    let &[b1, b2] = inputs else {
        bail!("extract: expected 2 inputs, got {}", inputs.len())
    };
    ensure!(b1 == b2, "extract: input widths differ: {b1} vs {b2}");
    ensure!(a <= b1, "extract: output {a} > input {b1}");
    Ok([a, b1])
}

pub fn parse_signature_concat(outputs: &[usize], inputs: &[usize]) -> Result<[usize; 3]> {
    let &[a] = outputs else {
        bail!("concat: expected 1 output, got {}", outputs.len())
    };
    let &[b, c] = inputs else {
        bail!("concat: expected 2 inputs, got {}", inputs.len())
    };
    ensure!(a == b + c, "concat: output {a} != {b} + {c}");
    Ok([a, b, c])
}

pub fn generate_name(base: impl ToString, p: &[usize]) -> String {
    p.iter().fold(base.to_string(), |r, x| format!("{r}_{x}"))
}

pub static BASE_OP_SIGNATURE: LazyLock<
    AHashMap<&'static str, fn(&[usize], &[usize]) -> Result<Vec<usize>>>,
> = LazyLock::new(|| {
    macro_rules! f {
        ($op:ident $f:ident) => {
            (
                stringify!($op),
                (|o, i| $f(o, i).map(|v| v.to_vec()))
                    as fn(&[usize], &[usize]) -> Result<Vec<usize>>,
            )
        };
    }
    [
        f!(neg parse_signature_unary),
        f!(not parse_signature_unary),
        f!(clz parse_signature_unary),
        f!(ctz parse_signature_unary),
        f!(cnt parse_signature_unary),
        f!(rev parse_signature_unary),
        f!(add parse_signature_binary),
        f!(sub parse_signature_binary),
        f!(mul parse_signature_binary),
        f!(rem_s parse_signature_binary),
        f!(rem_u parse_signature_binary),
        f!(and parse_signature_binary),
        f!(orr parse_signature_binary),
        f!(xor parse_signature_binary),
        f!(lsl parse_signature_binary),
        f!(lsr parse_signature_binary),
        f!(asr parse_signature_binary),
        f!(ror parse_signature_binary),
        f!(rol parse_signature_binary),
        f!(div_s parse_signature_ternary),
        f!(div_u parse_signature_ternary),
        f!(eq parse_signature_cmp),
        f!(ne parse_signature_cmp),
        f!(ugt parse_signature_cmp),
        f!(uge parse_signature_cmp),
        f!(sgt parse_signature_cmp),
        f!(sge parse_signature_cmp),
        f!(ult parse_signature_cmp),
        f!(ule parse_signature_cmp),
        f!(slt parse_signature_cmp),
        f!(sle parse_signature_cmp),
        f!(add_s_overflow parse_signature_cmp),
        f!(add_u_overflow parse_signature_cmp),
        f!(sub_s_overflow parse_signature_cmp),
        f!(sub_u_overflow parse_signature_cmp),
        f!(select parse_signature_select),
        f!(extract_low parse_signature_extract_low),
        f!(extend_zero parse_signature_extend),
        f!(extend_sign parse_signature_extend),
        f!(insert parse_signature_insert),
        f!(orr_shifted parse_signature_insert),
        f!(extract parse_signature_extract),
        f!(concat_hi_lo parse_signature_concat),
    ]
    .into_iter()
    .collect()
});
