use dateg::execute;

use crate::Theory;

impl Theory {
    pub(super) fn add_rules_transformations_vector(&mut self) {
        crate::get_!(self
            stmt_p sel0
            out1 in0 in1 in3
            shape_of lt_shape
        );

        execute! {self;
            // Gather(_, index, _)
            (rule
                (query index (sel0 (stmt_p h (out1 64) "index" "_" (in0))))
                (query val (sel0 (stmt_p h (out1 o) "gather" "_" (in3 value index _))))
                (query h (shape_of value))
                (uni val value)
            )
            (rule
                (query index (sel0 (stmt_p h (out1 64) "index" "_" (in0))))
                (query val (sel0 (stmt_p h (out1 o) "gather" "_" (in3 value index _))))
                (query h_ (shape_of value))
                (query _ (lt_shape h h_))
                (set val (sel0 (stmt_p h (out1 o) "extract_first" "_" (in1 value))))
            )
        }

        //  idempotence
        for kind in ["extract_first", "extend_zero"] {
            execute! {self;
                (rule
                    (query inter (sel0 (stmt_p _ (out1 o) {#kind.into()} "_" (in1 input))))
                    (query st (stmt_p h (out1 o) {#kind.into()} "_" (in1 inter)))
                    (set st (stmt_p h (out1 o) {#kind.into()} "_" (in1 input)))
                )
            }
        }
    }
}
