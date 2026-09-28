// TODO: refactor, deduplicate, clean up.
//  Currently this code is a mess..

use ahash::AHashMap;
use dateg::{
    Entry::{Const, Var},
    RuleId,
};
use lira::{Shape, Statement, ir_t::StatementT};
use lira_trs::{IMPLICITNESS_STD, dfg::Implicitness};

use crate::Theory;

impl Theory {
    /// Adds rule to the active ruleset
    pub fn add_rewrite_from_snippets(
        &mut self,
        fr: &[Statement],
        to: &[Statement],
        implicitness: Option<&AHashMap<&'static str, Implicitness>>,
    ) -> anyhow::Result<()> {
        let fr: Vec<_> = fr
            .iter()
            .map(|stmt| StatementT::from_stmt(stmt.clone()))
            .collect();
        let to: Vec<_> = to
            .iter()
            .map(|stmt| StatementT::from_stmt(stmt.clone()))
            .collect();

        let rid = self.rewrite_from_snippets_t(&fr, &to, implicitness)?;
        self.add_ruleset_rule(rid);
        Ok(())
    }

    /// Adds rule to the active ruleset
    pub fn add_rewrite_from_snippets_t(
        &mut self,
        fr: &[StatementT],
        to: &[StatementT],
        implicitness: Option<&AHashMap<&'static str, Implicitness>>,
    ) -> anyhow::Result<()> {
        let rid = self.rewrite_from_snippets_t(fr, to, implicitness)?;
        self.add_ruleset_rule(rid);
        Ok(())
    }

