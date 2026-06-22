# Basic operations

All basic LIRA operations are inherited from the standard operation from the lira/arch module.

Below is an implementation of a standard operation in [python](../python/lira/arch.py):

```python3
@dataclass
class Operation(Component):
    inputs: list[int]
    outputs: list[int]
    semantic_base: Optional[str] = None
    semantic_func: Optional[str] = None
    semantic_func_128: Optional[str] = None
    semantic_table: Optional[str] = None
```

# Types

In general, base operations work on bit-vector (BV) values.

Note: `BV<1>` is used instead of `Bool`.

# Name Conventions

Operations are grouped by operand signature.
The `name` field follows the specific pattern.

## Unary

`BV<n> -> BV<n>` - `<semnatic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `not`     | bitwise NOT |
| `neg`     | two's complement negation |
| `popcnt`  | population count (number of set bits) |
| `ctz`     | count trailing zeros |
| `clz`     | count leading zeros |
| `reverse` | reverse bit order |

## Binary

`BV<n> BV<n> -> BV<n>` – `<semnatic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `add`     | addition |
| `sub`     | subtraction |
| `mul`     | multiplication |
| `and`     | bitwise AND |
| `orr`     | bitwise OR |
| `xor`     | bitwise XOR |
| `lsl`     | logical shift left |
| `lsr`     | logical shift right |
| `asr`     | arithmetic shift right |
| `rem_u`   | unsigned remainder (`rem(a,0)=a`) |
| `rem_s`   | signed remainder (`rem(a,0)=a`) |
| `ror`     | rotate right |
| `rol`     | rotate left |

## Comparison

`BV<n> BV<n> -> BV<1>` - `<semnatic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `eq`  | equality |x
| `ne`  | not equal |
| `slt` | signed less than |
| `sle` | signed less or equal |
| `sgt` | signed greater than |
| `sge` | signed greater or equal |
| `ult` | unsigned less than |
| `ule` | unsigned less or equal |
| `ugt` | unsigned greater than |
| `uge` | unsigned greater or equal |
| `add_overflow` | signed addition overflow |
| `sub_overflow` | signed subtraction overflow |

## Ternary

`BV<n> BV<n> BV<n> -> BV<n>` - `<semnatic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `div_u` | unsigned division: `div(a,b,c) = b != 0 ? a/b : c` |
| `div_s` | signed division: `div(a,b,c) = b != 0 ? a/b : c` |

## Select

`BV<1> BV<n> BV<n> -> BV<n>` - `<semnatic_base>_<n>`

| Operation | Description |
|-----------|-------------|
| `select` | multiplexer: `select(cond, true, false)` |

## Cast

`BV<in> -> BV<out>` - `<semnatic_base>_<in>_to_<out>`

| Operation | Description |
|-----------|-------------|
| `extract_low`  | extract low bits (`out` <= `in`) |
| `extend_sign`  | sign-extend (`out` > `in`) |
| `extend_zero`  | zero-extend (`out` > `in`) |

## Derivatives

Some compound operations are derived from the standard set and need semantic definitions in the LIRA architecture:

- `extract(v, start, width)` = `extract_low(lsr(v, start), width)`
- `concat(low, high)` = `orr(extend_zero(low, high_bits + low_bits), lsl(extend_zero(high, high_bits + low_bits), low_bits))`
