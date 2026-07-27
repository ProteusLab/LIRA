use dateg::execute;
use lira_trs::{dfg, theory::Lira};

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
    let dfg = dfg::State::from_lira(&ir, |kind| match kind {
        "input" | "op" | "const" => dfg::ImplicitKind::Pure,
        _ => dfg::ImplicitKind::Implicit,
    });

    let mut lira = Lira::default();
    let state = dfg.to_egraph(&mut lira);

    let stmt_p = lira.stmt_p;
    let sel = lira.sel;
    let in2 = lira.in2;
    let s_op = lira.s_op;
    let c0 = lira.c0;
    execute! {lira;
        (val add (String) {"add.64".to_string()})
        (val sub (String) {"sub.64".to_string()})

        (set_ruleset_active "opt")
        (rewrite
            (stmt_p h o {s_op} {add} (in2 a b))
            (stmt_p h o {s_op} {add} (in2 b a))
        )
        (rewrite
            (sel {c0} (stmt_p h o {s_op} {add} (in2
                (sel {c0} (stmt_p h o {s_op} {sub} (in2 a b))) b
            )))
            a
        )
    }

    while lira.run_ruleset("factorize vector arguments") {}
    while lira.run_ruleset("opt") {}
    while lira.run_ruleset("de factorize vector arguments") {}

    let dfg = dfg::State::from_egraph(&lira, state);

    let ir = dfg.to_lira();
    let text2 = ir.to_string();
    for stmt in ir.iter() {
        eprintln!("{stmt}");
    }
    assert_eq!(text2, text_expected);
}
