# Floating-point operations

All standard floating-point operations are inherited from the floating-point
operation from the lira/arch module.

Below is an implementation of a floating-point operation in
[python](../python/lira/arch.py):

```python3
@dataclass
class FloatOperation(Operation):
    """Floating-point operation used by `fop` statements.

    Unlike `Operation` it is not a pure function:
        * it reads the FPU controls and
        * accumulates exception flags in the FPU state
    """
```

Unlike a standard [operation](ir_ops.md), a floating-point operation is not a
pure function: it reads the FPU controls (rounding mode, flush-to-zero and
default NaN) and ORs exception flags into the FPU state.

# Types

Floating-point operands are bit-vector (BV) values of the IEEE 754 binary
interchange formats: `BV<16>` (binary16), `BV<32>` (binary32) and `BV<64>`
(binary64).

Additional operand types:

* `BV<3>` - rounding mode (see [Rounding mode](#rounding-mode));
* `BV<8>` - fixed-point `fbits` operand of the integer conversions;
* `BV<2>` - comparison result (see [Comparison](#comparison)).

# Name Conventions

Float operations are grouped by operand signature.
The `name` field follows the specific pattern.

## Unary

`BV<n> BV<3> -> BV<n>` - `<semantic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `fsqrt`   | square root |
| `frint`   | round to integral using the rounding mode |
| `frintx`  | round to integral and signal inexact |

## Binary

`BV<n> BV<n> BV<3> -> BV<n>` - `<semantic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `fadd`    | addition |
| `fsub`    | subtraction |
| `fmul`    | multiplication |
| `fdiv`    | division |

## Ternary

`BV<n> BV<n> BV<n> BV<3> -> BV<n>` - `<semantic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `fmuladd` | fused multiply-add: `addend + a * b` with a single rounding |

## Min/Max

`BV<n> BV<n> -> BV<n>` - `<semantic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `fmax`    | maximum; NaNs propagate |
| `fmin`    | minimum; NaNs propagate |
| `fmaxnm`  | IEEE maxNum: one quiet NaN loses |
| `fminnm`  | IEEE minNum: one quiet NaN loses |

## Comparison

`BV<n> BV<n> -> BV<2>` - `<semantic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `fcmpq`   | compare: `0` EQ, `1` LT, `2` GT, `3` unordered |
| `fcmps`   | compare and signal on every NaN: `0` EQ, `1` LT, `2` GT, `3` unordered |

## Cast

`BV<in> BV<3> -> BV<out>` - `<semantic_base>_<in>_to_<out>`

| Operation | Description |
|-----------|-------------|
| `fcvtf`   | float to float |

## Fixed-point conversions

`BV<in> BV<8> BV<3> -> BV<out>` - `<semantic_base>_<in>_to_<out>`

| Operation | Description |
|-----------|-------------|
| `ftosi`   | float to signed fixed-point with `fbits`; saturating |
| `ftoui`   | float to unsigned fixed-point with `fbits`; saturating |
| `sitof`   | signed fixed-point with `fbits` to float |
| `uitof`   | unsigned fixed-point with `fbits` to float |

# Rounding mode

The last input of the rounding operations selects the rounding mode:

| value | mode |
|-------|------|
| `0`   | RNE (ties to even) |
| `1`   | RTP (towards +inf) |
| `2`   | RTN (towards -inf) |
| `3`   | RTZ (towards zero) |
| `4`   | RNA (ties away from zero) |
| `5`   | ODD (round to odd, for `FCVTXN`) |
| `7`   | dynamic (taken from the FPU state) |

An explicit mode covers instructions that fix their own rounding, such as
AArch64 `FCVTZS` and `FRINTA`.

# Modifiers

A float operation can apply modifiers to its base. They are appended to the
name (`<base>_<N>[_to_<M>]_<modifier>...`, in the order below) and listed as
attributes `fpu.<modifier>`:

| modifier      | meaning |
|---------------|---------|
| `default_nan` | NaN results are the default NaN, as if the default-NaN control were set |
| `no_flags`    | no exception flags are raised |

For example, `fmuladd_32_default_nan_no_flags` with attributes
`[fpu.default_nan, fpu.no_flags]` is Arm's `FPMulAdd_ZA`, which the SME outer
products use: the other controls (rounding mode, flush-to-zero) still apply.

# Derivatives

Some compound operations are derived from the standard set and need semantic
definitions in the LIRA architecture:

- architecture specific operations (`FRECPS`, `FJCVTZS`, `BFDotAdd`, ...) are
  intentionally **not** bases: a converter expresses them through snippets
  over the standard bases.

# `fop` statement

```
<shape> <out-width> <out> = fop <float-operation> <inputs...>
```

`fop` works lane by lane like `op`. The difference is that a float operation
is not a pure function:

* it reads the **FPU controls**: rounding mode, flush-to-zero and default NaN;
* it ORs **exception flags** into the FPU state.

Pure contexts, such as `Operation.semantic_func` snippets, therefore cannot
contain `fop`. `fop` composes with the vector statements: `scan` and `fold`
over a float operation fold lane by lane, left to right, each step reading the
controls and accumulating the flags, so the order of the lanes defines the
semantics.

Float operations are declared in `Arch.float_operations`. A float operation
has the same shape as an operation: `name`, `attributes`, `inputs`, `outputs`
and `semantic_base`. `semantic_base` names a standard base (see above) and is
`None` for architecture specific float operations, which a converter expresses
through snippets over the standard bases.

# FPU state

The FPU state is stored in architecture registers named by attributes:

* the control register has `fpu.control`, with fields `fpu.rmode@<lsb>+2`,
  `fpu.fz@<bit>`, `fpu.fz16@<bit>` and `fpu.dn@<bit>`;
* the status register has `fpu.status`, with flags `fpu.flag.<name>@<bit>`:
  `invalid`, `divbyzero`, `overflow`, `underflow`, `inexact` and
  `input_denormal`.

For example, in AArch64:

```yaml
- name: fpcr
  attributes: [fpu.control, fpu.rmode@22+2, fpu.fz@24, fpu.fz16@19, fpu.dn@25]
```
