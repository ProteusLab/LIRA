use std::rc::Rc;

use ahash::AHashMap;
use du_utils_slist::{SList, slist};
use egglog::*;
use egglog::{extract::DefaultCost, prelude::*};

use crate::{
    dfg::{self, Statement},
    egraph::{EGraph, Quoted},
};

impl EGraph {
    pub fn new_dfg() -> Self {
        let mut r = Self::default();

        // Add sorts
        r.execute_many(&slist![(
            (sort Statement)
            (datatype State (state_initial) (state_after Statement))
            (datatype Selector (sel i64 Statement))
            (datatype Shape (shape i64) (shape_dynamic i64 String))
            (sort Outputs)
            (sort Inputs)
            (datatype Implicit (pure) (implicit State))
            (constructor stmt (Shape Outputs String String Inputs Implicit) Statement)
        )]);
        for i in 0..4 {
            r.add_constructor(format!("out{i}"), &vec!["i64"; i], "Outputs");
        }
        for i in 0..10 {
            r.add_constructor(format!("in{i}"), &vec!["Selector"; i], "Inputs");
        }

        // Add global variables namespaces
        r.add_function("universe_state", &["String"], "State", None);
        r.add_function("universe_stmt", &["String"], "Statement", None);

        r
    }

    pub fn add_dfg(&mut self, state: &dfg::State, name: &str) {
        let mut ser = Ser {
            eg: self,
            cache: Default::default(),
        };
        let finish = ser.state(state);
        self.execute(slist![(set(universe_state {Quoted(name)})[[finish]])]);
    }

    // Note: it's very inefficient to call this function many times.
    pub fn get_dfg(&mut self, name: &str) -> dfg::State {
        self.extract(|_| 1).get_dfg(name)
    }
    // Note: it's very inefficient to call this function many times.
    pub fn get_dfg_with(&mut self, name: &str, f: impl Fn(&str) -> u64 + 'static) -> dfg::State {
        self.extract(f).get_dfg(name)
    }

    pub fn extract(&mut self, f: impl Fn(&str) -> u64 + 'static) -> Extracted {
        let extractor = egglog::extract::Extractor::compute_costs_from_rootsorts(
            None,
            self._inner(),
            CostModel(f),
        );

        let rel = "universe_state";
        let func = self._inner().get_function(rel).unwrap();
        assert_eq!(func.schema().input.len(), 1);
        let sort_input = func.schema().input[0].clone();
        let sort_output = func.schema().output.clone();

        let results = query(
            self._inner_mut(),
            &[("k", sort_input.clone()), ("v", sort_output.clone())],
            facts![(= (universe_state k) v)],
        )
        .unwrap();

        let mut td = egglog::TermDag::default();
        let mut index = AHashMap::new();
        for row in results.iter() {
            let [key, value] = row.try_into().unwrap();
            let (_, tid) = extractor
                .extract_best_with_sort(self._inner(), &mut td, value, sort_output.clone())
                .unwrap();
            let key = self
                ._inner()
                .value_to_base::<egglog::sort::S>(key)
                .to_string();
            index.insert(key, tid);
        }

        Extracted { td, index }
    }
}

pub struct Extracted {
    td: TermDag,
    index: AHashMap<String, TermId>,
}

impl Extracted {
    pub fn get_dfg(&self, name: &str) -> dfg::State {
        let &term_id = self.index.get(name).unwrap_or_else(|| panic!("no {name}"));
        let mut des = Des {
            td: &self.td,
            stmt_cache: AHashMap::new(),
        };
        des.state(term_id)
    }
}

