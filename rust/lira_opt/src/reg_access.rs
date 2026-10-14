use ahash::AHashMap;
use lira::{ArchIndex, Shape, Statement, StatementSeq, StatementSeqBuilder};

/// Expects:
/// - ~all writes to be conditional~
/// - all writes to use same lane/ty (to merge them)
///
/// Note: this can't be expressed efficiently in egraph because of AC blowup.
pub fn optimize_reg_writes(
    stmts: &StatementSeq,
    index: &ArchIndex,
) -> anyhow::Result<StatementSeq> {
    let count_writes = |stmts: &[Statement]| {
        stmts
            .iter()
            .filter(|stmt| stmt.kind.contains("write"))
            .count()
    };

    let writes_num = count_writes(&stmts[..]);
    let writes_offset = stmts.len() - writes_num;
    anyhow::ensure!(
        count_writes(&stmts[writes_offset..]) == writes_num,
        "current implementation assumes all writes to be at the very end",
    );

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    struct InputPlusConstant {
        input: Option<usize>,
        constant: i128,
    }
    impl InputPlusConstant {
        /// Check if these can never be equal
        fn ne(&self, other: &Self) -> bool {
            self.input == other.input && self.constant != other.constant
        }
    }
    let mut good_rsi: AHashMap<&str, InputPlusConstant> = AHashMap::new();

    let mut r = StatementSeqBuilder::default();
    for stmt in stmts[..writes_offset].iter() {
        if let Some(ipc) = match stmt.as_stmt_specific(index) {
            Ok(lira::StmtSpecificStd::Input(input)) => Some(InputPlusConstant {
                input: Some(input.id),
                constant: 0,
            }),
            Ok(lira::StmtSpecificStd::Const(c)) => Some(InputPlusConstant {
                input: None,
                constant: c.value,
            }),
            Ok(lira::StmtSpecificStd::OpG(opg)) => match opg.op {
                "add"
                    if let (Some(ipc0), Some(ipc1)) = (
                        good_rsi.get(&opg.args[0].as_str()),
                        good_rsi.get(&opg.args[1].as_str()),
                    ) && (ipc0.input.is_none() || ipc1.input.is_none()) =>
                {
                    Some(InputPlusConstant {
                        input: ipc0.input.or(ipc1.input),
                        constant: ipc0.constant.wrapping_add(ipc1.constant),
                    })
                }
                _ => None,
            },
            _ => None,
        } {
            good_rsi.insert(stmt.outputs[0].as_str(), ipc);
        }
        r.try_push(stmt.clone()).unwrap();
    }

    let names0: Vec<_> = (0..writes_num).map(|n| format!("_ra_w_0{n}")).collect();
    let names1: Vec<_> = (0..writes_num).map(|n| format!("_ra_w_1{n}")).collect();
    let names2: Vec<_> = (0..writes_num).map(|n| format!("_ra_w_2{n}")).collect();
    struct RegWrites<'a> {
        rf: &'a String,
        writes: Vec<RegWrite<'a>>,
    }
    #[derive(Debug)]
    struct RegWrite<'a> {
        shape: &'a Shape,
        rsi: &'a str,
        addr: InputPlusConstant,
        cond: &'a str,
        val: &'a str,
    }
    let mut writes: Vec<RegWrites> = vec![];
    for (n, (stmt, stmt_inputs)) in stmts.iter_with_ext_inputs().skip(writes_offset).enumerate() {
        let (cond, rsi, val) = match stmt.as_stmt_specific(index)? {
            lira::StmtSpecificStd::CondWrite(w) => (w.cond, w.rsi, w.value),
            lira::StmtSpecificStd::Write(w) => {
                r.try_push_str(&format!("{} 1 {} = const 1", stmt.shape, &names0[n]))
                    .unwrap();
                (names0[n].as_str(), w.rsi, w.value)
            }
            _ => panic!("unexpected kind {}", stmt.kind),
        };

        let err = || anyhow::anyhow!("bad rsi in {stmt}");
        let addr = good_rsi.get(rsi).ok_or_else(err)?;
        let rw = RegWrite {
            shape: &stmt.shape,
            addr: *addr,
            cond: cond,
            rsi,
            val,
        };
        if let Some(writes) = writes.iter_mut().find(|w| w.rf == &stmt.specifier) {
            if let Some(previous_pos) = writes.writes.iter().position(|w| &w.addr == addr)
                && writes
                    .writes
                    .iter()
                    .skip(previous_pos + 1)
                    .all(|w| w.addr.ne(addr))
            {
                // There was write on the same location and
                //  we can swap this write with all in between means
                //  we can merge this write with the previous.
                let previous = &mut writes.writes[previous_pos];
                anyhow::ensure!(previous.shape == rw.shape);

                let cond = format!(
                    "{} 1 {} = op.g orr {} {}",
                    previous.shape, names1[n], previous.cond, rw.cond
                );
                r.try_push_str(&cond).unwrap();

                let ty = stmt_inputs.last().unwrap().1;
                let val = format!(
                    "{} {} {} = op.g select {} {} {}",
                    previous.shape, ty, names2[n], rw.cond, rw.val, previous.val
                );
                r.try_push_str(&val).unwrap();

                previous.cond = &names1[n];
                previous.val = &names2[n];
            } else {
                writes.writes.push(rw);
            }
        } else {
            writes.push(RegWrites {
                rf: &stmt.specifier,
                writes: vec![rw],
            });
        }
    }
    for writes in writes {
        for write in writes.writes {
            let write = format!(
                "{} = cond.write {} {} {} {}",
                write.shape, writes.rf, write.cond, write.rsi, write.val
            );
            r.try_push(Statement::parse(&write).unwrap()).unwrap();
        }
    }

    Ok(r.finish())
}
