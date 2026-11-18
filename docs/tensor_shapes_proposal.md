# Proposal: tensor shapes

## Motivation

Tensor shapes let definitions and documentation describe computations in terms
of their logical structure. One-dimensional vectors can represent the same
computations, but require flattening that structure into indexing conventions.

This became particularly clear when generalizing fold and scan:

- Understanding their signatures called for distinguishing scalars from
  single-element vectors.
- A per-matrix-row fold can be expressed using flattened vectors, but while
  exploring support for matrix extensions, describing it in matrix terms made
  the generalization clear: `[M, N] -> [M]`, with one result per row.

The tradeoff is a more complex programmatic representation and, especially,
text format.

## Shape model

`Shape` becomes `Vec<Dimension>`, where `Dimension` is the current shape:
`const × optional dyn-const`. No dimensions means scalar; `[1]` means a
single-element vector; `[M, N]` means a matrix.

```python
@dataclass
class Dimension:
    lanes_base: int
    lanes_mult: Optional[str] = None

@dataclass
class Shape:
    dimensions: list[Dimension] = field(default_factory=list)
```

Keep one shared shape for all outputs of a statement. Inputs may have different
shapes, as determined by the statement's semantics.

## Text format

Separate dimensions with dots, keeping the current spelling of each dimension:
`4`, `2N`, `2.4`, `8M.4N`.

Scalar shape is `.` and may be omitted; the writer omits it. On the left of `=`,
an even number of whitespace-separated tokens means only `type name` pairs;
an odd number means a leading shape token followed by those pairs.

| Example                     | Meaning                                      |
| --------------------------- | -------------------------------------------- |
| `. 32 x = input 0;`         | Scalar, explicit shape                       |
| `32 x = input 0;`           | Scalar, omitted shape                        |
| `1 32 x = input 0;`         | Length-one vector                            |
| `2.3VL 32 x 1 y = input 0;` | Both outputs have matrix shape `[2, 3 × VL]` |

Old scalar text using `1` needs migration. Dots now separate dimensions, so
dynamic-constant names cannot contain them; escaping remains a review question.

## Implementation choices

Structured serialization writes `Shape` as a bare dimension list rather than
a `dimensions` mapping. This requires `#[serde(transparent)]` in Rust and a
special case in Python. Keeping the wrapper would avoid that special handling;
the tensor model does not require either format.

## Open questions

Should registers retain a single `Dimension` for their bit width, as in this
draft, or have a full `Shape` plus an element width to describe scalar, vector,
and matrix registers explicitly?
