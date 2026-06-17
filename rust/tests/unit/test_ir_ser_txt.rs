use lira::*;

#[test]
fn test_empty_sequence() {
    let seq = SeqBuilder::new().build().unwrap();
    assert_eq!(seq.to_string(), "");
}

#[test]
fn test_built_sequence_roundtrip() {
    let mut seq = SeqBuilder::new();
    let a = seq.input(0, 32);
    let b = seq.const_(42, 32);
    let r = seq.add(&a, &b);
    seq.output(&r, 0);
    let stmts = seq.build().unwrap();
    let text = stmts.to_string();
    let seq2 = StatementSeq::parse(&text).unwrap();
    assert_eq!(stmts, seq2);
}

#[test]
fn test_shape_with_mult() {
    let text = "4c 32 _t1 = input 0;\n4c 32 _t2 = input 0;\n4c 32 _t3 = op add_32 _t1 _t2;\n1 = output 0 _t3;\n";
    let seq = StatementSeq::parse(text).unwrap();
    let text2 = seq.to_string();
    assert_eq!(text, text2);
    assert_eq!(seq[0].shape.lanes_base, 4);
    assert_eq!(seq[0].shape.lanes_mult, Some("c".into()));
}

#[test]
fn test_read_write() {
    let rf = RegisterFile {
        name: "XRegs".into(), attributes: vec![],
        reg_size: Shape { lanes_base: 32, lanes_mult: None },
        regs: vec![Register { name: "x0".into(), attributes: vec![] }],
    };
    let mut seq = SeqBuilder::new();
    let reg = seq.input(0, 5);
    let v = seq.read(&rf, &reg);
    seq.write(&rf, &reg, &v);
    let stmts = seq.build().unwrap();
    let text = stmts.to_string();
    let seq2 = StatementSeq::parse(&text).unwrap();
    assert_eq!(seq2[1].kind, "read");
    assert_eq!(seq2[2].kind, "write");
}

#[test]
fn test_env_and_cond_env() {
    let get_pc = EnvironmentFunction { name: "getPC".into(), attributes: vec![], inputs: vec![], outputs: vec![32] };
    let write_mem = EnvironmentFunction { name: "writeMem16".into(), attributes: vec![], inputs: vec![32, 16], outputs: vec![] };
    let mut seq = SeqBuilder::new();
    seq.env(&get_pc, vec![]);
    let cond = seq.input(0, 1);
    let addr = seq.input(1, 32);
    let fallback = seq.input(2, 32);
    seq.cond_env(&write_mem, &cond, vec![&addr], vec![&fallback]);
    let stmts = seq.build().unwrap();
    let text = stmts.to_string();
    let seq2 = StatementSeq::parse(&text).unwrap();
    assert_eq!(seq2[0].kind, "env");
    assert_eq!(seq2.last().unwrap().kind, "cond_env");
}

#[test]
fn test_builder_decode_snippet() {
    let mut sb = SnippetBuilder::new("decode_0");
    let enc = sb.input(0, 32);
    let c7 = sb.const_(7, 32);
    let shifted = sb.lsr(&enc, &c7);
    let low5 = sb.extract_low(&shifted, 5);
    let extended = sb.extend_zero(&low5, 32);
    sb.output(&extended, 0);
    let snip = sb.build().unwrap();
    let text = snip.seq.to_string();
    let seq2 = StatementSeq::parse(&text).unwrap();
    assert_eq!(seq2.len(), 6);
}

#[test]
fn test_builder_constraint_snippet() {
    let mut sb = SnippetBuilder::new("constraint_36");
    let enc = sb.input(0, 32);
    let mask = sb.const_(28799, 32);
    let masked = sb.and_(&enc, &mask);
    let expected = sb.const_(20483, 32);
    let ok = sb.eq(&masked, &expected);
    sb.output(&ok, 0);
    let snip = sb.build().unwrap();
    let text = snip.seq.to_string();
    let seq2 = StatementSeq::parse(&text).unwrap();
    assert_eq!(seq2.len(), 6);
}
