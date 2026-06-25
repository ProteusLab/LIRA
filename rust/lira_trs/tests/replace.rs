use lira_trs::{dfg, egraph::EGraph};

#[test]
fn replace() {
    let text = "1 = get a;\n";

    let ir = lira::StatementSeq::parse(text).unwrap();
    let dfg = dfg::lira2dfg(&ir, |_| false);

    let test = |best: &'static str| {
        let mut eg = EGraph::new_dfg();
        eg.add_dfg(&dfg, "test");
        eg._inner_mut()
            .parse_and_run_program(None, include_str!("./replace.egg"))
            .unwrap();
        eg.run_ruleset_saturate("replace");
        let dfg = eg.get_dfg_with("test", move |s| {
            if ["a", "b", "c"].contains(&s) && s != best {
                2
            } else {
                1
            }
        });
        let ir = dfg::dfg2lira(&dfg);
        let text2 = ir.to_string();
        assert_eq!(text2, format!("1 = get {best};\n"));
    };

    test("a");
    test("b");
    test("c");
}
