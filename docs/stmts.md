# Statements

Semantic for standard statement kinds in pseudocode

This text assumes a general understanding of LIRA IR

## Environment

```python
# Vector of Bit Vectors
class Value:
    bit_width: int
    values: list[int]

# Constant
class Context:
    dyn_consts: dict[str, int]
    snippets: dict[str, StatementSeq]
    operations: dict[str, ContextOperation]
    environment_functions: dict[str, ContextEnvironmentFunction]
    float_operations: dict[str, _]
    ...

# Mutable
class State:
    pc: int
    set_pc: OnceInit[int]
    registers: dict[str, StateRegFile]
    system_registers: dict[str, StateSystemRegister]
    ... # e.g. Memory, FPU
class StateRegFile:
    size: int # Full size, shape.instantiate(dyn_consts)
    values: list[int]
    def read(self, idx: int, shape: int, ty: int) -> Value:
        assert self.size == shape * ty
        idx = idx % self.values.len()
        return reinterpret(self.values[idx], shape, ty)
    def write(self, idx: int, value: Value):
        assert self.size == value.shape * value.bit_width
        idx = idx % self.values.len()
        self.values[idx] = reinterpret(value, value.shape, value.bit_width)

class StmtExecCtx:
    shape: int
    specifier: str
    stmt_inputs: list[Value]
    stmt_outputs_types: list[int]
    snippet_inputs: list[Value]
    snippet_outputs: list[OnceInit[Value]]
    context: Context
    state: State

    def alloc_outputs(self) -> list[Value]:
        return [Value(ty, []) for ty in self.stmt_outputs_types]

def execute_statement_sequence(
    context: Context,
    state: State,
    stmts: StatementSeq,
    snippet_inputs: list[Value],
    snippet_outputs: list[OnceInit[Value]],
):
    values = {}
    for stmt in stmts:
        stmt_shape = stmt.shape.instantiate(context.dyn_consts)
        stmt_inputs = [values[name] for name in stmt.inputs]
        ctx = StmtExecCtx(
            stmt_shape,
            stmt.specifier,
            stmt_inputs,
            stmt.outputs_types,
            snippet_inputs,
            snippet_outputs,
            context,
            state,
        )
        stmt_outputs = (semantic(stmt.kind))(ctx)
        # Note: these two guarantees don't have to be checked in semantics
        #   Tbd: outline more checks
        assert all(shape(output) == stmt_shape for output in stmt_outputs)
        assert types(stmt_outputs) == stmt.outputs_types
        for name, value in zip(stmt.outputs, stmt_outputs):
            values.insert_new(name, value)
    assert all(output.initialized() for output in snippet_outputs)
```

Different execution contexts:
- `Context/State` are collections of interpretation-specific data.
- Statement kinds (including standard ones) can assume presence of specific data in `Context/State`.
- Not every `Context/State` should include everything, if statement kind requires data that is not available - this statement is invalid in the given context.
  - Example: `State` for execution of `Operation.semantic_func` must be empty (operation is a pure function by definition).
- Given `Context/State` definitions contain union of fields required by standard statements.

### Notation

- `Value(bit_width, lanes)` constructs a vector of `lanes` bit-vectors of `bit_width` bits each.
- `value[i]` is sugar for `value.values[i]`.
- `shape(value)` is sugar for `len(value.values)`.
- `types(values) -> list[int]` returns bit widths of the given values.
- `(a, b) = inputs` is used as an arity check: it panics if the number of inputs differs.
- `OnceInit[T]` is a single-assignment slot with `.set_first_time(value)` and `.initialized()`.
- `insert_new` assert key was not present
- `parse_int`: todo: should this be limited to positive decimal number?

## Semantics

TODO: grouping feels off

### Utils

#### Cond prefix

While the exact interpretation of `cond.` prefix varies between statement kinds, there's a general rule of input values interpretation.

```python
def cond_prefix_split(
    inputs: list[Value],
    output_types: list[int],
    shape: int,
) -> tuple[Value, list[Value], list[Value]]:
    cond = inputs[0]
    assert cond.bit_width == 1
    assert shape(cond) == shape
    on_false = inputs[1:][:len(output_types)]
    inputs = inputs[1:][len(output_types):]
    assert len(on_false) == len(output_types)
    assert all(shape(of) == shape for of in on_false)
    assert types(on_false) == output_types
    return cond, on_false, inputs
```

