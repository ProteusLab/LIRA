use du_utils_slist::{SList, StrString, slist};

use crate::egraph::EGraph;

impl EGraph {
    #[track_caller]
    pub fn add_sort(&mut self, name: impl StrString) {
        self.execute(slist![(sort[[name]])]);
    }

    #[track_caller]
    pub fn add_constructor<S: StrString>(
        &mut self,
        name: impl StrString,
        inputs: &[S],
        sort: impl StrString,
    ) {
        self.execute(slist![(constructor[[name]]([inputs])[[sort]])]);
    }
    #[track_caller]
    pub fn add_constant(&mut self, name: impl StrString, sort: impl StrString) {
        self.execute(slist![(constructor[[name]]()[[sort]])]);
    }

    #[track_caller]
    pub fn add_relation<S: StrString>(&mut self, name: impl StrString, inputs: &[S]) {
        self.execute(slist![(relation[[name]]([inputs]))]);
    }
    #[track_caller]
    pub fn add_relation_new<S: StrString>(&mut self, name: impl StrString, inputs: &[S]) -> String {
        let name = self.gen_temp_name(name.as_str());
        self.add_relation(&name, inputs);
        name
    }

    #[track_caller]
    pub fn add_function<S: StrString>(
        &mut self,
        name: impl StrString,
        inputs: &[S],
        output: impl StrString,
        merge: Option<&str>,
    ) {
        let merge = match merge {
            Some(merge) => vec![":merge", merge],
            None => vec![":no-merge"],
        };
        self.execute(slist![(function[[name]]([inputs])[[output]][merge])]);
    }

    #[track_caller]
    pub fn add_ruleset(&mut self, name: impl StrString) {
        self.execute(slist![(ruleset[[name]])]);
    }
    #[track_caller]
    pub fn add_ruleset_new(&mut self, name: impl StrString) -> String {
        let name = self.gen_temp_name(name);
        self.add_ruleset(&name);
        name
    }

    #[track_caller]
    pub fn add_rule(
        &mut self,
        ruleset: impl StrString,
        lhs: impl Into<SList>,
        rhs: impl Into<SList>,
    ) {
        self.execute(slist![(rule [[lhs]] [[rhs]] ":ruleset" [[ruleset]])]);
    }

    /// Runs given ruleset a single time
    ///
    /// Returns "If any changes were made to the database"
    #[track_caller]
    pub fn run_ruleset(&mut self, ruleset: impl StrString) -> bool {
        let r = self.execute(slist![(run [[ruleset]] 1)]);
        assert_eq!(r.len(), 1);
        match &r[0] {
            egglog::CommandOutput::RunSchedule(run_report) => run_report.updated,
            r => panic!("{r:?}"),
        }
    }

    #[track_caller]
    pub fn run_ruleset_saturate(&mut self, ruleset: impl StrString) -> bool {
        let mut at_least_once = false;
        while self.run_ruleset(&ruleset) {
            at_least_once = true;
        }
        at_least_once
    }
    /// Runs ruleset one time. Runs second time and asserts there was no new changes.
    #[track_caller]
    pub fn run_ruleset_saturate_single(&mut self, ruleset: impl StrString) {
        self.run_ruleset(&ruleset);
        let new = self.run_ruleset(ruleset);
        assert!(!new);
    }
}
