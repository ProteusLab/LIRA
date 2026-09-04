# Generates C functions with semantic for standard operations
#
# Types: everything is expressed with `uint64_t` (aka `u64`)
# - higher (96, 128) types are not supported
#
# Signature:
# - first output - return type
# - rest outputs - first arguments by pointer
# - and finally go inputs

assert __name__ == '__main__'

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Callable
from itertools import chain

from lira import arch_ser_yaml

assert len(sys.argv) == 3, f'{sys.argv[0]} <INPUT> <OUTPUT>'



i64 = '(int64_t)'
u64 = '(uint64_t)'
unary = lambda a: ([a], [a])
binary = lambda a: ([a], [a, a])
ternary = lambda a: ([a], [a, a, a])
cmp = lambda a: ([1], [a, a])
expr = lambda f: lambda a: f' return ({f(a)}) & {(1<<a) - 1}ul; '
expr_s = lambda pattern: expr(lambda _: pattern)

def sext(var: str, a: int) -> str:
    return f'({i64}({var} << {64-a}) >> {64-a})'

def s_overflow(op: str):
    return lambda a: f'''
    int64_t x = 0;
    return __builtin_s{op}l_overflow(i0 << {64-a}, i1 << {64-a}, &x) ? 1 : 0;
'''

generators = {}
for name, sig, code in [
    ('not', unary, expr_s('~i0')),
    ('neg', unary, expr_s('-i0')),
    ('cnt', unary, expr_s('__builtin_popcountll(i0)')),
    ('clz', unary, expr(lambda a: f'i0 == 0 ? {a} : (__builtin_clzll(i0) - {64-a})')),
    ('ctz', unary, expr(lambda a: f'i0 == 0 ? {a} : __builtin_ctzll(i0)')),
    ('rev', unary, expr(lambda a: f'__builtin_bitreverse64(i0 << {64-a})')),
    ('add', binary, expr_s('i0 + i1')),
    ('sub', binary, expr_s('i0 - i1')),
    ('mul', binary, expr_s('i0 * i1')),
    ('and', binary, expr_s('i0 & i1')),
    ('orr', binary, expr_s('i0 | i1')),
    ('xor', binary, expr_s('i0 ^ i1')),
    ('lsl', binary, expr(lambda a: (f'i1 >= {a} ? 0 : (i0 << i1)'))),
    ('lsr', binary, expr(lambda a: (f'i1 >= {a} ? 0 : (i0 >> i1)'))),
    ('asr', binary, expr(lambda a: f'{u64}({i64}(i0 << {64-a}) >> (i1 >= {a} ? 63 : i1)) >> {64-a}')),
    ('rem_u', binary, expr_s(f'i1 == 0 ? 0 : i0 % i1')),
    ('rem_s', binary, expr(lambda a: f'i1 == 0 ? 0 : {u64}({sext("i0", a)} % {sext("i1", a)})')),
    ('ror', binary, expr(lambda a: f'(i0 >> (i1 % {a})) | (i0 << (({a} - i1) % {a}))')),
    ('rol', binary, expr(lambda a: f'(i0 << (i1 % {a})) | (i0 >> (({a} - i1) % {a}))')),
    ('eq', cmp, expr_s('i0 == i1 ? 1 : 0')),
    ('ne', cmp, expr_s('i0 != i1 ? 1 : 0')),
    ('ult', cmp, expr_s('i0 < i1 ? 1 : 0')),
    ('ule', cmp, expr_s('i0 <= i1 ? 1 : 0')),
    ('ugt', cmp, expr_s('i0 > i1 ? 1 : 0')),
    ('uge', cmp, expr_s('i0 >= i1 ? 1 : 0')),
    ('slt', cmp, expr(lambda a: f'{sext("i0", a)} < {sext("i1", a)} ? 1 : 0')),
    ('sle', cmp, expr(lambda a: f'{sext("i0", a)} <= {sext("i1", a)} ? 1 : 0')),
    ('sgt', cmp, expr(lambda a: f'{sext("i0", a)} > {sext("i1", a)} ? 1 : 0')),
    ('sge', cmp, expr(lambda a: f'{sext("i0", a)} >= {sext("i1", a)} ? 1 : 0')),
    ('add_u_overflow', cmp, expr(lambda a: f'(i0 << {64-a}) + (i1 << {64-a}) > (i0 << {64-a}) ? 0 : 1')),
    ('sub_u_overflow', cmp, expr(lambda a: f'(i0 << {64-a}) - (i1 << {64-a}) < (i0 << {64-a}) ? 0 : 1')),
    ('add_s_overflow', cmp, s_overflow('add')),
    ('sub_s_overflow', cmp, s_overflow('sub')),
    ('div_u', ternary, expr_s(f'i1 == 0 ? i2 : i0 / i1')),
    # TODO: check overflow, e.g. division by -1
    ('div_s', ternary, expr(lambda a: f'i1 == 0 ? i2 : {u64}({sext("i0", a)} / {sext("i1", a)})')),
    ('select', lambda a: ([a], [1, a, a]), expr_s('i0 == 1 ? i1 : i2')),
]:
    def process(outputs: list[int], inputs: list[int], sig=sig, code=code) -> str:
        a = inputs[-1]
        assert (outputs, inputs) == sig(a), f'{(outputs, inputs)}, expected {sig(a)}'
        return code(a)
    generators[name] = process

def extract_low(outputs: list[int], inputs: list[int]) -> str:
    assert len(outputs) == 1
    assert len(inputs) == 1
    assert outputs[0] <= inputs[0]
    return expr_s('i0')(outputs[0])
generators['extract_low'] = extract_low


def extend_zero(outputs: list[int], inputs: list[int]) -> str:
    assert len(outputs) == 1
    assert len(inputs) == 1
    assert outputs[0] >= inputs[0]
    return expr_s('i0')(outputs[0])
generators['extend_zero'] = extend_zero

def extend_sign(outputs: list[int], inputs: list[int]) -> str:
    assert len(outputs) == 1
    assert len(inputs) == 1
    i = inputs[0]
    o = outputs[0]
    assert o >= i
    return f' return {u64}({i64}(i0 << {64-i}) >> {o-i}) >> {64-o}; '
generators['extend_sign'] = extend_sign

path_input = Path(sys.argv[1])
path_output = Path(sys.argv[2])

arch = arch_ser_yaml.read_arch(path_input)

with open(path_output, 'w') as f:
    f.write('''\
#include <stdint.h>

''')

    for op in arch.operations:
        if not op.semantic_base is None:
            for ty in chain(op.inputs, op.outputs):
                assert ty >= 1 and ty <= 64
            try:
                code = generators[op.semantic_base](op.outputs, op.inputs)
                inputs = ', '.join([f'uint64_t i{n}' for n, _ in enumerate(op.inputs)])
                f.write(f'uint64_t {op.name}({inputs}) {{{code}}}\n')
            except Exception as e:
                raise type(e)(f'{e} while processing {op.name} ({op.semantic_base})') from e