    pub fn rewrite_from_snippets_t(
        &mut self,
        fr: &[StatementT],
        to: &[StatementT],
        implicitness: Option<&AHashMap<&'static str, Implicitness>>,
    ) -> anyhow::Result<RuleId> {
        crate::get_!(self
            stmt_p stmt_r stmt_w
            sel state_after
            in0 in1 in2 in3 in4
            out0 out1 out2 out3
            type_of shape_of
            out_many out_many_get
        );

        let all = || fr.iter().chain(to.iter());
        macro_rules! primitive_values {
            (let $out:ident: $ty:ident <= $iter:expr) => {
                let tmp: AHashMap<_, _> = $iter
                    .map(|v| (v.clone(), self.add_primitive_value(v.clone())))
                    .collect();
                let $out = |v: &$ty| Const(tmp[v]);
            };
        }
        let max_outputs = all().map(|s| s.outputs.len()).max().unwrap_or(0);
        primitive_values!(let cst_usize: usize <= all()
            .flat_map(|stmt| stmt.outputs_types
                .iter().map(|ty| ty.as_concrete()).flatten().copied())
            .chain(0..max_outputs)
        );
        primitive_values!(let cst_shape: Shape <= all()
            .filter_map(|stmt| stmt.shape.as_concrete())
        );
        primitive_values!(let cst_string: String <= all().map(|stmt| &stmt.kind)
            .chain(all().filter_map(|stmt| stmt.specifier.as_concrete()))
        );

        let implicitness = |stmt: &StatementT| {
            if let Some(implicitness) = implicitness {
                if let Some(implicitness) = implicitness.get(&stmt.kind.as_str()) {
                    return Ok(*implicitness);
                }
            }
            if let Some(implicitness) = IMPLICITNESS_STD.get(&stmt.kind.as_str()) {
                return Ok(*implicitness);
            }
            anyhow::bail!("unknown implicitness for stmt kind {}", stmt.kind);
        };

        let mut rb = self.rule_builder(None);
        let mut variables = AHashMap::new();
        let mut inputs = vec![];
        let mut outputs = vec![];
        let mut state_initial = None;
        let mut state = None;

        let mut vars_types = AHashMap::new();
        let mut vars_shapes = AHashMap::new();
        let mut vars_strings = AHashMap::new();

        for stmt in fr.iter() {
            if stmt.kind == "input" {
                assert_eq!(stmt.outputs.len(), 1);
                assert_eq!(stmt.inputs.len(), 0);
                let input_id: usize = stmt.specifier.as_concrete().unwrap().parse()?;
                anyhow::ensure!(input_id == inputs.len());
                let val = rb.var();
                variables.insert(&stmt.outputs[0], val);
                macro_rules! pt {
                    ($func:ident, $cst:ident, $vars:expr, $t:expr) => {
                        match &$t {
                            lira::ir_t::MaybeTemplate::Template(t) => {
                                let var = $vars.entry(t).or_insert_with(|| rb.var());
                                rb.query($func, (Var(val),), Var(*var));
                                Var(*var)
                            }
                            lira::ir_t::MaybeTemplate::Concrete(v) => {
                                let cst = $cst(v);
                                rb.query($func, (Var(val),), cst);
                                cst
                            }
                        }
                    };
                }
                pt!(type_of, cst_usize, vars_types, stmt.outputs_types[0]);
                pt!(shape_of, cst_shape, vars_shapes, stmt.shape);
                inputs.push(val);
            } else if stmt.kind == "output" {
                assert_eq!(stmt.outputs.len(), 0);
                assert_eq!(stmt.inputs.len(), 1);
                let output_id: usize = stmt.specifier.as_concrete().unwrap().parse()?;
                anyhow::ensure!(output_id == outputs.len());
                outputs.push(variables[&stmt.inputs[0]]);
            } else {
                let implicitness = implicitness(stmt)?;
                if !matches!(implicitness, Implicitness::Pure) && state_initial.is_none() {
                    let var = rb.var();
                    state_initial = Some(var);
                    state = Some(var);
                }

                let var_out_tys_many = rb.var();
                let var_out_tys = rb.var();
                rb.query(out_many, (Var(var_out_tys),), Var(var_out_tys_many));
                for i in 0..stmt.outputs.len() {
                    let output = match &stmt.outputs_types[i] {
                        lira::ir_t::MaybeTemplate::Template(t) => {
                            let var = vars_types.entry(t).or_insert_with(|| rb.var());
                            Var(*var)
                        }
                        lira::ir_t::MaybeTemplate::Concrete(v) => cst_usize(v),
                    };
                    rb.query(out_many_get, (Var(var_out_tys), cst_usize(&i)), output);
                }
                let var_inputs = rb.var();
                let v = |n: usize| Var(variables[&stmt.inputs[n]]);
                match stmt.inputs.len() {
                    0 => rb.query(in0, (), Var(var_inputs)),
                    1 => rb.query(in1, (v(0),), Var(var_inputs)),
                    2 => rb.query(in2, (v(0), v(1)), Var(var_inputs)),
                    3 => rb.query(in3, (v(0), v(1), v(2)), Var(var_inputs)),
                    4 => rb.query(in4, (v(0), v(1), v(2), v(3)), Var(var_inputs)),
                    n => anyhow::bail!("unsupported: {n} inputs in {stmt}"),
                }

                let entry_shape = match &stmt.shape {
                    lira::ir_t::MaybeTemplate::Template(t) => {
                        let var = vars_shapes.entry(t).or_insert_with(|| rb.var());
                        Var(*var)
                    }
                    lira::ir_t::MaybeTemplate::Concrete(v) => cst_shape(v),
                };
                let entry_specifier = match &stmt.specifier {
                    lira::ir_t::MaybeTemplate::Template(t) => {
                        let var = vars_strings.entry(t).or_insert_with(|| rb.var());
                        Var(*var)
                    }
                    lira::ir_t::MaybeTemplate::Concrete(v) => cst_string(v),
                };

                let st = rb.var();
                match implicitness {
                    Implicitness::Pure => rb.query(
                        stmt_p,
                        (
                            entry_shape,
                            Var(var_out_tys_many),
                            cst_string(&stmt.kind),
                            entry_specifier,
                            Var(var_inputs),
                        ),
                        Var(st),
                    ),
                    Implicitness::Read | Implicitness::Write => {
                        rb.query(
                            match implicitness {
                                Implicitness::Pure => unreachable!(),
                                Implicitness::Read => stmt_r,
                                Implicitness::Write => stmt_w,
                            },
                            (
                                entry_shape,
                                Var(var_out_tys_many),
                                cst_string(&stmt.kind),
                                entry_specifier,
                                Var(var_inputs),
                                Var(state.unwrap()),
                            ),
                            Var(st),
                        );
                    }
                }

                if matches!(implicitness, Implicitness::Write) {
                    let var = rb.var();
                    rb.query(state_after, (Var(st),), Var(var));
                    state = Some(var);
                }

                for i in 0..stmt.outputs.len() {
                    let var = rb.var();
                    rb.query(sel, (cst_usize(&i), Var(st)), Var(var));
                    variables.insert(&stmt.outputs[i], var);
                }
            }
        }

        let state_old = state;
        let mut variables = AHashMap::new();
        let mut state = state_initial;

        for stmt in to.iter() {
            if stmt.kind == "input" {
                assert_eq!(stmt.outputs.len(), 1);
                assert_eq!(stmt.inputs.len(), 0);
                let input_id: usize = stmt.specifier.as_concrete().unwrap().parse()?;
                variables.insert(&stmt.outputs[0], inputs[input_id]);
            } else if stmt.kind == "output" {
                assert_eq!(stmt.outputs.len(), 0);
                assert_eq!(stmt.inputs.len(), 1);
                let output_id: usize = stmt.specifier.as_concrete().unwrap().parse()?;
                let val = variables[&stmt.inputs[0]];
                rb.union(Var(outputs[output_id]), Var(val));
            } else {
                let implicitness = implicitness(stmt)?;

                if !matches!(implicitness, Implicitness::Pure) {
                    anyhow::ensure!(
                        state.is_some(),
                        "`to` depends on state, but `from` didn't introduce it"
                    );
                }

                let o = |n: usize| match &stmt.outputs_types[n] {
                    lira::ir_t::MaybeTemplate::Template(t) => Var(vars_types[t]),
                    lira::ir_t::MaybeTemplate::Concrete(v) => cst_usize(v),
                };
                let var_out_tys = match stmt.outputs.len() {
                    0 => rb.add(out0, ()),
                    1 => rb.add(out1, (o(0),)),
                    2 => rb.add(out2, (o(0), o(1))),
                    3 => rb.add(out3, (o(0), o(1), o(2))),
                    n => anyhow::bail!("unimplemented: {n} outputs in {stmt}"),
                };
                let v = |n: usize| Var(variables[&stmt.inputs[n]]);
                let var_inputs = match stmt.inputs.len() {
                    0 => rb.add(in0, ()),
                    1 => rb.add(in1, (v(0),)),
                    2 => rb.add(in2, (v(0), v(1))),
                    3 => rb.add(in3, (v(0), v(1), v(2))),
                    4 => rb.add(in4, (v(0), v(1), v(2), v(3))),
                    n => anyhow::bail!("unimplemented: {n} inputs in {stmt}"),
                };

                let entry_shape = match &stmt.shape {
                    lira::ir_t::MaybeTemplate::Template(t) => Var(vars_shapes[t]),
                    lira::ir_t::MaybeTemplate::Concrete(v) => cst_shape(v),
                };
                let entry_specifier = match &stmt.specifier {
                    lira::ir_t::MaybeTemplate::Template(t) => Var(vars_strings[t]),
                    lira::ir_t::MaybeTemplate::Concrete(v) => cst_string(v),
                };

                let st = match implicitness {
                    Implicitness::Pure => rb.add(
                        stmt_p,
                        (
                            entry_shape,
                            Var(var_out_tys),
                            cst_string(&stmt.kind),
                            entry_specifier,
                            Var(var_inputs),
                        ),
                    ),
                    Implicitness::Read | Implicitness::Write => rb.add(
                        match implicitness {
                            Implicitness::Pure => unreachable!(),
                            Implicitness::Read => stmt_r,
                            Implicitness::Write => stmt_w,
                        },
                        (
                            entry_shape,
                            Var(var_out_tys),
                            cst_string(&stmt.kind),
                            entry_specifier,
                            Var(var_inputs),
                            Var(state.unwrap()),
                        ),
                    ),
                };

                if matches!(implicitness, Implicitness::Write) {
                    let var = rb.add(state_after, (Var(st),));
                    state = Some(var);
                }

                for i in 0..stmt.outputs.len() {
                    let var = rb.add(sel, (cst_usize(&i), Var(st)));
                    variables.insert(&stmt.outputs[i], var);
                }
            }
        }

        if state.is_some() {
            // `state` can be `Some` only if `state_old` was
            rb.union(Var(state.unwrap()), Var(state_old.unwrap()));
        }

        Ok(rb.build())
    }
}
