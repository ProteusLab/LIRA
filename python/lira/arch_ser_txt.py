from lira.ir import *
from lira.arch import *
from lira.ir_ser_txt import *

from dataclasses import is_dataclass, fields, asdict
from typing import Any, Type, get_origin, get_args
from pathlib import Path
import json
import os
import shutil

def to_serializable(obj: Any) -> Any:
    '''Convert a dataclass or nested structure into JSON‑serializable dicts/lists.'''
    if is_dataclass(obj):
        return {f.name: to_serializable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, list):
        return [to_serializable(item) for item in obj]
    return obj

def from_serializable(cls: Type, data: Any) -> Any:
    '''Reconstruct a dataclass, list of dataclasses, or primitive from serialized data.'''
    origin = get_origin(cls)
    if is_dataclass(cls):
        types = {f.name: f.type for f in fields(cls)}
        return cls(**{name: from_serializable(types[name], value) for name, value in data.items()})
    if origin is list:
        return [from_serializable(get_args(cls)[0], item) for item in data]
    return data

def read_arch(folder_path: Path) -> Arch:
    def load_json(suffix: str):
        with open(folder_path / suffix, 'r') as f:
            return json.load(f)

    arch_info = load_json('arch.json')
    name = arch_info['name']
    attributes = arch_info['attributes']

    def load_json_as(cls, suffix: str):
        return from_serializable(cls, load_json(suffix))

    register_files =        load_json_as(list[RegisterFile], 'register_files.json')
    system_registers =      load_json_as(list[SystemRegister], 'system_registers.json')
    environment_functions = load_json_as(list[EnvironmentFunction], 'environment_functions.json')
    tables_int =            load_json_as(list[TableInt], 'tables_int.json')

    index = load_json('index.json')
    op_names = index['operations']
    snippet_names = index['snippets']
    instr_names = index['instructions']

    def load_lira(suffix: str):
        with open(folder_path / suffix) as f:
            return deserialize_statement_seq(f.read())

    def load_operation(name: str):
        return load_json_as(Operation, f'operations/{name}.json')
    def load_snippet(name: str):
        return Snippet(name, load_lira(f'snippets/{name}.lira'))
    def load_instruction(name: str):
        instr = load_json(f'instructions/{name}.json')
        instr['semantic'] = {'stmts':[]}
        instr = from_serializable(Instruction, instr)
        instr.semantic = load_lira(f'instructions/{name}.lira')
        return instr

    operations = [load_operation(name) for name in op_names]
    snippets = [load_snippet(name) for name in snippet_names]
    instructions = [load_instruction(name) for name in instr_names]

    return Arch(
        name=name,
        attributes=attributes,
        register_files=register_files,
        system_registers=system_registers,
        environment_functions=environment_functions,
        tables_int=tables_int,
        operations=operations,
        snippets=snippets,
        instructions=instructions,
    )

def write_arch(arch: Arch, folder_path: Path) -> None:
    '''Write an entire architecture to a folder, overwriting any existing content.'''
    if folder_path.exists():
        shutil.rmtree(folder_path)
    folder_path.mkdir(parents=True)

    def write_json(data, suffix: str) -> None:
        with open(folder_path / suffix, 'w') as f:
            json.dump(data, f)

    write_json({'name': arch.name, 'attributes': arch.attributes}, 'arch.json')

    def write_component_list(objs, suffix: str) -> None:
        write_json([to_serializable(obj) for obj in objs], suffix)

    write_component_list(arch.register_files, 'register_files.json')
    write_component_list(arch.system_registers, 'system_registers.json')
    write_component_list(arch.environment_functions, 'environment_functions.json')
    write_component_list(arch.tables_int, 'tables_int.json')

    index = {
        'operations': [op.name for op in arch.operations],
        'snippets': [s.name for s in arch.snippets],
        'instructions': [i.name for i in arch.instructions],
    }
    write_json(index, 'index.json')

    ops_dir = folder_path / 'operations'
    ops_dir.mkdir()
    for op in arch.operations:
        with open(ops_dir / f'{op.name}.json', 'w') as f:
            json.dump(to_serializable(op), f, indent=2)

    snippets_dir = folder_path / 'snippets'
    snippets_dir.mkdir()
    for snip in arch.snippets:
        with open(snippets_dir / f'{snip.name}.lira', 'w') as f:
            f.write(serialize_statement_seq(snip.seq))

    instr_dir = folder_path / 'instructions'
    instr_dir.mkdir()
    for instr in arch.instructions:
        instr_dict = to_serializable(instr)
        instr_dict.pop('semantic', None)
        with open(instr_dir / f'{instr.name}.json', 'w') as f:
            json.dump(instr_dict, f, indent=2)
        with open(instr_dir / f'{instr.name}.lira', 'w') as f:
            f.write(serialize_statement_seq(instr.semantic))
