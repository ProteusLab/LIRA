use std::rc::Rc;

use ahash::AHashMap;
use lira::{Shape, StatementSeq};

pub struct Statement {
    pub shape: Shape,
    pub outputs: Vec<usize>,
    pub kind: String,
    pub spec: String,
    pub inputs: Vec<Selector>,
    pub implicit: Option<State>,
}

#[derive(Clone)]
pub struct Selector {
    pub stmt: Rc<Statement>,
    pub output: usize,
}

#[derive(Default)]
pub enum State {
    #[default]
    Initial,
    After(Rc<Statement>),
}

impl Selector {
    pub fn new(stmt: Rc<Statement>, output: usize) -> Self {
        Self { stmt, output }
    }
}

impl Statement {
    pub fn from_stmt(
        stmt: &lira::Statement,
        inputs: Vec<Selector>,
        implicit: Option<State>,
    ) -> Self {
        Self {
            shape: stmt.shape.clone(),
            outputs: stmt.outputs_types.clone(),
            kind: stmt.kind.clone(),
            spec: stmt.specifier.clone(),
            inputs,
            implicit,
        }
    }

    pub fn to_stmt(&self, outputs: Vec<String>, inputs: Vec<String>) -> lira::Statement {
        lira::Statement {
            shape: self.shape.clone(),
            outputs,
            outputs_types: self.outputs.clone(),
            kind: self.kind.clone(),
            specifier: self.spec.clone(),
            inputs,
        }
    }
}

pub fn lira2dfg(seq: &StatementSeq, is_pure: impl Fn(&str) -> bool) -> State {
    let mut state = State::Initial;
    let mut name2sel: AHashMap<String, Selector> = AHashMap::new();
    for stmt in seq.iter() {
        let is_dirty = !is_pure(&stmt.kind);
        let inputs = stmt.inputs.iter().map(|i| name2sel[i].clone()).collect();
        let implicit = is_dirty.then(|| std::mem::take(&mut state));
        let s = Rc::new(Statement::from_stmt(stmt, inputs, implicit));
        if is_dirty {
            state = State::After(s.clone())
        }
        for o in 0..stmt.outputs.len() {
            name2sel.insert(stmt.outputs[o].to_string(), Selector::new(s.clone(), o));
        }
    }
    state
}

pub fn dfg2lira(state: &State) -> StatementSeq {
    #[derive(Default)]
    struct Ser {
        seq: StatementSeq,
        counter: usize,
        cache: AHashMap<*const Statement, usize>,
    }
    impl Ser {
        fn gen_temp_name(&mut self) -> String {
            let name = format!("t{}", self.counter);
            self.counter += 1;
            name
        }
        fn state(&mut self, state: &State) {
            let State::After(source) = state else { return };
            self.stmt(source);
        }
        fn sel(&mut self, sel: &Selector) -> String {
            let id = self.stmt(&sel.stmt);
            self.seq[id].outputs[sel.output].clone()
        }
        fn stmt(&mut self, stmt: &Rc<Statement>) -> usize {
            if let Some(outputs) = self.cache.get(&Rc::as_ptr(stmt)) {
                return *outputs;
            }
            if let Some(implicit) = &stmt.implicit {
                self.state(implicit);
            }
            let inputs = stmt.inputs.iter().map(|input| self.sel(input)).collect();
            let outputs = stmt.outputs.iter().map(|_| self.gen_temp_name()).collect();
            let s = stmt.to_stmt(outputs, inputs);
            let id = self.seq.len();
            self.cache.insert(Rc::as_ptr(stmt), id);
            self.seq.try_push(s).unwrap();
            id
        }
    }
    let mut ser = Ser::default();
    ser.state(state);
    ser.seq
}

#[test]
fn dfg_round_trip() {
    let text = "\
1 5 ra = input 0;
1 64 delta = input 1;
1 5 rd = input 2;
1 0 unused = const 0;
1 64 base = read X ra;
1 64 addr = op add_64 base delta;
1 64 val = env load64 addr;
1 = write X rd val;
";
    // Reorder basing on dataflow, remove unused pure statement.
    let text_expected = "\
1 5 t0 = input 0;
1 64 t1 = read X t0;
1 64 t2 = input 1;
1 64 t3 = op add_64 t1 t2;
1 64 t4 = env load64 t3;
1 5 t5 = input 2;
1 = write X t5 t4;
";
    let ir = StatementSeq::parse(text).unwrap();
    let dfg = lira2dfg(&ir, |kind| ["input", "op", "const"].contains(&kind));
    let ir = dfg2lira(&dfg);
    let text2 = ir.to_string();
    for stmt in ir.iter() {
        eprintln!("{stmt}");
    }
    assert_eq!(text2, text_expected);
}
