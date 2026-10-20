use anyhow::Context;
use du_utils_timed::timed_print;
use lira_opt::Theory;
use lira_trs::dfg;
use rayon::{ThreadPoolBuilder, prelude::*};

fn test(sa: &str, sb: &str, mgc: usize, eq: bool) -> anyhow::Result<()> {
    let pool = ThreadPoolBuilder::new().num_threads(1).build().unwrap();
    pool.install(|| {
        test_(sa, sb, mgc, eq).with_context(|| {
            anyhow::anyhow!(
                "while comparing:\n---\n{sa}\n---\n{sb}\n---\nMGC: {mgc}\nExpected eq: {eq:?}"
            )
        })
    })
}
fn test_(sa: &str, sb: &str, mgc: usize, eq: bool) -> anyhow::Result<()> {
    let ir_a = lira::StatementSeq::parse(sa)?;
    let ir_b = lira::StatementSeq::parse(sb)?;

    let implicitness = |kind: &str| match kind {
        "input" | "op.g" | "const" => dfg::Implicitness::Pure,
        _ => dfg::Implicitness::Write,
    };

    let dfg_a = dfg::State::from_lira(&ir_a, implicitness);
    let dfg_b = dfg::State::from_lira(&ir_b, implicitness);

    let mut lira = Theory::default();
    lira.add_transformation_rulesets(mgc);

    let state_a = dfg_a.to_egraph(&mut lira);
    let state_b = dfg_b.to_egraph(&mut lira);

    lira.run_ruleset_set_transformation_costs_to_zero();
    lira.run_ruleset_transformations_operations();

    let state_a = state_a.canon(&lira);
    let state_b = state_b.canon(&lira);

    anyhow::ensure!(eq == (state_a == state_b));

    Ok(())
}

#[test]
fn operations() -> anyhow::Result<()> {
    let snippet_a = "\
1 64 a = input 0;
1 64 b = input 1;
1 64 add_a_b = op.g add a b;
1 64 sub_a_b = op.g sub a b;
1 64 val = op.g add b sub_a_b;
1 = output _ val;
";
    let snippet_b = "\
1 64 t0 = input 0;
1 64 t1 = input 1;
1 = output _ t0;
";
    let snippet_c = "\
1 64 t0 = input 0;
1 64 t1 = input 1;
1 = output _ t1;
";

    test(snippet_a, snippet_b, 2, true)?;
    test(snippet_a, snippet_c, 2, false)?;

    Ok(())
}

#[test]
fn operations_stress() -> anyhow::Result<()> {
    let batches = batches();
    dbg!();

    // Within-batch: every pair must be equal.
    let pairs: Vec<_> = (0..batches.len())
        .flat_map(|b0| {
            let n = batches[b0].items.len();
            (0..n).flat_map(move |i| (0..i).map(move |j| (b0, i, j)))
        })
        .collect();
    pairs.into_par_iter().for_each(|(b0, i, j)| {
        let b = &batches[b0];
        timed_print(format!("{} {i} {j}", b.name), 100, || {
            test(b.items[i], b.items[j], 2, true).unwrap();
        });
    });
    dbg!();
    // Between-batches: every pair must be unequal.
    let pairs: Vec<_> = (0..batches.len())
        .flat_map(|b0| {
            let n0 = batches[b0].items.len();
            let batches = &batches;
            (0..b0).flat_map(move |b1| {
                let n1 = batches[b1].items.len();
                (0..n0).flat_map(move |i| (0..n1).map(move |j| (b0, b1, i, j)))
            })
        })
        .collect();
    pairs.into_par_iter().for_each(|(b0, b1, i, j)| {
        let b0b = &batches[b0];
        let b1b = &batches[b1];
        timed_print(format!("{b0} {b1} {i} {j}"), 100, || {
            test(b0b.items[i], b1b.items[j], 2, false).unwrap();
        });
    });
    dbg!();

    Ok(())
}

