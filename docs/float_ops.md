# Floating-point operations (`fop`) and vector statements

Status: proposal. It completes the `fop` sketch and implements part of the
vector semantics from `docs/stmts.md` on the `docs` branch.

The Python library (`lira.arch.FloatOperation`, `lira.float_ops`,
`lira.ir_builder`) implements this, and `archs/aarch64` uses it.

## `fop` statement

```
<shape> <out-width> <out> = fop <float-operation> <inputs...>
```

`fop` works lane by lane like `op`. The difference is that a float operation
is not a pure function:

* it reads the **FPU controls**: rounding mode, flush-to-zero and default NaN;
* it ORs **exception flags** into the FPU state.

Pure contexts, such as `Operation.semantic_func` snippets, therefore cannot
contain `fop`.

Float operations are declared in `Arch.float_operations`, with the same shape
as operations: `name`, `attributes`, `inputs`, `outputs`, `semantic_base`.
The list is omitted from YAML when empty, so existing descriptions are
unchanged.

## Standard float operation bases

`N`/`M` are IEEE 754 binary16/32/64 widths (16, 32, 64). An operation is named
`<base>_<N>`; a conversion is named `<base>_<N>_to_<M>`.

| base | signature | meaning |
|---|---|---|
| `fadd`, `fsub`, `fmul`, `fdiv` | `N <- N N 3` | `a op b`, rounded |
| `fmuladd` | `N <- N N N 3` | `addend + a * b` with a single rounding |
| `fsqrt` | `N <- N 3` | square root |
| `fmax`, `fmin` | `N <- N N` | maximum/minimum; NaNs propagate |
| `fmaxnm`, `fminnm` | `N <- N N` | IEEE maxNum/minNum: one quiet NaN loses |
| `fcmpq`, `fcmps` | `2 <- N N` | compare: 0 EQ, 1 LT, 2 GT, 3 unordered; `fcmps` signals on every NaN |
| `frint`, `frintx` | `N <- N 3` | round to integral; `frintx` also signals inexact |
| `fcvtf` | `M <- N 3` | float to float |
| `ftosi`, `ftoui` | `M <- N 8 3` | float to (un)signed fixed-point with `fbits`; saturating |
| `sitof`, `uitof` | `M <- N 8 3` | (un)signed fixed-point with `fbits` to float |

The following bases are defined for the remaining Arm instructions. They are
in `lira/float_ops.py` but are not used by `archs/aarch64/aarch64.yaml` yet,
and they have not been checked on hardware:

| base | signature | meaning |
|---|---|---|
| `fmulx` | `N <- N N 3` | `fmul`, but `0 × ∞ = ±2` |
| `frecps`, `frsqrts` | `N <- N N 3` | Newton-Raphson steps `2 − a·b`, `(3 − a·b) / 2` (fused) |
| `frecpe`, `frsqrte`, `frecpx` | `N <- N` | reciprocal (square root) estimate, reciprocal exponent |
| `frint32`, `frint64` | `N <- N 3` | round to an integral value that fits in 32/64 bits, else most negative integer |
| `fjcvtzs` | `32 1 <- 64` | JavaScript conversion: modulo 2^32, flag = exact and in range |
| `fmuladdh` | `32 <- 32 16 16 3` | `addend + a * b` with half-precision factors, single rounding |
| `fcvtbf` | `16 <- 32 3` | single to BFloat16 |
| `bfdotadd` | `32 <- 32 16 16 16 16` | `acc + a0·b0 + a1·b1` on BFloat16 (Arm BFDotAdd) |

The last input of the rounding operations is a **rounding mode**:
0 RNE, 1 RTP (+∞), 2 RTN (−∞), 3 RTZ, 4 RNA (ties away), 5 ODD (round to odd,
for `FCVTXN`), and **7 = dynamic**
(taken from the FPU state). An explicit mode covers instructions that fix
their own rounding, such as AArch64 `FCVTZS` and `FRINTA`.

## FPU state

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

## Semantics

`lira/float_ops.py` is the executable reference: exact rational arithmetic
followed by a single rounding. It transliterates the Arm FP library:
FPUnpack, FPRound, FPProcessNaN(s), FPAdd, FPMulAdd, FPMax(Num), FPCompare,
FPConvert, FPToFixed, FixedToFP and FPRoundInt. The following Arm FPU model
rules are part of the standard semantics:

* **NaN propagation:** a signalling NaN beats a quiet NaN, then the first
  operand beats later ones. The result is quieted. With DN set it is the
  default NaN.
* **Flush-to-zero:** subnormal inputs flush to zero and set
  `input_denormal`; for half precision the flush sets no flag. Results that
  are tiny before rounding flush to zero and set `underflow` but not
  `inexact`. Half precision uses FZ16.
* **Underflow:** tininess is detected before rounding.
* **Conversions to integer** saturate: NaN becomes 0 and signals `invalid`.

Other FPU models, such as RISC-V's canonical NaN or tininess after rounding,
would add a model attribute. They are not defined yet.

The model was checked against an Apple M-series CPU on every AArch64 scalar
FP instruction. The checks used random FPCR modes and operands, including
special values.

## Vector statements

These are implemented by the Python builder
(`index`, `gather`, `replicate`, `extract_first`, `extend_zero_lanes`, `fold`)
and follow `docs/stmts.md` on the `docs` branch:

* **`read`/`write` with a shape** reinterpret a register as `lanes × width`
  bits, with lane 0 in the low bits.
* **`index`** produces `[0, 1, …, lanes−1]`.
* **`gather(value, index, default)`:** `out[i] = value[index[i]]` when the
  index is in range, otherwise `default[i]`. `value` may have a different
  shape.
* **`replicate`** broadcasts a shape-1 value; **`extract_first`** keeps the
  first lanes; **`extend_zero`** (the statement kind) appends zero lanes.
* **`fold op state... vectors...`** threads `state = op(state, lanes…)`
  through the lanes and returns the final state.
* **`env`/`cond_env`/`fop`** work lane by lane in order. For example, a
  shaped `mem_read` performs one access per lane.
