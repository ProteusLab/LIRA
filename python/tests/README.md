# LIRA Python Tests

## Unit tests

```bash
pytest python/tests/unit/ -v
```

With coverage:

```bash
pytest --cov=python/lira python/tests/unit/ --cov-report=term
```

## Integration test

Reads `tests/integration/reference.yaml`, writes back via [normalization script](../../tools/yaml_canonicalize.py), asserts round-trip equality.

```bash
pytest python/tests/integration/ -v
```