### General semantics

#### Input

```python
def semantic_input(ctx: StmtExecCtx) -> list[Value]:
    () = ctx.stmt_inputs
    input_id = parse_int(ctx.specifier)
    input_value = ctx.snippet_inputs[input_id]
    return [input_value]
```

#### Output

```python
def semantic_output(ctx: StmtExecCtx) -> list[Value]:
    assert ctx.shape == 1
    (value,) = ctx.stmt_inputs
    output_id = parse_int(ctx.specifier)
    ctx.snippet_outputs[output_id].set_first_time(value)
    return []
```

#### Const

```python
def semantic_const(ctx: StmtExecCtx) -> list[Value]:
    () = ctx.stmt_inputs
    (ty,) = ctx.stmt_outputs_types
    value = parse_int(ctx.specifier)
    return [Value(ty, [value] * ctx.shape)]
```

#### Dyn Const

```python
def semantic_dyn_const(ctx: StmtExecCtx) -> list[Value]:
    () = ctx.stmt_inputs
    (ty,) = ctx.stmt_outputs_types
    value = ctx.context.dyn_consts[ctx.specifier]
    return [Value(ty, [value] * ctx.shape)]
```

#### Snippet

```python
def semantic_snippet(ctx: StmtExecCtx) -> list[Value]:
    outputs = [OnceInit() for _ in ctx.stmt_outputs_types]
    execute_statement_sequence(
        ctx.context,
        ctx.state,
        ctx.context.snippets[ctx.specifier],
        ctx.stmt_inputs,
        outputs
    )
    return [output.value() for output in outputs]
```

#### Cond PC

TODO: should `read/write` be a part of statement kind?
- For consistency with registers

```python
def semantic_cond_pc(ctx: StmtExecCtx) -> list[Value]:
    assert ctx.shape == 1
    (cond, on_false, inputs) = cond_prefix_split(ctx.stmt_inputs, ctx.stmt_outputs_types, ctx.shape)
    if ctx.specifier == 'read':
        () = inputs
        if cond:
            return [ctx.state.read_pc()]
        else:
            return on_false
    elif ctx.specifier == 'write':
        (value,) = inputs
        if cond:
            ctx.state.write_pc(value)
        return []
    else:
        panic
```

#### Cond SysReg Read/Write

```python
def semantic_cond_sys_reg_read(ctx: StmtExecCtx) -> list[Value]:
    '''
    Implementation-defined
    similar to `cond.pc.read` get value of system register or return provided default
    '''
    (cond, on_false, inputs) = cond_prefix_split(ctx.stmt_inputs, ctx.stmt_outputs_types, ctx.shape)
    (sys_reg_id,) = inputs

def semantic_cond_sys_reg_write(ctx: StmtExecCtx) -> list[Value]:
    '''
    Implementation-defined
    similar to `cond.pc.write` set value of system register if cond
    '''
    (cond, on_false, inputs) = cond_prefix_split(ctx.stmt_inputs, ctx.stmt_outputs_types, ctx.shape)
    (sys_reg_id, value) = inputs
```

### Lane-wise semantics

TODO: it should be possible to outline smth like this
- Note: cond prefix is used the same way for lanewise semantics

```python
def execute_semantic_lanewise(
    ctx: StmtExecCtx,
    semantic: Callable[[StmtExecCtx, list[Value]], list[Value]]
) -> list[Value]:
    assert all(shape(value) == ctx.shape for value in ctx.stmt_inputs)
    outputs = ctx.alloc_outputs()
    for lane in range(ctx.shape):
        stmt_inputs = [stmt_input[lane] for stmt_input in ctx.stmt_inputs]
        stmt_outputs = semantic(ctx, stmt_inputs)
        assert types(stmt_outputs) == ctx.stmt_outputs_types
        for j in range(len(outputs)):
            outputs[j].values.append(stmt_outputs[j])
    return outputs
```

#### Op

```python
def semantic_op(ctx: StmtExecCtx) -> list[Value]:
    inputs = ctx.stmt_inputs
    assert all(ctx.shape == shape(value) for value in inputs)
    op = ctx.context.operations[ctx.specifier]
    assert types(inputs) == op.inputs

    outputs = ctx.alloc_outputs()
    for lane in range(ctx.shape):
        result = op.eval([value[lane] for value in inputs])
        add_new_lane(outputs, result)
    return outputs
```

