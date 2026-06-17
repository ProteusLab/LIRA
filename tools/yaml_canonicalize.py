#!/usr/bin/env python3

import sys
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

yaml = YAML()
yaml.default_flow_style = False
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.preserve_quotes = True


def recursive_literalize(obj):
    if isinstance(obj, dict):
        return {k: recursive_literalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [recursive_literalize(v) for v in obj]
    if isinstance(obj, str) and '\n' in obj:
        return LiteralScalarString(obj)
    return obj


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.yaml> <output.yaml>", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    data = yaml.load(input_path)
    data = recursive_literalize(data)
    yaml.dump(data, output_path)

    content = output_path.read_text()
    content = content.replace('\"\"', "''")
    import re
    content = re.sub(r'":(\w+)"', r':\1', content)
    output_path.write_text(content)


if __name__ == "__main__":
    main()
