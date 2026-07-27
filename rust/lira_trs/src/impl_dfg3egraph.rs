use std::rc::Rc;

use ahash::AHashMap;
use dateg::{ContainerVec, TokenOpaque};
use dateg_extractors::dag::IndexFor;

use crate::{
    dfg::{self, Implicit},
    theory,
};

impl dfg::State {
    pub fn to_egraph(&self, lira: &mut theory::Lira) -> TokenOpaque<theory::State> {
        struct Ser<'a> {
            lira: &'a mut theory::Lira,
            cache: AHashMap<*const dfg::Statement, TokenOpaque<theory::Stmt>>,
        }
        impl Ser<'_> {
            fn state(&mut self, state: &dfg::State) -> TokenOpaque<theory::State> {
                match state {
                    dfg::State::Initial => self.lira.state_initial(),
                    dfg::State::After(statement) => {
                        let stmt = self.stmt(statement);
                        let state_after = self.lira.state_after;
                        self.lira.row_add(state_after, (stmt,))
                    }
                }
            }
            fn sel(&mut self, sel: &dfg::Selector) -> TokenOpaque<theory::Value> {
                let stmt = self.stmt(&sel.stmt);
                let output = self.lira.add_primitive_value(sel.output);
                let sel = self.lira.sel;
                let r = self.lira.row_add(sel, (output, stmt));
                r
            }
            fn stmt(&mut self, stmt: &Rc<dfg::Statement>) -> TokenOpaque<theory::Stmt> {
                if let Some(token) = self.cache.get(&Rc::as_ptr(stmt)) {
                    return *token;
                }

                let shape = self
                    .lira
                    .add_primitive_value(theory::Shape(stmt.shape.clone()));

                let outputs = theory::OutputsMany(stmt.outputs.clone());
                let outputs = self.lira.add_primitive_value(outputs);
                let out_many = self.lira.out_many;
                let outputs = self.lira.row_add(out_many, (outputs,));

                let inputs =
                    ContainerVec(stmt.inputs.iter().map(|input| self.sel(input)).collect());
                let inputs = self.lira.add_container_value(inputs);
                let in_many = self.lira.in_many;
                let inputs = self.lira.row_add(in_many, (inputs,));

                let kind = self.lira.add_primitive_value(stmt.kind.to_string());
                let spec = self.lira.add_primitive_value(stmt.spec.to_string());

                let token = match &stmt.implicit {
                    dfg::Implicit::Pure => {
                        let stmt = self.lira.stmt_p;
                        self.lira
                            .row_add(stmt, (shape, outputs, kind, spec, inputs))
                    }
                    dfg::Implicit::ImplicitRead(state) => {
                        let state = self.state(state);
                        let stmt = self.lira.stmt_r;
                        self.lira
                            .row_add(stmt, (shape, outputs, kind, spec, inputs, state))
                    }
                    dfg::Implicit::Implicit(state) => {
                        let state = self.state(state);
                        let stmt = self.lira.stmt_w;
                        self.lira
                            .row_add(stmt, (shape, outputs, kind, spec, inputs, state))
                    }
                };

                self.cache.insert(Rc::as_ptr(stmt), token);
                token
            }
        }
        let mut ser = Ser {
            lira,
            cache: Default::default(),
        };
        let r = ser.state(self);
        r
    }

    pub fn from_egraph(lira: &theory::Lira, state: TokenOpaque<theory::State>) -> Self {
        let index = lira.extract(state);

        struct Des<'a> {
            lira: &'a theory::Lira,
            index: theory::Index,
            cache: AHashMap<TokenOpaque<theory::Stmt>, Rc<dfg::Statement>>,
        }
        impl Des<'_> {
            fn state(&mut self, state: TokenOpaque<theory::State>) -> dfg::State {
                match self.index.value(state) {
                    theory::EState::Initial() => dfg::State::Initial,
                    theory::EState::StateAfter(stmt) => dfg::State::After(self.stmt(stmt)),
                }
            }
            fn stmt(&mut self, stmt: TokenOpaque<theory::Stmt>) -> Rc<dfg::Statement> {
                if let Some(stmt) = self.cache.get(&stmt) {
                    return stmt.clone();
                }
                let (shape, outputs, kind, spec, inputs, implicit) = match self.index.value(stmt) {
                    theory::EStmt::StmtP(h, o, k, s, i) => (h, o, k, s, i, dfg::Implicit::Pure),
                    theory::EStmt::StmtR(h, o, k, s, i, state) => {
                        (h, o, k, s, i, Implicit::ImplicitRead(self.state(state)))
                    }
                    theory::EStmt::StmtW(h, o, k, s, i, state) => {
                        (h, o, k, s, i, dfg::Implicit::Implicit(self.state(state)))
                    }
                };
                let statement = Rc::new(dfg::Statement {
                    shape: shape.get(self.lira).0,
                    outputs: self.index.value(outputs).0.get(self.lira).0,
                    kind: kind.get(self.lira),
                    spec: spec.get(self.lira),
                    inputs: {
                        let inputs = self.index.value(inputs).0.get(self.lira);
                        inputs.0.iter().map(|&value| self.value(value)).collect()
                    },
                    implicit,
                });
                self.cache.insert(stmt, statement.clone());
                statement
            }
            fn value(&mut self, value: TokenOpaque<theory::Value>) -> dfg::Selector {
                let theory::EValue(idx, stmt) = self.index.value(value);
                let output = idx.get(self.lira);
                let stmt = self.stmt(stmt);
                dfg::Selector { stmt, output }
            }
        }

        Des {
            lira,
            index,
            cache: Default::default(),
        }
        .state(state)
    }
}