#### FOp

```python
def semantic_fop(ctx: StmtExecCtx) -> list[Value]:
    inputs = ctx.stmt_inputs
    assert all(ctx.shape == shape(value) for value in inputs)
    fop = ctx.context.float_operations[ctx.specifier]
    assert types(inputs) == fop.inputs

    outputs = ctx.alloc_outputs()
    for lane in range(ctx.shape):
        result = fop.eval(ctx.Context, ctx.State, [value[lane] for value in inputs])
        add_new_lane(outputs, result)
    return outputs
```

#### Env

```python
def semantic_env(ctx: StmtExecCtx) -> list[Value]:
    inputs = ctx.stmt_inputs
    assert all(ctx.shape == shape(value) for value in inputs)
    env = ctx.context.environment_functions[ctx.specifier]
    assert types(inputs) == env.inputs

    outputs = ctx.alloc_outputs()
    for lane in range(ctx.shape):
        result = env.eval(ctx.context, ctx.state, [value[lane] for value in inputs])
        add_new_lane(outputs, result)
    return outputs
```

#### Cond Env

```python
def semantic_cond_env(ctx: StmtExecCtx) -> list[Value]:
    (cond, on_false, inputs) = cond_prefix_split(ctx.stmt_inputs, ctx.stmt_outputs_types, ctx.shape)
    assert all(ctx.shape == shape(value) for value in inputs)
    env = ctx.context.environment_functions[ctx.specifier]
    assert types(inputs) == env.inputs

    outputs = ctx.alloc_outputs()
    for lane in range(ctx.shape):
        if cond[lane]:
            result = env.eval(ctx.context, ctx.state, [value[lane] for value in inputs])
        else:
            result = on_false[0][lane]
        add_new_lane(outputs, result)
    return outputs
```

#### Read

```python
def semantic_read(ctx: StmtExecCtx) -> list[Value]:
    inputs = ctx.stmt_inputs
    (rsi,) = inputs
    assert shape(rsi) == 1
    rf = ctx.state.registers[ctx.specifier]
    (ty,) = ctx.stmt_outputs_types
    result = rf.read(rsi[0], ctx.shape, ty)
    return [result]
```

#### Cond Read

```python
def semantic_cond_read(ctx: StmtExecCtx) -> list[Value]:
    (cond, on_false, inputs) = cond_prefix_split(ctx.stmt_inputs, ctx.stmt_outputs_types, ctx.shape)
    (rsi,) = inputs
    assert shape(rsi) == 1
    rf = ctx.state.registers[ctx.specifier]
    (ty,) = ctx.stmt_outputs_types
    result = rf.read(rsi[0], ctx.shape, ty)
    for lane in range(ctx.shape):
        if not cond[lane]:
            result.values[lane] = on_false[0][lane]
    return [result]
```

#### Write

```python
def semantic_write(ctx: StmtExecCtx) -> list[Value]:
    inputs = ctx.stmt_inputs
    (rsi, value) = inputs
    assert shape(rsi) == 1
    assert shape(value) == ctx.shape
    rf = ctx.state.registers[ctx.specifier]
    rf.write(rsi[0], value)
    return []
```

#### Cond Write

```python
def semantic_cond_write(ctx: StmtExecCtx) -> list[Value]:
    (cond, on_false, inputs) = cond_prefix_split(ctx.stmt_inputs, ctx.stmt_outputs_types, ctx.shape)
    (rsi, value) = inputs
    assert shape(rsi) == 1
    assert shape(value) == ctx.shape
    rf = ctx.state.registers[ctx.specifier]
    value_on_false = rf.read(rsi[0], ctx.shape, value.bit_width)
    for lane in range(ctx.shape):
        if not cond[lane]:
            value.values[lane] = value_on_false[lane]
    rf.write(rsi[0], value)
    return []
```

### Vector semantics

#### Replicate

```python
# TODO: rename into broadcast?
# Note: can be expressed as `gather(value, 0, _)`
def semantic_replicate(ctx: StmtExecCtx) -> list[Value]:
    inputs = ctx.stmt_inputs
    (value,) = inputs
    assert shape(value) == 1
    return [Value(value.bit_width, [value[0]] * ctx.shape)]
```

