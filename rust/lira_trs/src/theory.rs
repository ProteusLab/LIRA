use dateg::{BaseValue, ContainerVec, TokenOpaque, TokenOpaqueMarker, theory};
use dateg_extractors::dag::index_dag;

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
    (constructor sel0 (Stmt) Value)

    (constructor out0 () Outputs)
    (constructor out1 (usize) Outputs)
    (constructor out2 (usize usize) Outputs)
    (constructor out3 (usize usize usize) Outputs)
    (constructor in0 () Inputs)
    (constructor in1 (Value) Inputs)
    (constructor in2 (Value Value) Inputs)
    (constructor in3 (Value Value Value) Inputs)
    (constructor in4 (Value Value Value Value) Inputs)

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

    (val c0 (usize) {0})
    (val c1 (usize) {1})
    (val c2 (usize) {2})
    (val c3 (usize) {3})
    (val c4 (usize) {4})

    (val scalar (Shape) { Shape(lira::Shape::new_scalar()) })

    (val s_op           (String) {"op".to_string()})
    (val s_env          (String) {"env".to_string()})
    (val s_read         (String) {"read".to_string()})
    (val s_write        (String) {"write".to_string()})
    (val s_cond_env     (String) {"cond_env".to_string()})
    (val s_cond_read    (String) {"cond_read".to_string()})
    (val s_cond_write   (String) {"cond_write".to_string()})
    (val s_input        (String) {"input".to_string()})
    (val s_output       (String) {"output".to_string()})
    (val s_const        (String) {"const".to_string()})
    (val s_index        (String) {"index".to_string()})
    (val s_gather       (String) {"gather".to_string()})
    (val s_replicate    (String) {"replicate".to_string()})
    (val s_dyn_const    (String) {"dyn_const".to_string()})
)(
    (add _state_initial (initial))
    (add _out0 (out0))
    (add _in0 (in0))

    // Standard representation keeps inputs and outputs in an arbitrarily sized vector.
    // Actual rewrites will use only fixed sizes, which are way simpler to work with.
    // These rulesets convert between these two representations.
    (set_ruleset_active "factorize vector arguments")
    (rule (query o (out_many v)) (query {c0} (out_many_len v))
        (set o (out0))
    )
    (rule (query o (out_many v)) (query {c1} (out_many_len v))
        (query o0 (out_many_get v {c0}))
        (set o (out1 o0))
    )
    (rule (query o (out_many v)) (query {c2} (out_many_len v))
        (query o0 (out_many_get v {c0}))
        (query o1 (out_many_get v {c1}))
        (set o (out2 o0 o1))
    )
    (rule (query o (out_many v)) (query {c3} (out_many_len v))
        (query o0 (out_many_get v {c0}))
        (query o1 (out_many_get v {c1}))
        (query o2 (out_many_get v {c2}))
        (set o (out3 o0 o1 o2))
    )
    (rule (query i (in_many v)) (query {c0} (in_many_len v))
        (set i (in0))
    )
    (rule (query i (in_many v)) (query {c1} (in_many_len v))
        (query i0 (in_many_get v {c0}))
        (set i (in1 i0))
    )
    (rule (query i (in_many v)) (query {c2} (in_many_len v))
        (query i0 (in_many_get v {c0}))
        (query i1 (in_many_get v {c1}))
        (set i (in2 i0 i1))
    )
    (rule (query i (in_many v)) (query {c3} (in_many_len v))
        (query i0 (in_many_get v {c0}))
        (query i1 (in_many_get v {c1}))
        (query i2 (in_many_get v {c2}))
        (set i (in3 i0 i1 i2))
    )
    (rule (query i (in_many v)) (query {c4} (in_many_len v))
        (query i0 (in_many_get v {c0}))
        (query i1 (in_many_get v {c1}))
        (query i2 (in_many_get v {c2}))
        (query i3 (in_many_get v {c3}))
        (set i (in4 i0 i1 i2 i3))
    )
    (set_ruleset_active "de factorize vector arguments")
    (rule (query i (in0))               (set i (in_many (vec0i))))
    (rule (query i (in1 i0))            (set i (in_many (vec1i i0))))
    (rule (query i (in2 i0 i1))         (set i (in_many (vec2i i0 i1))))
    (rule (query i (in3 i0 i1 i2))      (set i (in_many (vec3i i0 i1 i2))))
    (rule (query i (in4 i0 i1 i2 i3))   (set i (in_many (vec4i i0 i1 i2 i3))))
    (rule (query o (out0))          (set o (out_many (vec0o))))
    (rule (query o (out1 o0))       (set o (out_many (vec1o o0))))
    (rule (query o (out2 o0 o1))    (set o (out_many (vec2o o0 o1))))
    (rule (query o (out3 o0 o1 o2)) (set o (out_many (vec3o o0 o1 o2))))

    // Usually there's a single output
    (set_ruleset_active "aliases convert")
    (birewrite (sel {c0} s) (sel0 s))
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

    pub fn extract(&self, t: impl TokenOpaqueMarker) -> Index {
        Index::extract(
            self,
            t,
            (self.stmt_p, self.stmt_r, self.stmt_w),
            self.out_many,
            self.in_many,
            (self.initial, self.state_after),
            self.sel,
        )
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
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Shape(pub lira::Shape);
impl BaseValue for Shape {}

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
