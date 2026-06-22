from pathlib import Path
from typing import Any, Type, get_origin, get_args
from dataclasses import is_dataclass, fields

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from .arch import *
from .ir import StatementSeq
from .ir_ser_txt import serialize_statement_seq, deserialize_statement_seq

def to_serializable(obj: Any) -> Any:
    if isinstance(obj, StatementSeq):
        return LiteralScalarString(serialize_statement_seq(obj))
    if is_dataclass(obj):
        d = {}
        for f in fields(obj):
            val = getattr(obj, f.name)
            d[f.name] = to_serializable(val)
        return d
    if isinstance(obj, list):
        return [to_serializable(item) for item in obj]
    return obj


def from_serializable(cls: Type, data: Any) -> Any:
    origin = get_origin(cls)
    if is_dataclass(cls):
        types = {f.name: f.type for f in fields(cls)}
        kwargs = {}
        for name, value in data.items():
            if types[name] is StatementSeq and isinstance(value, str):
                kwargs[name] = deserialize_statement_seq(value)
            else:
                kwargs[name] = from_serializable(types[name], value)
        return cls(**kwargs)
    if origin is list:
        item_cls = get_args(cls)[0]
        return [from_serializable(item_cls, item) for item in data]
    return data


def write_arch(arch: Arch, filepath: Path) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)

    data = to_serializable(arch)
    with open(filepath, 'w', encoding='utf-8') as f:
        yaml.dump(data, f)


def read_arch(filepath: Path) -> Arch:
    yaml = YAML()
    with open(filepath, 'r', encoding='utf-8') as f:
        data = yaml.load(f)
    return from_serializable(Arch, data)