#### Index

```python
def semantic_index(ctx: StmtExecCtx) -> list[Value]:
    () = ctx.stmt_inputs
    (ty,) = ctx.stmt_outputs_types
    return [Value(ty, list(range(ctx.shape)))]
```

#### Extract First

```python
# Note: can be expressed as `gather(value, index, _)`
def semantic_extract_first(ctx: StmtExecCtx) -> list[Value]:
    (value,) = ctx.stmt_inputs
    assert shape(value) >= ctx.shape
    value.values = value.values[:ctx.shape]
    return [value]
```

#### Extend Zero

```python
# Note: can be expressed as `gather(value, index, 0)`
def semantic_extend_zero(ctx: StmtExecCtx) -> list[Value]:
    (value,) = ctx.stmt_inputs
    assert shape(value) <= ctx.shape
    value.values.extend_with(ctx.shape, 0)
    return [value]
```

#### Extend Ones

```python
# Note: can be expressed as `gather(value, index, 1)`
def semantic_extend_ones(ctx: StmtExecCtx) -> list[Value]:
    (value,) = ctx.stmt_inputs
    assert shape(value) <= ctx.shape
    # Note: this can be relaxed in future
    assert value.bit_width == 1
    value.values.extend_with(ctx.shape, 1)
    return [value]
```

#### Gather

```python
def semantic_gather(ctx: StmtExecCtx) -> list[Value]:
    (val, idx, on_false) = ctx.stmt_inputs
    # Note: val can have different shape
    assert shape(idx) == shape(on_false) == ctx.shape
    (ty,) = ctx.stmt_outputs_types
    result = []
    for lane in range(ctx.shape):
        if idx[lane] < shape(val):
            result.append(val[idx[lane]])
        else:
            result.append(on_false[lane])
    return [Value(ty, result)]
```

#### CVI

```python
# Note: reverse of gather
# Note: ideally should not be used: it's bad for both formal analysis and hardware implementation
# Name: Conditional Vector Insert (or cond value index)
def semantic_cvi(ctx: StmtExecCtx) -> list[Value]:
    (base, cond, value, index) = ctx.stmt_inputs
    assert shape(base) == ctx.shape
    assert shape(cond) == shape(value) == shape(index)
    for lane in range(shape(cond)):
        if cond[lane]:
            if index[lane] < shape(base):
                base[index[lane]] = value[lane]
    return [base]
```

#### Scan/Fold

```python
def semantic_scan(ctx):
    return semantic_scan_fold('scan', ctx)
def semantic_fold(ctx):
    return semantic_scan_fold('fold', ctx)
def semantic_scan_fold(kind: str, ctx: StmtExecCtx) -> list[Value]:
    op = ctx.context.operations[ctx.specifier]

    # First `width` inputs (at least one) are scalars
    width = 0
    while shape(ctx.stmt_inputs[width]) != 1:
        width += 1
    # All other inputs (at least one) have same non-scalar shape
    vec_shape = shape(ctx.stmt_inputs[width])
    for lane in range(width, len(ctx.stmt_inputs)):
        assert vec_shape == shape(ctx.stmt_inputs[lane])

    inputs_scalar, inputs_vector = ctx.stmt_inputs.split_at(width)

    # Initialize state with scalar inputs
    # For each lane of vector inputs
    #   Evaluate operation on state and new part of input
    #   Split result of operation into new state and new output
    state = inputs_scalar
    outputs = ctx.alloc_outputs()
    for lane in range(vec_shape):
        inputs_vector_part = [value[lane] for value in inputs_vector]
        inputs_current = list(chain(state, inputs_vector_part))
        values = op.eval(inputs_current)
        new_state, new_outputs = values.split_at(width)
        state = new_state
        for i in range(len(outputs)):
            outputs[i].values.append(new_outputs[i])

    # Note: joining these two requires one statement to produce values with different shape.
    #   At the moment of writing this is not supported for the sake of simplicity,
    #   since it was never needed in practice.
    #   (Note: same with shape - there was no need in making it multidimensional)
    if kind == 'scan':
        # Note: final state is ignored
        return outputs
    if kind == 'fold':
        # Note: outputs are ignored. Normally, for `fold` there should be 0 of them
        return state
```

#### Suggestions

##### Cast/Reinterpret

##### Concat