#[cfg(test)]
fn optimize(
    ir: &lira::StatementSeq,
    post_init: impl FnOnce(&mut theory::Lira),
) -> lira::StatementSeq {
    let dfg = dfg::State::from_lira(&ir, |kind| match kind {
        "input" | "op" | "const" => dfg::ImplicitKind::Pure,
        _ => dfg::ImplicitKind::Implicit,
    });

    let mut lira = theory::Lira::default();
    let state = dfg.to_egraph(&mut lira);
    post_init(&mut lira);
    let dfg = dfg::State::from_egraph(&lira, state);

    dfg._dbg_print();

    let ir = dfg.to_lira();
    for stmt in ir.iter() {
        eprintln!("{stmt};");
    }
    ir
}

#[test]
fn dfg3egraph_simple() {
    let input = "\
1 64 a = get a;
1 64 b = get b;
1 64 val = op add_64 a b;
1 = output _ val;
";
    // Variable renaming
    let expected = "\
1 64 t0 = get a;
1 64 t1 = get b;
1 64 t2 = op add_64 t0 t1;
1 = output _ t2;
";

    let ir = lira::StatementSeq::parse(input).unwrap();
    let output = optimize(&ir, |_| {}).to_string();
    assert_eq!(output, expected);
}

#[test]
fn dfg3egraph() {
    let input = "\
1 64 a = get a;
1 64 b = get b;
1 64 add_a_b = op add_64 a b;
1 64 sub_a_b = op sub_64 a b;
1 64 val = op add_64 b sub_a_b;
1 = output _ val;
";
    // Optimize. Note, that commutativity is necessary
    let expected = "\
1 64 t0 = get a;
1 64 t1 = get b;
1 = output _ t0;
";

    let ir = lira::StatementSeq::parse(input).unwrap();
    let output = optimize(&ir, |lira| {
        let stmt_pure = lira.stmt_p;
        let sel = lira.sel;
        let in2 = lira.in2;
        let s_op = lira.s_op;
        let c0 = lira.c0;

        dateg::execute! {lira;
            (val add (String) {"add_64".to_string()})
            (val sub (String) {"sub_64".to_string()})

            (set_ruleset_active "opt")
            (rewrite
                (stmt_pure h o {s_op} {add} (in2 a b))
                (stmt_pure h o {s_op} {add} (in2 b a))
            )
            (rewrite
                (sel {c0} (stmt_pure h o {s_op} {add} (in2
                    (sel {c0} (stmt_pure h o {s_op} {sub} (in2 a b))) b
                )))
                a
            )
        }
        while lira.run_ruleset("factorize vector arguments") {}
        while lira.run_ruleset("opt") {}
    })
    .to_string();
    assert_eq!(output, expected);
}
