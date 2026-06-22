# LIRA Python Usage Example

* RISC-V-like test architecture (register file, environment functions, operations, snippets, and a `blt` instruction)
* Serializes it to YAML, deserializes it back
* Asserts round-trip equality.

## Run

```bash
python3 example.py --output /path/to/output.yaml
```

## Requirements
```bash
pip install ruamel.yaml
```
