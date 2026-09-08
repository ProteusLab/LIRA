# LIRA Rust Tests

## Integration test

Reads `tests/integration/reference.yaml`, writes back via [normalization script](../../tools/yaml_canonicalize.py), asserts round-trip equality.

```bash
cargo test -p lira-tests --test integration
```

## All tests

```bash
cargo test -p lira-tests
```
