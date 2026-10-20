use std::collections::BTreeMap;

use dateg::{BaseValue, ContainerVec, TokenOpaque, TokenOpaqueMarker, theory};
use dateg_extractors::dag::{Extractor, index_dag};
use lira::Shape;

theory!(Lira(
    (sort Stmt)
    (sort State)
    (sort Value)
    (sort Inputs)
    (sort Outputs)

    (ty usize)
    (ty String)
    (ty Shape)

    (ty OutputsMany)
    (container InputsMany)
)(
    // Implicit state of environment
    (constructor initial () State)
    (constructor state_after (Stmt) State)

    // Output selector (lira statement returns tuple)
    (constructor sel (usize Stmt) Value)

    // Statement itself: (shape, output types, kind, specifier, inputs, state?)
    // Note: names are cut to avoid looking like register or memory read and write operations
    // Pure: does not depend on implicit state
    (constructor stmt_p (Shape Outputs String String Inputs) Stmt)
    // With read-only dependency on implicit state
    (constructor stmt_r (Shape Outputs String String Inputs State) Stmt)
    // Writes implicit state
    (constructor stmt_w (Shape Outputs String String Inputs State) Stmt)

    // Wrappers over containers
    (constructor out_many (OutputsMany) Outputs)
    (constructor in_many (InputsMany) Inputs)

    // Aliases

    // Usually there's a single output
    (constructor sel0 (Stmt) Value)

    // It's really inconvenient to work with a vector currently
    (constructor out0 () Outputs)
    (constructor out1 (usize) Outputs)
    (constructor out2 (usize usize) Outputs)
    (constructor out3 (usize usize usize) Outputs)
    (constructor in0 () Inputs)
    (constructor in1 (Value) Inputs)
    (constructor in2 (Value Value) Inputs)
    (constructor in3 (Value Value Value) Inputs)
    (constructor in4 (Value Value Value Value) Inputs)

    // Commonly used
    (constructor constant (Shape usize String) Stmt)
    (constructor op_g_0 (Shape usize String Inputs) Stmt)

    // Properties

    (function shape_of (Value) Shape)
    (function type_of (Value) usize)

    // Helper functions to work with vectors

    (evaluation out_many_len    (OutputsMany) usize { |(v,)| v.0.len() })
    (evaluation in_many_len     (InputsMany) usize  { |(v,)| v.0.len() })
    (evaluation_partial out_many_get (OutputsMany usize) usize { |(v, idx)| v.0.get(idx).copied() })
    (evaluation_partial in_many_get  (InputsMany usize) Value  { |(v, idx)| v.0.get(idx).copied() })
    (evaluation vec0i ()                        InputsMany { |()| im(vec![]) })
    (evaluation vec1i (Value)                   InputsMany { |(a,)| im(vec![a]) })
    (evaluation vec2i (Value Value)             InputsMany { |(a, b)| im(vec![a, b]) })
    (evaluation vec3i (Value Value Value)       InputsMany { |(a, b, c)| im(vec![a, b, c]) })
    (evaluation vec4i (Value Value Value Value) InputsMany { |(a, b, c, d)| im(vec![a, b, c, d]) })
    (evaluation vec0o ()                    OutputsMany { |()| om(vec![]) })
    (evaluation vec1o (usize)               OutputsMany { |(a,)| om(vec![a]) })
    (evaluation vec2o (usize usize)         OutputsMany { |(a, b)| om(vec![a, b]) })
    (evaluation vec3o (usize usize usize)   OutputsMany { |(a, b, c)| om(vec![a, b, c]) })

    // Constants

    (val scalar (Shape) { Shape::new_scalar() })

    (val s_                     (String) {"_".into()})
    (val s_input                (String) {"input".into()})
    (val s_output               (String) {"output".into()})
    (val s_const                (String) {"const".into()})
    (val s_dyn_const            (String) {"dyn_const".into()})
    (val s_snippet              (String) {"snippet".into()})
    (val s_cond_pc_read         (String) {"cond.pc.read".into()})
    (val s_cond_pc_write        (String) {"cond.pc.write".into()})
    (val s_cond_sys_reg_read    (String) {"cond.sys_reg.read".into()})
    (val s_cond_sys_reg_write   (String) {"cond.sys_reg.write".into()})
    (val s_op                   (String) {"op".into()})
    (val s_fop                  (String) {"fop".into()})
    (val s_env                  (String) {"env".into()})
    (val s_cond_env             (String) {"cond.env".into()})
    (val s_read                 (String) {"read".into()})
    (val s_cond_read            (String) {"cond.read".into()})
    (val s_write                (String) {"write".into()})
    (val s_cond_write           (String) {"cond.write".into()})
    (val s_broadcast            (String) {"broadcast".into()})
    (val s_index                (String) {"index".into()})
    (val s_gather               (String) {"gather".into()})
    (val s_extract_first        (String) {"extract_first".into()})
    (val s_extend_zero          (String) {"extend_zero".into()})
    (val s_extend_ones          (String) {"extend_ones".into()})
    (val s_cvi                  (String) {"cvi".into()})
)(
    // Add value to table to query it later
    (add __state_initial (initial))

    (set_ruleset_active "enrich")

    (birewrite (sel 0 s) (sel0 s))

    (rule (query o (out_many v)) (query 0 (out_many_len v))
        (set o (out0))
    )
    (rule (query o (out_many v)) (query 1 (out_many_len v))
        (query o0 (out_many_get v 0))
        (set o (out1 o0))
    )
    (rule (query o (out_many v)) (query 2 (out_many_len v))
        (query o0 (out_many_get v 0))
        (query o1 (out_many_get v 1))
        (set o (out2 o0 o1))
    )
    (rule (query o (out_many v)) (query 3 (out_many_len v))
        (query o0 (out_many_get v 0))
        (query o1 (out_many_get v 1))
        (query o2 (out_many_get v 2))
        (set o (out3 o0 o1 o2))
    )
    (rule (query i (in_many v)) (query 0 (in_many_len v))
        (set i (in0))
    )
    (rule (query i (in_many v)) (query 1 (in_many_len v))
        (query i0 (in_many_get v 0))
        (set i (in1 i0))
    )
    (rule (query i (in_many v)) (query 2 (in_many_len v))
        (query i0 (in_many_get v 0))
        (query i1 (in_many_get v 1))
        (set i (in2 i0 i1))
    )
    (rule (query i (in_many v)) (query 3 (in_many_len v))
        (query i0 (in_many_get v 0))
        (query i1 (in_many_get v 1))
        (query i2 (in_many_get v 2))
        (set i (in3 i0 i1 i2))
    )
    (rule (query i (in_many v)) (query 4 (in_many_len v))
        (query i0 (in_many_get v 0))
        (query i1 (in_many_get v 1))
        (query i2 (in_many_get v 2))
        (query i3 (in_many_get v 3))
        (set i (in4 i0 i1 i2 i3))
    )

    (rule (query i (in0))               (set i (in_many (vec0i))))
    (rule (query i (in1 i0))            (set i (in_many (vec1i i0))))
    (rule (query i (in2 i0 i1))         (set i (in_many (vec2i i0 i1))))
    (rule (query i (in3 i0 i1 i2))      (set i (in_many (vec3i i0 i1 i2))))
    (rule (query i (in4 i0 i1 i2 i3))   (set i (in_many (vec4i i0 i1 i2 i3))))
    (rule (query o (out0))          (set o (out_many (vec0o))))
    (rule (query o (out1 o0))       (set o (out_many (vec1o o0))))
    (rule (query o (out2 o0 o1))    (set o (out_many (vec2o o0 o1))))
    (rule (query o (out3 o0 o1 o2)) (set o (out_many (vec3o o0 o1 o2))))

    (rule (query val (sel _ (stmt_p h _ _ _ _))) (set h (shape_of val)))
    (rule (query val (sel _ (stmt_r h _ _ _ _ _))) (set h (shape_of val)))
    (rule (query val (sel _ (stmt_w h _ _ _ _ _))) (set h (shape_of val)))
    (rule (query val (sel n (stmt_p _ (out_many os) _ _ _)))
        (query ty (out_many_get os n)) (set ty (type_of val)))
    (rule (query val (sel n (stmt_r _ (out_many os) _ _ _ _)))
        (query ty (out_many_get os n)) (set ty (type_of val)))
    (rule (query val (sel n (stmt_w _ (out_many os) _ _ _ _)))
        (query ty (out_many_get os n)) (set ty (type_of val)))

    (birewrite (stmt_p h (out1 o) "const" v (in0)) (constant h o v))
    (birewrite (stmt_p h (out1 o) "op.g" op i) (op_g_0 h o op i))
));

