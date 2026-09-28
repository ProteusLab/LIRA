use ahash::AHashMap;
use anyhow::Context;
use lira::{Operation, Statement, StatementSeq, StatementSeqBuilder};

use crate::Arch;

impl Arch {
    pub fn generalize_operations(&mut self) {
        let index = lira::Arch::build_index(&self.0.operations);
        lira::Arch::iter_stmt_seq_mut_part(&mut self.0.instructions, &mut self.0.snippets)
            .for_each(|(_, stmts)| generalize_operations_stmt_seq(stmts, &index));
    }

    pub fn specialize_operations(&mut self) -> anyhow::Result<()> {
        let mut ops: AHashMap<_, _> = Default::default();
        for op in self.0.operations.iter() {
            if let Some(base) = &op.semantic_base {
                ops.insert(
                    (base.to_string(), op.outputs.clone(), op.inputs.clone()),
                    op.name.clone(),
                );
            }
        }

        for (name, stmts) in
            lira::Arch::iter_stmt_seq_mut_part(&mut self.0.instructions, &mut self.0.snippets)
        {
            let mut r = StatementSeqBuilder::default();
            let mut types = AHashMap::new();
            for stmt in stmts.iter() {
                let mut s = stmt.clone();
                if let Some((_, to)) = [("op.g", "op"), ("fold.op.g", "fold.op")]
                    .iter()
                    .find(|(fr, _)| fr == &stmt.kind)
                {
                    let inputs: Vec<_> = stmt.inputs.iter().map(|input| types[input]).collect();
                    let key = (
                        stmt.specifier.to_string(),
                        stmt.outputs_types.to_vec(),
                        inputs.to_vec(),
                    );
                    s.kind = to.to_string();
                    s.specifier = match ops.entry(key) {
                        std::collections::hash_map::Entry::Occupied(e) => e.get().to_string(),
                        std::collections::hash_map::Entry::Vacant(e) => {
                            let base = stmt.specifier.as_str();
                            let Some(parse) = lira::ir_ops::BASE_OP_SIGNATURE.get(base) else {
                                panic!("unexpected op {base}");
                            };
                            let params = parse(&stmt.outputs_types, &inputs)
                                .with_context(|| anyhow::anyhow!("{base} in {name}"))?;
                            let name = lira::ir_ops::generate_name(base, &params);
                            e.insert_entry(name.clone());
                            self.0.operations.push(Operation {
                                name: name.clone(),
                                attributes: vec![],
                                inputs,
                                outputs: stmt.outputs_types.clone(),
                                semantic_base: Some(base.to_string()),
                                semantic_func: None,
                                semantic_func_128: None,
                                semantic_table: None,
                            });
                            name
                        }
                    };
                }

                for (name, ty) in stmt.outputs.iter().zip(stmt.outputs_types.iter().copied()) {
                    let was = types.insert(name, ty);
                    assert!(was.is_none());
                }
                r.try_push(s).unwrap();
            }
            *stmts = r.finish();
        }

        Ok(())
    }
}

pub fn generalize_operations_stmt_seq(
    stmts: &mut StatementSeq,
    index: &AHashMap<&str, &Operation>,
) {
    let mut r = StatementSeqBuilder::default();
    for stmt in stmts.iter() {
        r.try_push(generalize_operations_stmt(stmt, index)).unwrap();
    }
    *stmts = r.finish();
}
pub fn generalize_operations_stmt(
    stmt: &Statement,
    index: &AHashMap<&str, &Operation>,
) -> Statement {
    let mut stmt = stmt.clone();

    if stmt.kind != "op" {
        return stmt;
    }

    let op = &index[&stmt.specifier.as_str()];
    let Some(base) = op.semantic_base.as_ref() else {
        return stmt;
    };

    stmt.kind = "op.g".to_string();
    stmt.specifier = base.to_string();

    stmt
}
