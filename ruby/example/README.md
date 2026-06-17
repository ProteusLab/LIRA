# LIRA Ruby Integration Test

* RISC-V-like test architecture (register file, environment functions, operations, snippets, and a `blt` instruction)
* Serializes it to YAML, deserializes it back
* Asserts round-trip equality

## Run

```bash
ruby example/integration_test.rb --output /path/to/output.yaml
```