index_dag!(Index
    stmt: EStmt (datatype Stmt
        StmtP (Shape Outputs String String Inputs)
        StmtR (Shape Outputs String String Inputs State)
        StmtW (Shape Outputs String String Inputs State)
            { |_, _| Some(1) } { |(_, _, _, _, _, implicit)| (implicit,) }
    )
    out: Out (datatype Outputs
        VOutputs (OutputsMany) { |_, _| Some(0) }
    )
    inputs: In (datatype Inputs
        VInputs (InputsMany) { |_, _| Some(0) }
    )
    state: EState (datatype State
        Initial ()  { |_, _| Some(0) }
        StateAfter (Stmt)  { |_, _| Some(0) }
    )
    value: EValue (datatype Value
        Select (usize Stmt)  { |_, _| Some(0) }
    )
    [InputsMany]
);

impl Lira {
    pub fn state_initial(&self) -> TokenOpaque<State> {
        self.row_get(self.initial, ()).unwrap()
    }

    pub fn extractor(&self, root: impl TokenOpaqueMarker) -> Extractor<Index> {
        Index::extractor(
            self,
            root,
            (self.stmt_p, self.stmt_r, self.stmt_w),
            self.out_many,
            self.in_many,
            (self.initial, self.state_after),
            self.sel,
        )
    }

