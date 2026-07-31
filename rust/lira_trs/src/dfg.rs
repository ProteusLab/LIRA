use std::rc::Rc;

use ahash::AHashMap;
use lira::Shape;

pub struct Statement {
    pub shape: Shape,
    pub outputs: Vec<usize>,
    pub kind: String,
    pub spec: String,
    pub inputs: Vec<Selector>,
    pub implicit: Implicit,
}

#[derive(Debug, Clone, Copy)]
pub enum ImplicitKind {
    Pure,
    Implicit,
    ImplicitRead,
}
#[derive(Default)]
pub enum Implicit {
    #[default]
    Pure,
    Implicit(State),
    ImplicitRead(State),
}

#[derive(Clone)]
pub struct Selector {
    pub stmt: Rc<Statement>,
    pub output: usize,
}

#[derive(Default, Clone)]
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

impl State {
    pub fn _dbg_print(&self, align_kind: usize, align_spec: usize) {
        #[derive(Default)]
        struct Ser {
            counter: usize,
            cache: AHashMap<*const Statement, String>,
            align_kind: usize,
            align_spec: usize,
        }
        impl Ser {
            fn gen_temp_name(&mut self) -> String {
                let name = format!("t{}", self.counter);
                self.counter += 1;
                name
            }
            fn state(&mut self, state: &State) -> String {
                match state {
                    State::Initial => "initial".to_string(),
                    State::After(statement) => format!("after {}", self.stmt(statement)),
                }
            }
            fn sel(&mut self, sel: &Selector) -> String {
                let idx = match sel.output {
                    0 => "".to_string(),
                    n => format!(".{n}"),
                };
                format!("{}{idx}", self.stmt(&sel.stmt))
            }
            fn stmt(&mut self, stmt: &Rc<Statement>) -> String {
                let key = Rc::as_ptr(stmt);
                if let Some(name) = self.cache.get(&key) {
                    return name.to_string();
                }

                let inputs: Vec<_> = stmt.inputs.iter().map(|sel| self.sel(sel)).collect();
                let inputs = inputs.join(" ");
                let inputs = format!("[{inputs}]");
                let implicit = match &stmt.implicit {
                    Implicit::Pure => "(pure)".to_string(),
                    Implicit::Implicit(state) => format!("(implicit {})", self.state(state)),
                    Implicit::ImplicitRead(state) => {
                        format!("(implicit_read {})", self.state(state))
                    }
                };
                let name = self.gen_temp_name();
                let outputs = format!("{:?}", stmt.outputs);
                let shape = format!("{}", stmt.shape);
                eprintln!(
                    "statement {name:>3} = {:<4} {:<4}  {:<4$} {:<5$}  {inputs:<20} {implicit}",
                    shape, outputs, stmt.kind, stmt.spec, self.align_kind, self.align_spec,
                );

                self.cache.insert(key, name.clone());
                name
            }
        }
        let mut ser = Ser::default();
        ser.align_kind = align_kind;
        ser.align_spec = align_spec;
        eprintln!("_dbg_print");
        ser.state(self);
        eprintln!();
    }
}