struct CostModel<F: Fn(&str) -> u64>(F);
impl<F: Fn(&str) -> u64> egglog::extract::CostModel<DefaultCost> for CostModel<F> {
    fn fold(&self, _: &str, children_cost: &[DefaultCost], head_cost: DefaultCost) -> DefaultCost {
        use egglog::extract::Cost as _;
        children_cost.iter().fold(head_cost, |a, b| a.combine(b))
    }
    fn enode_cost(
        &self,
        _: &prelude::EGraph,
        func: &Function,
        _: &egglog::FunctionRow,
    ) -> DefaultCost {
        (self.0)(func.name())
    }
    fn base_value_cost(
        &self,
        egraph: &prelude::EGraph,
        sort: &ArcSort,
        value: Value,
    ) -> DefaultCost {
        use egglog::extract::Cost as _;
        if sort.name() == "String" {
            let s: egglog::sort::S = egraph.value_to_base(value);
            return (self.0)(s.as_str());
        }
        DefaultCost::unit()
    }
}

struct Ser<'a> {
    eg: &'a mut EGraph,
    cache: AHashMap<*const Statement, String>,
}

impl Ser<'_> {
    fn state(&mut self, state: &dfg::State) -> SList {
        match state {
            dfg::State::Initial => slist![(state_initial)],
            dfg::State::After(statement) => {
                let bound = self.stmt(statement);
                slist![(state_after (universe_stmt {Quoted(bound)}))]
            }
        }
    }
    fn sel(&mut self, sel: &dfg::Selector) -> SList {
        let name = self.stmt(&sel.stmt);
        slist![(sel {sel.output} (universe_stmt {Quoted(name)}))]
    }
    fn stmt(&mut self, stmt: &Rc<Statement>) -> String {
        if let Some(name) = self.cache.get(&Rc::as_ptr(stmt)) {
            return name.to_string();
        }
        let shape = match &stmt.shape.lanes_mult {
            Some(mult) => slist![(shape_dynamic {stmt.shape.lanes_base} {Quoted(mult)})],
            None => slist![(shape {stmt.shape.lanes_base})],
        };
        let outputs = slist![
            ({ format!("out{}", stmt.outputs.len()) }[stmt.outputs.iter().map(|o| slist![{ o }])])
        ];
        let inputs: Vec<_> = stmt.inputs.iter().map(|sel| self.sel(sel)).collect();
        let inputs = slist![({ format!("in{}", inputs.len()) }[inputs])];
        let implicit = match &stmt.implicit {
            Some(imp) => slist![(implicit {self.state(imp)})],
            None => slist![(pure)],
        };

        let name = self.eg.gen_temp_name("add_dfg_stmt");
        self.eg.execute(slist![
            (set (universe_stmt {Quoted(&name)})
                (stmt
                    [[shape, outputs]]
                    {Quoted(&stmt.kind)} {Quoted(&stmt.spec)}
                    [[inputs, implicit]]
                )
            )
        ]);
        self.cache.insert(Rc::as_ptr(stmt), name.clone());
        name
    }
}

struct Des<'a> {
    td: &'a TermDag,
    stmt_cache: AHashMap<TermId, Rc<dfg::Statement>>,
}

impl<'a> Des<'a> {
    fn state(&mut self, t: TermId) -> dfg::State {
        match self.td.get(t) {
            Term::App(sym, children) if sym.as_str() == "state_initial" => dfg::State::Initial,
            Term::App(sym, children) if sym.as_str() == "state_after" => {
                let stmt = self.stmt(children[0]);
                dfg::State::After(stmt)
            }
            other => panic!("expected state, got {:?}", other),
        }
    }

    fn stmt(&mut self, t: TermId) -> Rc<dfg::Statement> {
        if let Some(stmt) = self.stmt_cache.get(&t) {
            return stmt.clone();
        }

        match self.td.get(t) {
            Term::App(sym, children) if sym.as_str() == "stmt" => {
                let shape = self.shape(children[0]);
                let outputs = self.outputs(children[1]);
                let kind = self.lit_string(children[2]);
                let spec = self.lit_string(children[3]);
                let inputs = self.inputs(children[4]);
                let implicit = self.implicit(children[5]);

                let statement = Rc::new(dfg::Statement {
                    shape,
                    outputs,
                    kind,
                    spec,
                    inputs,
                    implicit,
                });
                self.stmt_cache.insert(t, statement.clone());
                statement
            }
            other => panic!("expected stmt, got {:?}", other),
        }
    }

