# Set of standard operations

WIP

Note: in lira `BV1` is used instead of `Bool`

Note: mentioned `op_name` will be in the `Operation.semantic_base`

## Signatures

List of ops, grouped by signature

`BVn -> BVn`: `<op_name>_<n>`
- `not`
- `neg`
- `popcnt`
- `ctz`, `clz`
- `reverse` (bits)

`BVn BVn -> BVn`: `<op_name>_<n>`
- `add`, `sub`
- `and`, `orr`, `xor`
- `mul`
- `rem_u`, `rem_s`: `rem(a,0)=a`
- `lsl`, `lsr`, `asr`: on overflow: `shift(x,y+1)=shift_1(shift(x,y))`
- `ror`, `rol` (?)

`BVn BVn -> BV1`: `<op_name>_<n>`
- `eq`, `ne`
- `(u/s)(l/g)(t/e)` (`slt`, etc)
- `(add/sub)_(u/s)_overflow`
  - maybe also for `mul`?
  - maybe add saturating operations to std?

`BVn BVn BVn -> BVn`: `<op_name>_<n>`
- `div_u`, `div_s`: `div(a,b,c) = b != 0 ? a/b : c`
  - motivation for ternary: total definition - no UB

`BV1 BVn BVn -> BVn`: `<op_name>_<n>`
- `ite`/`select`

`BVin -> BVout`: `<op_name>_<out>_<in>` (order?)
- `extract_low`
- `extend_zero`, `extend_sign`

`BVin BVin -> BVout`: `<op_name>_<out>_<in>` (order?)
- `extract`: defined as: `extract(v,s) = extract_low(lsr(v,s))`

`BVa BVb -> BVa+b`: `<op_name>_<a>_<b>` (naming?)
- `concat`: defined as: `concat(x,y)=orr(extend_zero(y),lsl(extend_zero(x),b))`

## Derivability

Some standard operations have to have semantic in lira arch

`extract`, `concat`, `clz`, predicates

## Encoding

Encoding will likely be using same approach: `a |= b << c`.
Maybe it's better to make this operation standard one.
