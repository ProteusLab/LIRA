use lira_opt::Theory;
use lira_trs::dfg;

#[test]
fn rewrite() -> anyhow::Result<()> {
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

    let ir = lira::StatementSeq::parse(text)?;
    let dfg_input = dfg::State::from_lira(&ir, |kind| match kind {
        "input" | "op" | "const" => dfg::Implicitness::Pure,
        _ => dfg::Implicitness::Write,
    });

    let commute_lhs = "\
    1 64 a = input 0;
    1 64 b = input 1;
    1 64 r = op add.64 a b;
    1 = output 0 r;
";
    let commute_rhs = "\
    1 64 a = input 0;
    1 64 b = input 1;
    1 64 r = op add.64 b a;
    1 = output 0 r;
";
    let simplify_lhs = "\
    1 64 a = input 0;
    1 64 b = input 1;
    1 64 i = op sub.64 a b;
    1 64 r = op add.64 i b;
    1 = output 0 r;
";
    let simplify_rhs = "\
    1 64 a = input 0;
    1 = output 0 a;
";
    let commute_lhs = lira::ir_t::StatementSeqT::parse(commute_lhs)?;
    let commute_rhs = lira::ir_t::StatementSeqT::parse(commute_rhs)?;
    let simplify_lhs = lira::ir_t::StatementSeqT::parse(simplify_lhs)?;
    let simplify_rhs = lira::ir_t::StatementSeqT::parse(simplify_rhs)?;

    let mut lira = Theory::default();
    let state = dfg_input.to_egraph(&mut lira);

    lira.set_ruleset_active("opt");
    lira.add_rewrite_from_snippets_t(&commute_lhs, &commute_rhs, None)?;
    lira.add_rewrite_from_snippets_t(&simplify_lhs, &simplify_rhs, None)?;

    lira.enrich();
    while lira.run_ruleset("opt") {}
    lira.enrich();

    let dfg = dfg::State::from_egraph(&lira, state);

    let ir = dfg.to_lira();
    let text2 = ir.to_string();
    for stmt in ir.iter() {
        eprintln!("{stmt}");
    }
    eprintln!();
    assert_eq!(text2, text_expected);

    let simplify_lhs = "\
    1 64 a = input 0;
    1 64 b = input 1;
    1 64 i = op sub.64 a b;
    1 64 r = op add.64 i b;
    1 = output 0 r;
";
    // Error: uses second input
    let simplify_rhs = "\
    1 64 a = input 1;
    1 = output 0 a;
";
    let simplify_lhs = lira::ir_t::StatementSeqT::parse(simplify_lhs)?;
    let simplify_rhs = lira::ir_t::StatementSeqT::parse(simplify_rhs)?;

    let mut lira = Theory::default();
    let state = dfg_input.to_egraph(&mut lira);

    lira.set_ruleset_active("opt");
    lira.add_rewrite_from_snippets_t(&commute_lhs, &commute_rhs, None)?;
    lira.add_rewrite_from_snippets_t(&simplify_lhs, &simplify_rhs, None)?;

    lira.enrich();
    while lira.run_ruleset("opt") {}
    lira.enrich();

    let dfg = dfg::State::from_egraph(&lira, state);

    let ir = dfg.to_lira();
    let text2 = ir.to_string();
    for stmt in ir.iter() {
        eprintln!("{stmt}");
    }
    eprintln!();
    assert_ne!(text2, text_expected);

    Ok(())
}
