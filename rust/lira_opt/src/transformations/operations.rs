use dateg::execute;

use crate::Theory;

impl Theory {
    pub(super) fn add_rules_transformations_operations(&mut self, max_generation_cost: usize) {
        crate::get_!(self
            constant op_g_0 sel0
            in1 in2 in3
            bv_all_ones
            eq_usize type_of ult_usize
            generation_cost usize_max usize_add
        );

        // --- Commutativity ---
        for op in [
            "add",
            "and",
            "orr",
            "xor",
            "mul",
            "eq",
            "ne",
            "add_s_overflow",
            "add_u_overflow",
        ] {
            execute! {self;
                (rewrite (op_g_0 h o {#op.into()} (in2 a b)) (op_g_0 h o {#op.into()} (in2 b a)))
            };
        }

        // --- Associativity ---
        for op in ["add", "and", "orr", "xor", "mul"] {
            execute! {self;
                (rule
                    (query bc (sel0 (op_g_0 h o {#op.into()} (in2 b c))))
                    (query abc (op_g_0 h o {#op.into()} (in2 a bc)))
                    (add ab (sel0 (op_g_0 h o {#op.into()} (in2 a b))))
                    (set abc (op_g_0 h o {#op.into()} (in2 ab c)))
                    // Prevent infinite explosion via creating new e-classes
                    (query cost (usize_max (generation_cost a) (generation_cost b)))
                    (query _ (ult_usize cost {#max_generation_cost}))
                    (add cost_ab (usize_add cost 1))
                    (set cost_ab (generation_cost ab))
                )
                (rule
                    (query ab (sel0 (op_g_0 h o {#op.into()} (in2 a b))))
                    (query abc (op_g_0 h o {#op.into()} (in2 ab c)))
                    (add bc (sel0 (op_g_0 h o {#op.into()} (in2 b c))))
                    (set abc (op_g_0 h o {#op.into()} (in2 a bc)))
                    // Prevent infinite explosion via creating new e-classes
                    (query cost (usize_max (generation_cost b) (generation_cost c)))
                    (query _ (ult_usize cost {#max_generation_cost}))
                    (add cost_bc (usize_add cost 1))
                    (set cost_bc (generation_cost bc))
                )
            };
        }
        // concat
        execute! {self;
            (rule
                (query bc (sel0 (op_g_0 h o_bc "concat_hi_lo" (in2 b c))))
                (query abc (op_g_0 h o_abc "concat_hi_lo" (in2 a bc)))
                (query o_a (type_of a))
                (query o_b (type_of b))
                (add o_ab (usize_add o_a o_b))
                (add ab (sel0 (op_g_0 h o_ab "concat_hi_lo" (in2 a b))))
                (set abc (op_g_0 h o_abc "concat_hi_lo" (in2 ab c)))
                // Prevent infinite explosion via creating new e-classes
                (query cost (usize_max (generation_cost a) (generation_cost b)))
                (query _ (ult_usize cost {#max_generation_cost}))
                (add cost_ab (usize_add cost 1))
                (set cost_ab (generation_cost ab))
            )
            (rule
                (query ab (sel0 (op_g_0 h o_ab "concat_hi_lo" (in2 a b))))
                (query abc (op_g_0 h o_abc "concat_hi_lo" (in2 ab c)))
                (query o_b (type_of b))
                (query o_c (type_of c))
                (add o_bc (usize_add o_b o_c))
                (add bc (sel0 (op_g_0 h o_bc "concat_hi_lo" (in2 b c))))
                (set abc (op_g_0 h o_abc "concat_hi_lo" (in2 a bc)))
                // Prevent infinite explosion via creating new e-classes
                (query cost (usize_max (generation_cost b) (generation_cost c)))
                (query _ (ult_usize cost {#max_generation_cost}))
                (add cost_bc (usize_add cost 1))
                (set cost_bc (generation_cost bc))
            )
        }

        // --- Identity: x op k = x ---
        for (op, k) in [
            ("add", "0"),
            ("sub", "0"),
            ("xor", "0"),
            ("orr", "0"),
            ("mul", "1"),
            ("lsl", "0"),
            ("lsr", "0"),
            ("asr", "0"),
            ("ror", "0"),
            ("rol", "0"),
        ] {
            execute! {self;
                (rewrite (sel0 (op_g_0 h o {#op.into()} (in2 a (sel0 (constant h o {#k.into()}))))) a)
            };
        }
        execute! {self;
            (rule
                (query val (sel0 (op_g_0 h o "and" (in2 a c))))
                (query c (sel0 (constant h o (bv_all_ones o))))
                (uni val a)
            )
        }
        // --- Annihilation: x op k = k' ---
        for op in ["mul", "and", "lsl", "lsr", "asr"] {
            execute! {self;
                (rewrite (op_g_0 h o {#op.into()} (in2 (sel0 (constant h o "0")) a)) (constant h o "0"))
            }
        }

        // --- Comparisons and overflow flags with self ---
        for (op, r) in [
            ("eq", "1"),
            ("ne", "0"),
            ("ult", "0"),
            ("ule", "1"),
            ("ugt", "0"),
            ("uge", "1"),
            ("slt", "0"),
            ("sle", "1"),
            ("sgt", "0"),
            ("sge", "1"),
            ("sub_s_overflow", "0"),
            ("sub_u_overflow", "0"),
        ] {
            execute! {self;
                (rewrite (op_g_0 h o {#op.into()} (in2 a a)) (constant h o {#r.into()}))
            };
        }

        // --- Width adjusting operations ---
        for op in ["extract_low", "extend_zero", "extend_sign"] {
            execute! {self;
                // No-op
                (rule
                    (query v (sel0 (op_g_0 h o {#op.into()} (in1 a))))
                    (query _ (eq_usize (type_of a) o))
                    (uni v a)
                )
                // Idempotent
                (rewrite (op_g_0 h o {#op.into()} (in1 (sel0 (op_g_0 h o {#op.into()} (in1 x)))))
                    (op_g_0 h o {#op.into()} (in1 x)))
            }
        }

        execute! {self;
            // --- sub as add+neg ---
            // sub(a,b) -> add(a, neg(b))
            (rule
                (query lhs (op_g_0 h o "sub" (in2 a b)))
                (query cost (generation_cost b))
                (add neg_b (sel0 (op_g_0 h o "neg" (in1 b))))
                (set lhs (op_g_0 h o "add" (in2 a neg_b)))
                // Prevent infinite explosion via creating new e-classes
                (query _ (ult_usize cost {#max_generation_cost}))
                (add cost_neg_b (usize_add cost 1))
                (set cost_neg_b (generation_cost neg_b))
            )
            // add(a, neg(b)) -> sub(a,b)
            (rewrite
                (op_g_0 h o "add" (in2 a (sel0 (op_g_0 h o "neg" (in1 b)))))
                (op_g_0 h o "sub" (in2 a b)))
            (rewrite (sel0 (op_g_0 h o "neg" (in1 (sel0 (op_g_0 h o "neg" (in1 a)))))) a)
            (rewrite (op_g_0 h o "neg" (in1 (sel0 (constant h o "0")))) (constant h o "0"))
            (rewrite (op_g_0 h o "add" (in2 a (sel0 (op_g_0 h o "neg" (in1 a))))) (constant h o "0"))
            (rewrite (op_g_0 h o "neg" (in1 a)) (op_g_0 h o "sub" (in2 (sel0 (constant h o "0")) a)))

            // --- Annihilation ---
            (rewrite (op_g_0 h o "sub" (in2 a a)) (constant h o "0"))
            (rewrite (op_g_0 h o "xor" (in2 a a)) (constant h o "0"))

            // --- Idempotence ---
            (rewrite (sel0 (op_g_0 h o "and" (in2 a a))) a)
            (rewrite (sel0 (op_g_0 h o "orr" (in2 a a))) a)

            // --- Overflow with zero: cannot overflow ---
            (rewrite (op_g_0 h o "add_s_overflow" (in2 a (sel0 (constant h o "0")))) (constant h o "0"))
            (rewrite (op_g_0 h o "add_u_overflow" (in2 a (sel0 (constant h o "0")))) (constant h o "0"))
            (rewrite (op_g_0 h o "sub_s_overflow" (in2 a (sel0 (constant h o "0")))) (constant h o "0"))
            (rewrite (op_g_0 h o "sub_u_overflow" (in2 a (sel0 (constant h o "0")))) (constant h o "0"))

            // --- Inverse (xor) ---
            (rewrite (sel0 (op_g_0 h o "xor" (in2 a (sel0 (op_g_0 h o "xor" (in2 a b)))))) b)

            // --- Absorption (and / orr lattice) ---
            (rewrite (sel0 (op_g_0 h o "orr" (in2 (sel0 (op_g_0 h o "and" (in2 a b))) a))) a)
            (rewrite (sel0 (op_g_0 h o "and" (in2 (sel0 (op_g_0 h o "orr" (in2 a b))) a))) a)
            (rewrite (sel0 (op_g_0 h o "orr" (in2 (sel0 (op_g_0 h o "and" (in2 a b))) b))) b)
            (rewrite (sel0 (op_g_0 h o "and" (in2 (sel0 (op_g_0 h o "orr" (in2 a b))) b))) b)

            // --- Complement (not) ---
            (rewrite (sel0 (op_g_0 h o "not" (in1 (sel0 (op_g_0 h o "not" (in1 a)))))) a)
            (rewrite (op_g_0 h o "and" (in2 a (sel0 (op_g_0 h o "not" (in1 a)))))
                (constant h o "0"))
            (rewrite (op_g_0 h o "orr" (in2 a (sel0 (op_g_0 h o "not" (in1 a)))))
                (constant h o (bv_all_ones o)))
            (rewrite (op_g_0 h o "xor" (in2 a (sel0 (op_g_0 h o "not" (in1 a)))))
                (constant h o (bv_all_ones o)))

            // --- Strength reduction ---
            (rewrite (op_g_0 h o "mul"   (in2 a (sel0 (constant h o "2")))) (op_g_0 h o "add" (in2 a a)))
            (rewrite (op_g_0 h o "div_u" (in3 a (sel0 (constant h o "2")) (sel0 (constant h o "0"))))
                (op_g_0 h o "lsr" (in2 a (sel0 (constant h o "1")))))
            (rewrite (op_g_0 h o "rem_u" (in2 a (sel0 (constant h o "2"))))
                (op_g_0 h o "and" (in2 a (sel0 (constant h o "1")))))

            // Expensive...
            // // --- Width-1 collapses ---
            // (birewrite (op_g_0 h 1 "add" (in2 a b)) (op_g_0 h 1 "xor" (in2 a b)))
            // (birewrite (op_g_0 h 1 "sub" (in2 a b)) (op_g_0 h 1 "xor" (in2 a b)))
            // (birewrite (op_g_0 h 1 "and" (in2 a b)) (op_g_0 h 1 "mul" (in2 a b)))
            // (rewrite (op_g_0 h 1 "xor" (in2 a b)) (op_g_0 h 1 "ne" (in2 a b)))
            // (rule
            //     (query v (op_g_0 h 1 "ne" (in2 a b)))
            //     (query _ (eq_usize 1 (type_of a)))
            //     (set v (op_g_0 h 1 "xor" (in2 a b)))
            // )

            // --- Select ---
            (rewrite (sel0 (op_g_0 h o "select" (in3 _ a a))) a)
            (rewrite (sel0 (op_g_0 h o "select" (in3 (sel0 (constant h 1 "1")) a _))) a)
            (rewrite (sel0 (op_g_0 h o "select" (in3 (sel0 (constant h 1 "0")) _ b))) b)

            // --- Insert/Extract ---
            // extract(_, 0) -> extract_low
            (rewrite (op_g_0 h o "extract" (in2 base (sel0 (constant h _ "0"))))
                (op_g_0 h o "extract_low" (in1 base)))
            // insert(_, value, 0) -> value
            (rule
                (query v (sel0 (op_g_0 h o "insert" (in3 base val (sel0 (constant h o "0"))))))
                (query _ (eq_usize (type_of val) o))
                (uni v val)
            )
            // orr_shifted(0, value, 0) -> value
            (rule
                (query v (sel0 (op_g_0 h o "orr_shifted" (in3 (sel0 (constant h o "0")) val (sel0 (constant h o "0"))))))
                (query _ (eq_usize (type_of val) o))
                (uni v val)
            )
            // orr_shifted(base, 0, _) -> base
            (rewrite (sel0 (op_g_0 h o "orr_shifted" (in3 base (sel0 (constant h _ "0")) _))) base)
        }

        // --- De Morgan ---
        for (op, op2) in [("and", "orr"), ("orr", "and")] {
            execute! {self;
                // not(op(a,b)) -> op2(not(a), not(b))
                (rule
                    (query lhs (op_g_0 h o "not" (in1 (sel0 (op_g_0 h o {#op.into()} (in2 a b))))))
                    (add na (sel0 (op_g_0 h o "not" (in1 a))))
                    (add nb (sel0 (op_g_0 h o "not" (in1 b))))
                    (set lhs (op_g_0 h o {#op2.into()} (in2 na nb)))
                    // Prevent infinite explosion via creating new e-classes
                    (query cost_a (generation_cost a))
                    (query cost_b (generation_cost b))
                    (query _ (ult_usize cost_a {#max_generation_cost}))
                    (query _ (ult_usize cost_b {#max_generation_cost}))
                    (add cost_na (usize_add cost_a 1))
                    (set cost_na (generation_cost na))
                    (add cost_nb (usize_add cost_b 1))
                    (set cost_nb (generation_cost nb))
                )
                // op2(not(a), not(b)) -> not(op(a,b))
                (rule
                    (query lhs (op_g_0 h o {#op2.into()}
                        (in2 (sel0 (op_g_0 h o "not" (in1 a)))
                             (sel0 (op_g_0 h o "not" (in1 b))))))
                    (add ab (sel0 (op_g_0 h o {#op.into()} (in2 a b))))
                    (set lhs (op_g_0 h o "not" (in1 ab)))
                    // Prevent infinite explosion via creating new e-classes
                    (query cost (usize_max (generation_cost a) (generation_cost b)))
                    (query _ (ult_usize cost {#max_generation_cost}))
                    (add cost_ab (usize_add cost 1))
                    (set cost_ab (generation_cost ab))
                )
            };
        }

        // --- Distributivity ---
        for (outer, inner) in [("add", "mul"), ("orr", "and"), ("and", "orr")] {
            execute! {self;
                // outer(inner(a,b), inner(a,c)) -> inner(a, outer(b,c))
                (rule
                    (query lhs (op_g_0 h o {#outer.into()}
                        (in2 (sel0 (op_g_0 h o {#inner.into()} (in2 a b)))
                             (sel0 (op_g_0 h o {#inner.into()} (in2 a c))))))
                    (add bc (sel0 (op_g_0 h o {#outer.into()} (in2 b c))))
                    (set lhs (op_g_0 h o {#inner.into()} (in2 a bc)))
                    // Prevent infinite explosion via creating new e-classes
                    (query cost (usize_max (generation_cost b) (generation_cost c)))
                    (query _ (ult_usize cost {#max_generation_cost}))
                    (add cost_bc (usize_add cost 1))
                    (set cost_bc (generation_cost bc))
                )
                // inner(a, outer(b,c)) -> outer(inner(a,b), inner(a,c))
                (rule
                    (query lhs (op_g_0 h o {#inner.into()}
                        (in2 a (sel0 (op_g_0 h o {#outer.into()} (in2 b c))))))

                    (add ab (sel0 (op_g_0 h o {#inner.into()} (in2 a b))))
                    (add ac (sel0 (op_g_0 h o {#inner.into()} (in2 a c))))
                    (set lhs (op_g_0 h o {#outer.into()} (in2 ab ac)))
                    // Prevent infinite explosion via creating new e-classes
                    (query cost_ab (usize_max (generation_cost a) (generation_cost b)))
                    (query cost_ac (usize_max (generation_cost a) (generation_cost c)))
                    (query _ (ult_usize cost_ab {#max_generation_cost}))
                    (query _ (ult_usize cost_ac {#max_generation_cost}))
                    (add cost_ab_plus (usize_add cost_ab 1))
                    (add cost_ac_plus (usize_add cost_ac 1))
                    (set cost_ab_plus (generation_cost ab))
                    (set cost_ac_plus (generation_cost ac))
                )
            };
        }
    }
}
