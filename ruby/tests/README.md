# LIRA Ruby Tests

## Unit tests

```bash
ruby -I ruby -I ruby/lib ruby/tests/unit/*.rb
```

## Unit coverage

```bash
ruby -r simplecov -I ruby -I ruby/lib -e 'SimpleCov.start; Dir["ruby/tests/unit/*.rb"].each { |f| require_relative f }'
```

## Integration test

Reads `tests/integration/reference.yaml`, writes back via [normalization script](../../tools/yaml_canonicalize.py), asserts round-trip equality.

```bash
ruby -I ruby -I ruby/lib ruby/tests/integration/test_integration.rb
```