    fn shape(&mut self, t: TermId) -> lira::Shape {
        match self.td.get(t) {
            Term::App(sym, children) if sym.as_str() == "shape" => {
                let lanes_base = self.lit_usize(children[0]);
                lira::Shape {
                    lanes_base,
                    lanes_mult: None,
                }
            }
            Term::App(sym, children) if sym.as_str() == "shape_dynamic" => {
                let lanes_base = self.lit_usize(children[0]);
                let lanes_mult = Some(self.lit_string(children[1]));
                lira::Shape {
                    lanes_base,
                    lanes_mult,
                }
            }
            other => panic!("expected shape, got {:?}", other),
        }
    }

    fn outputs(&mut self, t: TermId) -> Vec<usize> {
        match self.td.get(t) {
            Term::App(sym, children) if sym.as_str().starts_with("out") => {
                let mut out = Vec::new();
                for &child in children {
                    out.push(self.lit_usize(child));
                }
                out
            }
            other => panic!("expected outputs, got {:?}", other),
        }
    }

    fn inputs(&mut self, t: TermId) -> Vec<dfg::Selector> {
        match self.td.get(t) {
            Term::App(sym, children) if sym.as_str().starts_with("in") => {
                let mut inputs = Vec::new();
                for &child in children {
                    inputs.push(self.selector(child));
                }
                inputs
            }
            other => panic!("expected inputs, got {:?}", other),
        }
    }

    fn implicit(&mut self, t: TermId) -> Option<dfg::State> {
        match self.td.get(t) {
            Term::App(sym, children) if sym.as_str() == "pure" => None,
            Term::App(sym, children) if sym.as_str() == "implicit" => {
                let state = self.state(children[0]);
                Some(state)
            }
            other => panic!("expected implicit, got {:?}", other),
        }
    }

    fn selector(&mut self, t: TermId) -> dfg::Selector {
        match self.td.get(t) {
            Term::App(sym, children) if sym.as_str() == "sel" => {
                let output = self.lit_usize(children[0]);
                let stmt = self.stmt(children[1]);
                dfg::Selector { output, stmt }
            }
            other => panic!("expected sel, got {:?}", other),
        }
    }

    fn lit_usize(&self, t: TermId) -> usize {
        match self.td.get(t) {
            Term::Lit(ast::Literal::Int(n)) => *n as usize,
            other => panic!("expected i64 literal, got {:?}", other),
        }
    }

    fn lit_string(&self, t: TermId) -> String {
        match self.td.get(t) {
            Term::Lit(ast::Literal::String(s)) => s.to_string(),
            other => panic!("expected string literal, got {:?}", other),
        }
    }
}

#[test]
fn dfg3egraph() {
    let text = "\
1 64 a = get a;
1 64 b = get b;
1 64 add_a_b = op add_64 a b;
1 64 sub_a_b = op sub_64 a b;
1 64 val = op add_64 b sub_a_b;
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

    eg.add_ruleset("opt");
    // Add commutativity
    eg.add_rule(
        "opt",
        slist![(("=" e (stmt h o {Quoted("op")} {Quoted("add_64")} (in2 a b) m)))],
        slist![(("union" e (stmt h o {Quoted("op")} {Quoted("add_64")} (in2 b a) m)))],
    );
    // (add (sub a b) b) -> a
    eg.add_rule(
        "opt",
        slist![(("=" e (sel 0 (stmt h o {Quoted("op")} {Quoted("add_64")} (in2
            (sel 0 (stmt h o {Quoted("op")} {Quoted("sub_64")} (in2 a b) (pure)))
            b
        ) (pure)))))],
        slist![(("union" e a))],
    );
    eg.run_ruleset_saturate("opt");

    let dfg = eg.get_dfg("test");

    let ir = dfg::dfg2lira(&dfg);
    let text2 = ir.to_string();
    for stmt in ir.iter() {
        eprintln!("{stmt}");
    }
    assert_eq!(text2, text_expected);
}
