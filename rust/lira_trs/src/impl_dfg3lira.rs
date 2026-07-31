use std::rc::Rc;

use ahash::{AHashMap, AHashSet};
use lira::StatementSeq;

use crate::dfg::*;

impl Statement {
    pub fn from_lira(stmt: &lira::Statement, inputs: Vec<Selector>, implicit: Implicit) -> Self {
        Self {
            shape: stmt.shape.clone(),
            outputs: stmt.outputs_types.clone(),
            kind: stmt.kind.clone(),
            spec: stmt.specifier.clone(),
            inputs,
            implicit,
        }
    }

    pub fn to_lira(&self, outputs: Vec<String>, inputs: Vec<String>) -> lira::Statement {
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

impl State {
    pub(crate) fn as_key(&self) -> Option<*const Statement> {
        match self {
            Self::Initial => None,
            Self::After(statement) => Some(Rc::as_ptr(statement)),
        }
    }
}

impl State {
    pub fn from_lira(seq: &StatementSeq, implicit: impl Fn(&str) -> ImplicitKind) -> Self {
        let mut state = State::Initial;
        let mut name2sel: AHashMap<String, Selector> = AHashMap::new();
        for stmt in seq.iter() {
            let inputs = stmt.inputs.iter().map(|i| name2sel[i].clone()).collect();
            let implicit = match implicit(&stmt.kind) {
                ImplicitKind::Pure => Implicit::Pure,
                ImplicitKind::Implicit => Implicit::Implicit(std::mem::take(&mut state)),
                ImplicitKind::ImplicitRead => Implicit::ImplicitRead(state.clone()),
            };
            let is_write = matches!(implicit, Implicit::Implicit(_));
            let s = Rc::new(Statement::from_lira(stmt, inputs, implicit));
            if is_write {
                state = State::After(s.clone())
            }
            for o in 0..stmt.outputs.len() {
                name2sel.insert(stmt.outputs[o].to_string(), Selector::new(s.clone(), o));
            }
        }
        state
    }

    pub fn to_lira(&self) -> StatementSeq {
        #[derive(Default)]
        struct Ser {
            seq: StatementSeq,
            counter: usize,
            cache: AHashMap<*const Statement, usize>,
            followed_by: AHashMap<Option<*const Statement>, Vec<Rc<Statement>>>,
        }
        #[derive(Default)]
        struct SerInit {
            inner: Ser,
            visited: AHashSet<*const Statement>,
        }

        impl SerInit {
            fn state(&mut self, state: &State) -> Option<*const Statement> {
                match state {
                    State::Initial => None,
                    State::After(statement) => {
                        self.stmt(statement);
                        Some(Rc::as_ptr(statement))
                    }
                }
            }
            fn stmt(&mut self, statement: &Rc<Statement>) {
                let key = Rc::as_ptr(statement);
                let new = self.visited.insert(key);
                if !new {
                    return;
                }
                for input in statement.inputs.iter() {
                    self.stmt(&input.stmt);
                }
                match &statement.implicit {
                    Implicit::Pure => {}
                    Implicit::Implicit(state) => {
                        self.state(state);
                    }
                    Implicit::ImplicitRead(state) => {
                        let follows = self.state(state);
                        self.inner
                            .followed_by
                            .entry(follows)
                            .or_default()
                            .push(statement.clone());
                    }
                }
            }
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
                let inputs = stmt.inputs.iter().map(|input| self.sel(input)).collect();
                match &stmt.implicit {
                    Implicit::Pure => {}
                    Implicit::Implicit(state) => self.state(state),
                    Implicit::ImplicitRead(_) => {}
                }
                let outputs = stmt.outputs.iter().map(|_| self.gen_temp_name()).collect();
                let s = stmt.to_lira(outputs, inputs);
                let id = self.seq.len();
                self.cache.insert(Rc::as_ptr(stmt), id);
                self.seq.try_push(s).unwrap();
                if let Implicit::Implicit(state) = &stmt.implicit {
                    if let Some(followed_by) = self.followed_by.get(&state.as_key()) {
                        for stmt in followed_by.clone().iter() {
                            self.stmt(stmt);
                        }
                    }
                }
                id
            }
        }
        let mut ser = SerInit::default();
        ser.state(self);
        let mut ser = ser.inner;
        ser.state(self);
        ser.seq
    }
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
1 5 t0 = input 2;
1 5 t1 = input 0;
1 64 t2 = read X t1;
1 64 t3 = input 1;
1 64 t4 = op add_64 t2 t3;
1 64 t5 = env load64 t4;
1 = write X t0 t5;
";
    let ir = StatementSeq::parse(text).unwrap();
    let dfg = State::from_lira(&ir, |kind| match kind {
        "input" | "op" | "const" => ImplicitKind::Pure,
        _ => ImplicitKind::Implicit,
    });
    let ir = dfg.to_lira();
    let text2 = ir.to_string();
    for stmt in ir.iter() {
        eprintln!("{stmt}");
    }
    assert_eq!(text2, text_expected);
}
