use lira_trs::{dfg, egraph::EGraph};

#[test]
fn rewrite() {
    let text = "\
1 64 a = get a;
1 64 b = get b;
1 64 add_a_b = op add.64 a b;
1 64 sub_a_b = op sub.64 a b;
1 64 val = op add.64 b sub_a_b;
1 = output _ val;
";
    // Optimize. Note, that commutativity is necessary
    let text_expected = "\
1 64 t0 = get a;
1 64 t1 = get b;
1 = output _ t0;
";

    let ir = lira::StatementSeq::parse(text).unwrap();
    let dfg = dfg::lira2dfg(&ir, |kind| ["input", "op", "const"].contains(&kind));

    let mut eg = EGraph::new_dfg();
    eg.add_dfg(&dfg, "test");

    eg._inner_mut()
        .parse_and_run_program(None, include_str!("./opt.egg"))
        .unwrap();

    eg.run_ruleset_saturate("opt");

    let dfg = eg.get_dfg("test");

    let ir = dfg::dfg2lira(&dfg);
    let text2 = ir.to_string();
    for stmt in ir.iter() {
        eprintln!("{stmt}");
    }
    assert_eq!(text2, text_expected);
}
