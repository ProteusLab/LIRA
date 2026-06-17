# LIRA Rust Example

* RISC-V-like test architecture (register file, environment functions, operations, snippets, and a `blt` instruction)
* Serializes it to YAML, deserializes it back
* Asserts round-trip equality.

## Run

```bash
cargo run -p lira-example
cargo run -p lira-example -- --output /path/to/output.yaml
```

## Test

```bash
cargo test -p lira-example
```
