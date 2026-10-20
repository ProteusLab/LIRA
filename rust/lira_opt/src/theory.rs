use lira::Shape;
use lira_trs::theory::Value;

dateg::theory!(Lira: lira_trs::theory::Lira {
        stmt_p stmt_r stmt_w
        sel0 in0 in1 in2 out1
        scalar shape_of
        s_ s_broadcast s_const
        constant op_g_0
    };
    ()
    (
        (evaluation_partial eq_shape (Shape Shape) () { |(a, b)| (a == b).then(|| ()) })
        (evaluation_partial ne_shape (Shape Shape) () { |(a, b)| (a != b).then(|| ()) })
        (evaluation_partial lt_shape (Shape Shape) () { |(a, b)| (false
            || (a.lanes_mult == b.lanes_mult && a.lanes_base < b.lanes_base)
            || (a.lanes_mult.is_none() && b.lanes_mult.is_some() && a.lanes_base < b.lanes_base)
        ).then(|| ())})
        (evaluation_partial eq_usize (usize usize) () { |(a, b)| (a == b).then(|| ()) })
        (evaluation_partial ne_usize (usize usize) () { |(a, b)| (a != b).then(|| ()) })
        (evaluation_partial ne_string (String String) () { |(a, b)| (a != b).then(|| ()) })
        (evaluation_partial lt_string (String String) () { |(a, b)| (a < b).then(|| ()) })
        (evaluation_partial ult_usize (usize usize) () { |(a, b)| (a < b).then(|| ()) })
        (evaluation_partial ule_usize (usize usize) () { |(a, b)| (a <= b).then(|| ()) })
        (evaluation_partial is_shape_scalar (Shape) () {
            |(shape,)| (shape == Shape::new_scalar()).then(|| ())
        })

        (evaluation bv_all_ones (usize) String { |(w,)| {
            assert!(w < 128);
            ((1u128 << w) - 1).to_string()
        }})

        // Scalar to self, broadcast to source
        // Merge behavior: if two replications are equal - their bases are equal too
        (function as_scalar (Value) Value :merge union)

        (relation neq (Value Value))

        (evaluation usize_min (usize usize) usize { |(a, b)| std::cmp::min(a, b) })
        (evaluation usize_max (usize usize) usize { |(a, b)| std::cmp::max(a, b) })
        (evaluation usize_add (usize usize) usize { |(a, b)| a.wrapping_add(b) })
        (evaluation usize_sub (usize usize) usize { |(a, b)| a.wrapping_sub(b) })
        (function generation_cost (Value) usize :merge usize_min)
    )
    (
        (set_ruleset_active "enrich")

        // Populate `as_scalar`
        (rule
            (query _ (is_shape_scalar (shape_of val)))
            (set val (as_scalar val))
        )
        (rule
            (query val (sel0 (constant _ o v)))
            (add c (sel0 (constant {scalar} o v)))
            (set c (as_scalar val))
        )
        (rule
            (query val (sel0 (stmt_p _ _ {s_broadcast} {s_} (in1 base))))
            (set base (as_scalar val))
        )
        (rule
            (query val (sel0 (op_g_0 h o s (in1 a_))))
            (query a (as_scalar a_))
            (add val_op (sel0 (op_g_0 {scalar} o s (in1 a))))
            (set val (sel0 (stmt_p h (out1 o) {s_broadcast} {s_} (in1 val_op))))
        )
        (rule
            (query val (sel0 (op_g_0 h o s (in2 a_ b_))))
            (query a (as_scalar a_))
            (query b (as_scalar b_))
            (add val_op (sel0 (op_g_0 {scalar} o s (in2 a b))))
            (set val (sel0 (stmt_p h (out1 o) {s_broadcast} {s_} (in1 val_op))))
        )

        // Simplify constant broadcast
        (rule
            (query st (stmt_p h (out1 o) {s_broadcast} {s_} (in1 base)))
            (query base (sel0 (stmt_p {scalar} (out1 o) {s_const} val (in0))))
            (set st (stmt_p h (out1 o) {s_const} val (in0)))
        )
    )
);
