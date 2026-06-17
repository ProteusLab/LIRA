# LIRA Rust Tests

## Unit tests

```bash
cargo test -p lira-tests --test unit_ir_ser_txt --test unit_arch_ser_yaml --test unit_ir_builder
```

## Unit coverage

```bash
cargo llvm-cov -p lira --lib -p lira-tests --test unit_ir_ser_txt --test unit_arch_ser_yaml --test unit_ir_builder
```
```bash
cargo llvm-cov -p lira --lib -p lira-tests --test unit_ir_ser_txt --test unit_arch_ser_yaml --test unit_ir_builder --html
```

## Integration test

Reads `tests/integration/reference.yaml`, writes back via [normalization script](../../tools/yaml_canonicalize.py), asserts round-trip equality.

```bash
cargo test -p lira-tests --test integration
```

## All tests

```bash
cargo test -p lira-tests
```