struct Batch {
    name: &'static str,
    items: Vec<&'static str>,
}
fn batches() -> Vec<Batch> {
    vec![
        // -------------------------------------------------------------------
        //  Canon: `a`
        //  Exercises: add/sub/xor/orr/mul identities, idempotence, double
        //  negation, absorption, select, bit-shift-by-zero.
        // -------------------------------------------------------------------
        Batch {
            name: "a",
            items: vec![
                "1 64 a = input 0;\n1 = output _ a;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g add a z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g sub a z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g xor a z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g orr a z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 one = const 1;\n1 64 r = op.g mul a one;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 r = op.g and a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 r = op.g orr a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 na = op.g not a;\n1 64 r = op.g not na;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 ab = op.g and a b;\n1 64 r = op.g orr ab a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 ab = op.g orr a b;\n1 64 r = op.g and ab a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 1 c = input 2;\n1 64 r = op.g select c a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 1 one = const 1;\n1 64 r = op.g select one a b;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g lsl a z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g lsr a z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g asr a z;\n1 = output _ r;\n",
            ],
        },
        // -------------------------------------------------------------------
        //  Canon: `b`
        //  Exercises: cancellation via add/sub, xor self-inverse, select
        //  with 0-selector, identities on `b`.
        // -------------------------------------------------------------------
        Batch {
            name: "b",
            items: vec![
                "1 64 a = input 0;\n1 64 b = input 1;\n1 = output _ b;\n",
                "1 64 b = input 1;\n1 64 z = const 0;\n1 64 r = op.g add b z;\n1 = output _ r;\n",
                "1 64 b = input 1;\n1 64 z = const 0;\n1 64 r = op.g add z b;\n1 = output _ r;\n",
                "1 64 b = input 1;\n1 64 z = const 0;\n1 64 r = op.g orr b z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 axb = op.g xor a b;\n1 64 r = op.g xor a axb;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 ab = op.g add a b;\n1 64 r = op.g sub ab a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 ab = op.g add b a;\n1 64 r = op.g sub ab a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 1 z = const 0;\n1 64 r = op.g select z a b;\n1 = output _ r;\n",
            ],
        },
        // -------------------------------------------------------------------
        //  Canon: `0`
        //  Exercises: annihilation, self-cancel, De Morgan → complement pair,
        //  scalable distributivity + ring cancellation.
        // -------------------------------------------------------------------
        Batch {
            name: "zero64",
            items: vec![
                "1 64 z = const 0;\n1 = output _ z;\n",
                "1 64 a = input 0;\n1 64 r = op.g xor a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 r = op.g sub a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g and a z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 z = const 0;\n1 64 r = op.g mul a z;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 na = op.g not a;\n1 64 r = op.g and a na;\n1 = output _ r;\n",
                //                 // scalable: a*(b+c+d) - (a*b + a*c + a*d)  ==  0
                //                 // Path: distributivity of mul over add (twice), associativity
                //                 // of add, then sub(x, x) → 0. ~10 operations on the LHS.
                //                 "\
                // 1 64 a    = input 0;
                // 1 64 b    = input 1;
                // 1 64 c    = input 2;
                // 1 64 d    = input 3;
                // 1 64 bc   = op.g add b c;
                // 1 64 bcd  = op.g add bc d;
                // 1 64 lhs  = op.g mul a bcd;
                // 1 64 ab   = op.g mul a b;
                // 1 64 ac   = op.g mul a c;
                // 1 64 ad   = op.g mul a d;
                // 1 64 abac = op.g add ab ac;
                // 1 64 abcd = op.g add abac ad;
                // 1 64 r    = op.g sub lhs abcd;
                // 1 = output _ r;\n",
            ],
        },
        // -------------------------------------------------------------------
        //  Canon: `a - b`
        //  Exercises: sub↔add(neg), identities under sub, commuted operands.
        // -------------------------------------------------------------------
        Batch {
            name: "a_minus_b",
            items: vec![
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 r = op.g sub a b;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 nb = op.g neg b;\n1 64 r = op.g add a nb;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 nb = op.g neg b;\n1 64 r = op.g add nb a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 z = const 0;\n1 64 a0 = op.g add a z;\n1 64 r = op.g sub a0 b;\n1 = output _ r;\n",
                // (a - a) + (a - b)
                "\
1 64 a  = input 0;
1 64 b  = input 1;
1 64 aa = op.g sub a a;
1 64 ab = op.g sub a b;
1 64 r  = op.g add aa ab;
1 = output _ r;\n",
            ],
        },
        // -------------------------------------------------------------------
        //  Canon: `a | b`
        //  Exercises: orr comm/assoc, idempotence, absorption-style
        //  reduction, De Morgan.
        // -------------------------------------------------------------------
        Batch {
            name: "a_or_b",
            items: vec![
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 r = op.g orr a b;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 r = op.g orr b a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 ab = op.g orr a b;\n1 64 r = op.g orr ab a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 ab = op.g orr a b;\n1 64 r = op.g orr a ab;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 b = input 1;\n1 64 na = op.g not a;\n1 64 nb = op.g not b;\n1 64 nab = op.g and na nb;\n1 64 r = op.g not nab;\n1 = output _ r;\n",
            ],
        },
        // -------------------------------------------------------------------
        //  Canon: 1-bit `false`
        // -------------------------------------------------------------------
        Batch {
            name: "false1",
            items: vec![
                "1 1 z = const 0;\n1 = output _ z;\n",
                "1 64 a = input 0;\n1 1  r = op.g ult a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 1  r = op.g slt a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 1  r = op.g ne a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 1  r = op.g sub_u_overflow a a;\n1 = output _ r;\n",
            ],
        },
        // -------------------------------------------------------------------
        //  Canon: 1-bit `true`
        // -------------------------------------------------------------------
        Batch {
            name: "true1",
            items: vec![
                "1 1 one = const 1;\n1 = output _ one;\n",
                "1 64 a = input 0;\n1 1  r = op.g eq a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 1  r = op.g ule a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 1  r = op.g sle a a;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 1  r = op.g uge a a;\n1 = output _ r;\n",
            ],
        },
        // -------------------------------------------------------------------
        //  Canon: `all-ones`
        // -------------------------------------------------------------------
        Batch {
            name: "all_ones64",
            items: vec![
                "1 64 a = input 0;\n1 64 na = op.g not a;\n1 64 r = op.g orr a na;\n1 = output _ r;\n",
                "1 64 a = input 0;\n1 64 na = op.g not a;\n1 64 r = op.g xor a na;\n1 = output _ r;\n",
            ],
        },
    ]
}
