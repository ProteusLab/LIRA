# LIRA IR

Linear Intermediate Representation for Architecture (instructions semantic) description and formal Analysis

## Motivation behind design decisions

Minimal set of concepts:
- may take some time to grasp ideas, but then learning full specification should be fast
- simple to convert to domain-specific representation

Single (parametric) type for values - vector of bitvectors
- scalar is a vector of shape 1
- length of vector is `base * (ctx.get(multiplier) or 1)`
- shape might become more-dimensional in future

No control flow - vector data types:
- better suited for formal analysis
- provides representation closer to actual hardware

Statement:
- is an action (defined by kind), that:
  - takes references to existing variables
    - and possibly opaque architecture state
  - returns (several) values
- is independent from other statements in the same sequence
  - except for (mostly) explicit dataflow, as noted above

Notes about statement:
- constants must be defined with special statement: separation of responsibilities - other statements do not need to handle both references and constant values
- there is a standard set of statements, but otherwise they can have any semantics
  - since they are independent, most algorithms can work even with unknown statements in a sequence
    - TODO: update language to match MLIR - it utilizes the same idea
- most statements are SIMD-like: they apply actions per lane independently
  - exceptions are statements specifically added to express non-SIMD instructions

## Standard statements

TODO: standalone description, currently it requires looking at `ir_std.*` to see fields and knowledge of generic structure of `Statement`

Pseudocode:
```
function execute(seq, ctx)
    values = {} # Used to pass values between statements
    for stmt in seq:
        Executor(stmt.kind).execute(stmt, values, ctx)
```

### Input

Kind: `input`

Specifier: id of context-defined input to bind to value

Semantic: binds "input value" from context

Pseudocode: `values[output] = ctx.input(id)`

### Output

Kind: `output`

Specifier: id with which to mark value

Semantic: marks value so context can retrieve it after execution

Pseudocode: `ctx.set_output(id, value)`

### Read

Kind: `read`

Specifier: name of `RegisterFile`

Semantic: read (full) register from specified `rf` by given index

Pseudocode: `values[output] = ctx.{rf}.read<shape>(rsi)`

### Write

Kind: `write`

Specifier: name of `RegisterFile`

Semantic: write value to (full) register from specified `rf` at given index

Pseudocode: `ctx.{rf}.write<shape>(rsi, value)`

### Operation

Kind: `op`

Specifier: name of `Operation`

Semantic: per lane evaluate operation on given inputs

Pseudocode: `values[output[.]] = [op(values[inputs[.]][i]) for i in shape]`

Pseudocode:
```
assert shape of all inputs and outputs is the same
assert inputs and outputs (types) match operation signature
for i in stmt.shape
    inputs = {}
    for j, input in stmt.args
        inputs[j] = values[input][i]
    r = op(inputs)
    for j, output_name in stmt.outputs
        values[output_name][i] = r[j]
```

### Environment Function Call

Kind: `env`

Specifier: name of `EnvironmentFunction`

Semantic: for each lane (in order) call environment function on given inputs

Pseudocode:
```
assert shape of all inputs and outputs is the same
assert inputs and outputs (types) match envirionment function signature
for i in stmt.shape
    inputs = {}
    for j, input in stmt.args
        inputs[j] = values[input][i]
    r = env(inputs)
    for j, output_name in stmt.outputs
        values[output_name][i] = r[j]
```

Note: usually it should be possible to process environments in parallel

### Conditional Environment Function Call

Kind: `cond_env`

Specifier: name of `EnvironmentFunction`

Semantic: for each lane (in order) conditionally call environment function on given inputs or return default value
- this is one of two key concepts to understand about LIRA:
  - there's no control flow, including conditional blocks, but there are (is, but can be more) statements, that have built-in conditional semantic
  - that's different, that's as good as it can be for formal analysis
  - this is still SSA form - even if condition isn't holding - output value is defined (no undefined behavior)

```
assert shape of all inputs and outputs is the same
assert inputs and outputs (types) match envirionment function signature
for i in stmt.shape
    inputs = {}
    for j, input in stmt.args
        inputs[j] = values[input][i]
    if cond[i]
        r = env(inputs)
    else
        r = on_false
    for j, output_name in stmt.outputs
        values[output_name][i] = r[j]
```

### Constant

Kind: `const`

Specifier: value (does not imply type by itself)

Semantic: create constant, implicitly replicates value

Pseudocode: `values[output] = [value for _ in shape]`

### Index

Kind: `index`

Specifier: unused, should be `_`

Semantic: create specific constant, necessary for sensible `Permutation`

Pseudocode: `values[output] = [i for i in shape]`
- produces constant `[0, 1, 2, ...]`

### Gather

Kind: `gather`

Specifier: unused, should be `_`

Pseudocode:
```
for i in stmt.shape
    if index[i] < value.shape
        r = value[index[i]]
    else
        r = default[i]
    values[output][i] = r
```

### Fold

### Scan

### Alias

Kind: `alias`

Specifier: snippet name

Semantic: executes given snippet

Pseudocode:
```
ctx_ = ctx.new(inputs=stmt.args)
ctx_.execute(ctx.snippet(stmt.semantic))
for i, output in stmt.outputs
    values[output] = ctx_.get_output(i)
```

## Standard Aliases

### Replicate

Gather with value-scalar, index-const0, default-dummy

### Reduce

Fold with assertion op is commutative-associative

### Dynamic Constant

Kind: `dyn_const`

Specifier: name of value to bind

Semantic: get value from context
- intendent usage: architecture-defined kinda dynamic part of architecture e.g. length of vector registers
- literal usage: can get arbitrary context-defined value e.g. base for instraction encoding

Pseudocode: `values[output] = ctx.get_dyn_const(name)`

Implementation: `fold(+, 1xV)`

## Extra statements
