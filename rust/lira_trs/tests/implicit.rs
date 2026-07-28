use dateg::execute;
use lira_trs::{dfg, theory::Lira};

fn optimize(ir: &lira::StatementSeq) -> lira::StatementSeq {
    let dfg = dfg::State::from_lira(&ir, |kind| match kind {
        "input" | "op" | "const" => dfg::ImplicitKind::Pure,
        "read" => dfg::ImplicitKind::ImplicitRead,
        _ => dfg::ImplicitKind::Implicit,
    });
    dfg._dbg_print();

    let mut lira = Lira::default();
    let state = dfg.to_egraph(&mut lira);

    let stmt_r = lira.stmt_r;
    let stmt_w = lira.stmt_w;
    let in1 = lira.in1;
    let in2 = lira.in2;
    let out0 = lira.out0;
    let out1 = lira.out1;
    let state_after = lira.state_after;
    let sel0 = lira.sel0;
    execute! {lira;
        (val read (String) {"read".to_string()})
        (val write (String) {"write".to_string()})

        (set_ruleset_active "opt")
        // Read doesn't modify the state
        (rewrite (state_after (stmt_r _ _ _ _ _ s)) s)
        // Write of just read value does nothing
        (rewrite
            (state_after (stmt_w h (out0) {write} rf (in2 rsi
                (sel0 (stmt_r h (out1 _) {read} rf (in1 rsi) s))
            ) s))
            s
        )
        // Write can be shadowed by consecutive one
        (rule
            (query state0 (state_after (stmt_w h (out0) {write} rf (in2 rsi _) s)))
            (query state1 (state_after (stmt_w h (out0) {write} rf (in2 rsi val) state0)))
            (set   state1 (state_after (stmt_w h (out0) {write} rf (in2 rsi val) s)))
        )
        // Read of just written value
        (rewrite
            (sel0 (stmt_r h _ {read} rf (in1 rsi)
                (state_after (stmt_w h _ {write} rf (in2 rsi val) _))
            ))
        val)
    }

    while lira.run_ruleset("factorize vector arguments") {}
    while lira.run_ruleset("aliases convert") {}
    while lira.run_ruleset("opt") {}
    while lira.run_ruleset("aliases convert") {}
    while lira.run_ruleset("de factorize vector arguments") {}

    let dfg = dfg::State::from_egraph(&lira, state);
    dfg._dbg_print();

    let ir = dfg.to_lira();
    for stmt in ir.iter() {
        eprintln!("{stmt};");
    }
    ir
}

#[test]
fn implicit1() {
    let input = "\
1 64 ra = input ra;
1 64 rb = input rb;
1 64 rc = input rc;
1 64 va = read gpr ra;
1 64 vb = read gpr rb;
1 = write gpr ra va;
1 64 vb2 = read gpr rb;
1 64 va2 = read gpr ra;
1 = write gpr ra vb2;
";
    let expected = "\
1 64 t0 = input ra;
1 64 t1 = input rb;
1 64 t2 = read gpr t1;
1 = write gpr t0 t2;
";

    let ir = lira::StatementSeq::parse(input).unwrap();
    let output = optimize(&ir).to_string();
    assert_eq!(output, expected);
}

#[test]
fn implicit2() {
    let input = "\
1 5 ra = input ra;
1 5 rb = input rb;
1 64 v = input v;
1 64 u = input u;
1 = write gpr ra u;
1 64 va = read gpr ra;
1 = write gpr ra v;
1 = write gpr rb va;
";
    let expected = "\
1 5 t0 = input ra;
1 64 t1 = input v;
1 = write gpr t0 t1;
1 5 t2 = input rb;
1 64 t3 = input u;
1 = write gpr t2 t3;
";

    let ir = lira::StatementSeq::parse(input).unwrap();
    let output = optimize(&ir).to_string();
    assert_eq!(output, expected);
}