    pub fn extract(&self, t: impl TokenOpaqueMarker) -> Index {
        self.extractor(t).extract(self, t)
    }

    /// Run bunch of simple rulesets: aliases, properties, etc
    pub fn enrich(&mut self) {
        while self.run_ruleset("enrich") {}
    }

    pub fn _dbg_tables(&self) {
        eprintln!();
        eprintln!("-- _dbg_tables --");
        macro_rules! table {
            ($table:ident) => {
                eprintln!("{}", stringify!($table));
                self.for_each_row(self.$table, |inputs, output| {
                    eprintln!("  {output:?} <- {inputs:?}");
                });
            };
        }
        table!(stmt_p);
        table!(stmt_r);
        table!(stmt_w);
        table!(out_many);
        table!(in_many);
        table!(initial);
        table!(state_after);
        table!(sel);
        eprintln!("Inputs");
        self._inner()
            .container_values()
            .for_each::<InputsMany>(|inputs, output| {
                eprintln!("  _{output:?} <- {:?}", inputs.0);
            });

        let mut strings = BTreeMap::new();
        macro_rules! collect_strings {
            ($table:ident) => {
                self.for_each_row(self.$table, |inputs, _| {
                    strings.insert(format!("{:?}", inputs.2), inputs.2);
                    strings.insert(format!("{:?}", inputs.3), inputs.3);
                });
            };
        }
        collect_strings!(stmt_p);
        collect_strings!(stmt_r);
        collect_strings!(stmt_w);
        eprintln!("Strings");
        for (k, v) in strings.iter() {
            eprintln!("  {k} {}", v.get(self))
        }

        macro_rules! print_ext {
            ($table:ident $($do_5:literal)?) => {
                eprintln!("{}", stringify!($table));
                self.for_each_row(self.$table, |inputs, output| {
                    eprint!("  {output:?} <- {} {:?} {} {} {:?}",
                        inputs.0.get(self),
                        inputs.1,
                        inputs.2.get(self),
                        inputs.3.get(self),
                        inputs.4,
                    );
                    $(if $do_5 {
                        eprint!(" {:?}", inputs.5);
                    })?
                    eprintln!();
                });
            };
        }
        print_ext!(stmt_p);
        print_ext!(stmt_r true);
        print_ext!(stmt_w true);
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct OutputsMany(pub Vec<usize>);
impl BaseValue for OutputsMany {}

pub type InputsMany = ContainerVec<Value>;

fn im(v: Vec<TokenOpaque<Value>>) -> InputsMany {
    ContainerVec(v)
}
fn om(v: Vec<usize>) -> OutputsMany {
    OutputsMany(v)
}
