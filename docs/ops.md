# Operations

List of standard operation bases, their signature and semantic.

Arithmetic: `add`, `sub`, `mul`, `neg`, `div_s`, `div_u`, `rem_s`, `rem_u`

Comparators: `eq`, `ne`, `ugt`, `uge`, `ult`, `ule`, `sgt`, `sge`, `slt`, `sle`

Overflow: `add_s_overflow`, `add_u_overflow`, `sub_s_overflow`, `sub_u_overflow`

Bitwise: `and`, `orr`, `xor`, `not`

Shifts: `lsl`, `lsr`, `asr`

Others:
- `clz`, `ctz`, `cnt`, `rev`, `rol`, `ror`
- `extend_zero`, `extend_sign`, `extract_low`
- `insert`, `extract`, `orr_shifted`
- `concat_hi_lo`
- `select`

## Signature

Basic operation is parametrized by a list of variables, they can have positive integer value.
Suggested way to name concrete operations is to use `<base> <"_" param value>*` name e.g. `add_18`

Signature is written in a form `<const/variable>+ "<-" <const/variable>+`, e.g. `1 <- n n`.

Some operations also have constraint on allowed values, e.g. `n <- m with n <= m`.

Note, that this way directly translates in a following way to define and constraint operation:
```python
interface BasicOperation:
    params_num: int
    # Note: these have to be constants (no arbitrary-number inputs)
    outputs_num: int
    inputs_num: int
    # Usually not needed
    def check_constraint(params: list[int]) -> bool:
        return True
    # Note: this should be a total function, which correctness is guaranteed on a valid inputs
    # Note: `list[ty; len]` notation is used to write a type `list with len elements`
    def parse(outputs: list[int], inputs: list[int]) -> list[int; self.params_num]:
    # Translate params to the signature
    def signature(params: list[int]) -> tuple[list[int], list[int]]:

# This is enough to implement
def is_signature_valid(base: BasicOperation, outputs: list[int], inputs: list[int]) -> bool:
    params = base.parse(outputs, inputs)
    expected = base.signature(params)
    return expected == (outputs, inputs) and base.check_constraint(params)
```
Usually, defining this set of functions is way more concise, than explicitly validating concrete signature.
The form to present signature, specified above, is trivially convertible to implementation of this interface.

### Signatures

Unary: `n <- n`:
- `neg`, `not`, `clz`, `ctz`, `cnt`, `rev`

Binary: `n <- n n`:
- `add`, `sub`, `mul`, `rem_s`, `rem_u`
- `and`, `orr`, `xor`
- `lsl`, `lsr`, `asr`
- `ror`, `rol`

Ternary: `n <- n n n`:
- `div_s`, `div_u`

Cmp: `1 <- n n`:
- `eq`, `ne`, `ugt`, `uge`, `ult`, `ule`, `sgt`, `sge`, `slt`, `sle`
- `add_s_overflow`, `add_u_overflow`, `sub_s_overflow`, `sub_u_overflow`

Select: `n <- 1 n n`
- `select`

Constrained:
- `n <- m with n <= m`: `extract_low`
- `n <- m with n >= m`: `extend_zero`, `extend_sign`
- `n <- n m n with m <= n`: `insert`, `orr_shifted`
- `n <- m m with n <= m`: `extract`
- `n <- m l with n = m + l`: `concat_hi_lo`

Note: in some cases (`xor_1` with `1 <- n n`) concrete operation can be parsed with different signatures, code should not rely on the opposite

## Semantic

Semantic is explicitly written in cases there different interpretations are widely used.

It's based on integer representation. Conversion between bit vectors and integers assumes standard two's complement representation:
- `bv2s`: bit vector as signed integer
- `bv2u`: bit vector as unsigned integer
- `i2bv`: integer to bit vector

Conventions:
- `bv2i` is used in case signedness of conversion doesn't matter
- `*` is used in place there exact number doesn't influence the result
- final `i2bv` is omitted
  - bool is treated as a bit vector of length one


Example: `add(a, b) = bv2i(a) + bv2i(b)`, here `a` and `b` have types `BV<n>`, result of expression is `int`, but it's assumed to be converted with `i2bv` back to bit vector. Note, that this is a standard wrapping behavior definition.

Arithmetic:
- `div_s(a, b, d) = if b != 0 then bv2s(a) / bv2s(b) else d`
  - `div_u` is the same with `bv2u`
  - Note: this provides `div_s(INT_MIN, -1, *) = INT_MIN`
- `rem_s(a, b) = a - b * div_s(a, b, *)`
  - `rem_u` is the same with `bv2u`
  - Note: this provides normal behavior of remainder, except `rem(a, 0) = a`

Comparators:
- `eq`, `ne`: equal and not equal
- `<signedness><greater/less><than/than or equal>`, e.g `uge`: unsigned greater than or equal: `>=`

Overflow:
- `add_s_overflow(a, b) = (bv2s(a) + bv2s(b)) != bv2s(i2bv(bv2s(a) + bv2s(b)))`
  - i.e. if limitation of finite bit vector representation cause wrong result
  - same for others with signedness and operation set correspondingly

Shifts:
- `lsl(a, b) = bv2u(a) * 2**bv2u(b)`
  - Note: this provides `lsl(a, huge number) = 0`
- `lsr(a, b) = bv2u(a) / 2**bv2u(b)`
  - Note: this provides `lsr(a, huge number) = 0`
- `asr(a, b) = bv2s(a) / 2**bv2u(b)`
  - Note: this provides `asr(a, huge number) = replicate sign bit`
  - Note: `b` is treated as unsigned

Others:
- `clz`, `ctz`: count leading/trailing zeroes
- `cnt`: count ones
- `rev`: reverse bits
- `extend_zero(a) = i2bv(bv2u(a))`
- `extend_sign(a) = i2bv(bv2s(a))`
- `extract_low(a) = i2bv(bv2u(a))`
  - Note: the formula looks the same as `extend_zero`, the difference lies in type constraint
- `select(cond, a, b) = if bv2bool(cond) then a else b`

Others: complex: are standard, but have to be defined (have `semantic_func`):
- `rol<N>(a, b) = lsl(a, b%N) | lsr(a, N - b%N)`
  - same for `ror` with `lsl` and `lsr` swapped
- `concat_hi_lo<_, _, L>(a, b) = bv2u(a) * 2**L + bv2u(b)`
- `extract(val, lsb) = extract_low(lsr(val, lsb))`
  - Note: standard extraction of several bits from a bigger bit vector from a given offset
- `orr_shifted(base, val, lsb) = orr(base, lsl(extend_zero(val), lsb))`
  - Note: this is simplified `insert` created for encoding - it behaves the same way if `base` has 0 bits in the place of modification
- `insert<_, M>(base, val, lsb) = orr(and(base, (2**M - 1) * 2**lsb), lsl(extend_zero(val), lsb))`
  - Note: standard inserting of several bits into a bigger bit vector at a given offset
