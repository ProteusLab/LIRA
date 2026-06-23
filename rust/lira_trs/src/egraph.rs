use std::borrow::Borrow;

use du_utils_slist::{SList, StrString, parse};

///! Thin wrapper over [`egglog::EGraph`]

#[derive(Default)]
pub struct EGraph {
    inner: egglog::EGraph,
    program: Vec<String>,

    /// Used to generate unique names basing on pattern
    counters: ahash::AHashMap<String, usize>,
}

impl EGraph {
    #[track_caller]
    // pub fn execute(&mut self, code: &SList) -> Vec<egglog::CommandOutput> {
    pub fn execute(&mut self, code: impl Borrow<SList>) -> Vec<egglog::CommandOutput> {
        let code = code.borrow().to_string();
        let loc = std::panic::Location::caller();
        let r = self.inner.parse_and_run_program(None, &code);
        self.program.push(code);
        r.unwrap_or_else(|err| {
            eprintln!("ERROR in program:");
            for line in self.program.iter() {
                eprintln!("  {line}")
            }
            panic!("{err} at {loc}")
        })
    }
    #[track_caller]
    pub fn execute_many(&mut self, code: &SList) {
        let code = parse![code; ([*@])].unwrap();
        for code in code {
            self.execute(&code);
        }
    }

    pub fn get_program(&self) -> &Vec<String> {
        &self.program
    }

    pub fn overall_run_report(&self) -> &impl std::fmt::Display {
        self.inner.get_overall_run_report()
    }

    pub fn get_size(&self, func: &str) -> usize {
        self.inner.get_size(func)
    }

    pub fn _inner(&self) -> &egglog::EGraph {
        &self.inner
    }
    pub fn _inner_mut(&mut self) -> &mut egglog::EGraph {
        &mut self.inner
    }

    pub fn gen_temp_name(&mut self, key: impl StrString) -> String {
        let prefix = "_et";
        if let Some(k) = self.counters.get_mut(key.as_str()) {
            *k += 1;
            format!("{prefix}{k}")
        } else {
            self.counters.insert(key.into_string(), 0);
            format!("{prefix}0")
        }
    }
}

pub struct Quoted<T: std::fmt::Display>(pub T);
impl<'a, T: std::fmt::Display> ToString for &'a Quoted<T> {
    fn to_string(&self) -> String {
        format!("\"{}\"", self.0)
    }
}
