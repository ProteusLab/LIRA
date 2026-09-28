mod operations;
mod vector;

use crate::Theory;

impl Theory {
    pub fn add_transformation_rulesets(&mut self, max_generation_cost: usize) {
        self.set_ruleset_active("transformations: operations");
        // Note: works on generic operations
        self.add_rules_transformations_operations(max_generation_cost);

        self.set_ruleset_active("transformations: vector");
        self.add_rules_transformations_vector();

        self.set_ruleset_active("set all transformation costs to zero");
        let sel = self.sel;
        let gc = self.generation_cost;
        dateg::execute! {self; (rule (query x (sel _ _)) (set 0 (gc x))) }
    }

    pub fn run_ruleset_set_transformation_costs_to_zero(&mut self) {
        self.run_ruleset("set all transformation costs to zero");
    }

    pub fn run_ruleset_transformations_operations(&mut self) {
        self.enrich();
        while self.run_ruleset("transformations: operations") {
            self.enrich();
        }
        self.enrich();
    }
    pub fn run_ruleset_transformations_vector(&mut self) {
        self.enrich();
        while self.run_ruleset("transformations: vector") {
            self.enrich();
        }
        self.enrich();
    }
}
