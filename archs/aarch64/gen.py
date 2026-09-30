#!/usr/bin/env python3
"""Generate the LIRA description of the A64 instructions.

Usage (from the repository root):
    python -m archs.aarch64.gen [--xml <ISA_A64_xml dir>] [--output aarch64.yaml]
                                [--simgen <subset.yaml>]

`--simgen` also writes the subset that lira-simgen-lib can simulate (see
`simgen_subset`).
"""
import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict

from python.lira.arch import Arch, Instruction, InstructionEncoding
from python.lira.ir_builder import InstructionBuilder, SnippetBuilder, Value
from python.lira import arch_ser_yaml

from . import xmlspec
from .insns import EXCLUDE, FILES, SEM, SPECS
from .lib import Ctx, S

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_XML = ROOT / 'ISA_A64_xml_A_profile-2026-06_mc' / 'ISA_A64_xml_A_profile-2026-06_mc'


def _decode_snippet(ctx: Ctx, f: xmlspec.Field) -> str:
    """`[32 -> field]`: extract one operand field from the instruction word."""
    name = f'decode_field_{f.lo}_{f.width}'
    if name not in ctx.snippets:
        sb = SnippetBuilder(name)
        s = S(ctx, sb)
        sb.output(s.bits(sb.input(0, 32), f.lo, f.width), 0)
        ctx.add_snippet(sb, dedup=False)
    return name


def _encode_snippet(ctx: Ctx, e: xmlspec.Encoding) -> str:
    """`[operands] -> 32`: `enc_base` is the encoding's const_encoding_part."""
    sig = '_'.join(f'{f.lo}w{f.width}' for f in e.operands) or 'none'
    name = f'encode_{sig}'
    if name not in ctx.snippets:
        sb = SnippetBuilder(name)
        s = S(ctx, sb)
        acc = sb.dyn_const('enc_base', 32)
        for i, f in enumerate(e.operands):
            v = s.zext(sb.input(i, f.width), 32)
            if f.lo:
                v = s.lsl(v, s.c(f.lo, 32))
            acc = s.orr(acc, v)
        sb.output(acc, 0)
        ctx.add_snippet(sb, dedup=False)
    return name


def resolve_overlaps(encs: Dict[str, xmlspec.Encoding]):
    """A more specific encoding wins over a general one it is contained in (the
    XML's `See(...)`, e.g. HINT vs. PACIASP): the general one excludes it."""
    all_encs = list(encs.values())
    for e in all_encs:
        e.excluded = []
        for f in all_encs:
            if f is e or (f.const_mask & e.const_mask) != e.const_mask:
                continue
            if f.const_mask != e.const_mask and (f.const_value & e.const_mask) == e.const_value:
                e.excluded.append((f.const_mask & ~e.const_mask, f.const_value & ~e.const_mask))


def _word(s: S, e: xmlspec.Encoding, F) -> Value:
    """The operand bits of the instruction word (fixed bits are zero)."""
    acc = s.c(0, 32)
    for f in e.operands:
        v = s.zext(F(f.name), 32)
        acc = s.orr(acc, s.lsl(v, s.c(f.lo, 32)) if f.lo else v)
    return acc


def _validity(s: S, e: xmlspec.Encoding, F, undef, word: Value = None) -> Value:
    """1 iff the operand fields form an allocated (not UNDEFINED) encoding.
    `word` is the instruction word when it is at hand (constraint_decode)."""
    bad = []
    if getattr(e, 'excluded', None):
        if word is None:
            word = _word(s, e, F)
        masked: Dict[int, Value] = {}
        for m, v in e.excluded:
            if m not in masked:
                masked[m] = s.and_(word, s.c(m, 32))
            bad.append(s.eqc(masked[m], v))
    for fname, pat in e.ne:                                # `field != pattern` in XML
        m = int(pat.replace('0', '1').replace('x', '0'), 2)
        v = int(pat.replace('x', '0'), 2)
        w = e.fields[fname].width
        bad.append(s.eqc(s.and_(F(fname), s.c(m, w)), v))
    if undef is not None:
        u = undef(s, e, F)
        if u is not None:
            bad.append(u)
    return s.not_(s.or1(*bad)) if bad else None


def _constraint_snippets(ctx: Ctx, e: xmlspec.Encoding, undef):
    # constraint_encode: operands -> 1; also checks bits the encoding fixes
    sb = SnippetBuilder(f'constraint_encode_{e.name}')
    s = S(ctx, sb)
    vals = {f.name: sb.input(i, f.width) for i, f in enumerate(e.operands)}
    F = _field_accessor(s, e, vals)
    checks = []
    for f in e.operands:
        m, v = e.fixed_bits(f.name)
        if m:
            checks.append(s.eqc(s.and_(vals[f.name], s.c(m, f.width)), v))
    ok = _validity(s, e, F, undef)
    if ok is not None:
        checks.append(ok)
    if not checks:
        return '', ''
    sb.output(s.and1(*checks), 0)
    enc_name = ctx.add_snippet(sb)

    # constraint_decode: instruction word -> 1 (fixed bits are matched by the decoder)
    ok_needed = ok is not None
    if not ok_needed:
        return '', enc_name
    sb = SnippetBuilder(f'constraint_decode_{e.name}')
    s = S(ctx, sb)
    word = sb.input(0, 32)
    sb.output(_validity(s, e, _field_accessor(s, e, {}, word), undef, word), 0)
    return ctx.add_snippet(sb), enc_name


def _field_accessor(s: S, e: xmlspec.Encoding, vals: Dict[str, Value], word: Value = None):
    """F(name): an operand value, a field extracted from `word` on first use,
    or the constant value of a fixed field."""
    operands = {f.name: f for f in e.operands}

    def F(name: str) -> Value:
        if name not in vals:
            if word is not None and name in operands:
                f = operands[name]
                vals[name] = s.bits(word, f.lo, f.width)
            else:
                v = e.fixed(name)
                assert v is not None, f'{e.name}: field {name} is neither operand nor fixed'
                vals[name] = s.c(v, e.fields[name].width)
        return vals[name]
    return F


def build_instruction(ctx: Ctx, e: xmlspec.Encoding) -> Instruction:
    handler, undef = SEM[e.file]
    constraint_decode, constraint_encode = _constraint_snippets(ctx, e, undef)
    encoding = InstructionEncoding(
        encoded_size=32,
        const_encoding_part=e.const_value,
        const_mask=e.const_mask,
        decode=[_decode_snippet(ctx, f) for f in e.operands],
        encode=_encode_snippet(ctx, e),
        constraint_decode=constraint_decode,
        constraint_encode=constraint_encode,
    )
    ib = InstructionBuilder(e.name, [f.width for f in e.operands],
                            [f.name for f in e.operands], encoding)
    s = S(ctx, ib)
    vals = {f.name: ib.add_input_operand(i, f.width) for i, f in enumerate(e.operands)}
    handler(s, e, _field_accessor(s, e, vals))
    ctx.collect_ops(ib)
    instr = ib.build()
    instr.attributes = [f'{k}.{v}' for k, v in sorted(e.docvars.items()) if k != 'isa']
    return instr


def build_arch(xml_dir: Path) -> Arch:
    ctx = Ctx()
    encs = xmlspec.load(xml_dir, FILES)
    for name in EXCLUDE:
        del encs[name]
    for name, e in list(encs.items()):
        spec_list = SPECS.get(e.file)
        if callable(spec_list):
            spec_list = spec_list(e)
        if spec_list:
            del encs[name]
            for suffix, fixed in spec_list:
                spec = xmlspec.specialize(e, suffix, fixed)
                encs[spec.name] = spec
    resolve_overlaps(encs)
    instructions = [build_instruction(ctx, e) for e in encs.values()]
    return Arch(
        name='AArch64',
        attributes=['isa.A64', 'endianness.little'],
        register_files=[ctx.rf_x, ctx.rf_nzcv, ctx.rf_v, ctx.rf_fpcr, ctx.rf_fpsr],
        system_registers=[],
        environment_functions=list(ctx.envs.values()),
        tables_int=list(ctx.tables.values()),
        operations=list(ctx.ops.values()),
        snippets=list(ctx.snippets.values()),
        instructions=instructions,
        float_operations=list(ctx.fops.values()),
    )


# What lira-simgen-lib supports: these statements (scalar and vector shapes
# without lanes_mult), register files and environment functions, and
# operations defined by a base, a snippet or a table
SIMGEN_KINDS = {'input', 'output', 'const', 'dyn_const', 'read', 'write', 'op', 'fop', 'env', 'cond_env',
                'index', 'gather', 'replicate', 'extract_first', 'extend_zero', 'fold'}
SIMGEN_RFS = ('X', 'V', 'NZCV', 'FPCR', 'FPSR')
SIMGEN_ENVS = {'pc_read', 'pc_write', 'supervisor_call'} | \
    {f'mem_{d}_{n}' for d in ('read', 'write') for n in (8, 16, 32, 64, 128)} | \
    {'check_alignment', 'exclusive_mark', 'exclusive_check', 'exclusive_clear',
     'barrier', 'hint', 'wait_timeout', 'branch_target', 'mem_copy', 'mem_set',
     'pac_add', 'pac_auth', 'pac_strip', 'pac_generic',
     'exception_call', 'exception_return', 'debug_state', 'sys_op', 'sys_op_read',
     'sysreg_read', 'sysreg_write', 'pstate_write'}


def simgen_subset(arch: Arch) -> Arch:
    """The instructions (with the operations and snippets they reach) that
    lira-simgen-lib can generate a simulator for."""
    ops = {o.name: o for o in arch.operations}
    snippets = {s.name: s for s in arch.snippets}

    def seq_ok(seq, used_ops, used_snippets):
        for st in seq.stmts:
            if st.kind not in SIMGEN_KINDS or st.shape.lanes_mult:
                return False
            if st.kind in ('read', 'write') and st.specifier not in SIMGEN_RFS:
                return False
            if st.kind in ('env', 'cond_env') and st.specifier not in SIMGEN_ENVS:
                return False
            if st.kind in ('op', 'fold') and not op_ok(ops[st.specifier], used_ops, used_snippets):
                return False
        return True

    def snippet_ok(name, used_ops, used_snippets):
        if name in used_snippets:
            return True
        used_snippets.add(name)
        return seq_ok(snippets[name].seq, used_ops, used_snippets)

    def op_ok(op, used_ops, used_snippets):
        if op.name in used_ops:
            return True
        used_ops.add(op.name)
        return all(snippet_ok(s, used_ops, used_snippets)
                   for s in (op.semantic_func, op.semantic_func_128) if s)

    keep, all_ops, all_snippets = [], set(), set()
    for ins in arch.instructions:
        used_ops, used_snippets = set(), set()
        e = ins.encoding
        refs = [*e.decode, e.encode, e.constraint_decode, e.constraint_encode]
        if seq_ok(ins.semantic, used_ops, used_snippets) and \
                all(snippet_ok(r, used_ops, used_snippets) for r in refs if r):
            keep.append(ins)
            all_ops |= used_ops
            all_snippets |= used_snippets
    used_rfs = {st.specifier for ins in keep for st in ins.semantic.stmts if st.kind in ('read', 'write')}
    used_envs = {st.specifier for ins in keep for st in ins.semantic.stmts if st.kind in ('env', 'cond_env')}
    used_fops = {st.specifier for ins in keep for st in ins.semantic.stmts if st.kind == 'fop'}
    return Arch(
        name=arch.name,
        attributes=arch.attributes,
        register_files=[rf for rf in arch.register_files if rf.name in used_rfs],
        system_registers=arch.system_registers,
        environment_functions=[f for f in arch.environment_functions if f.name in used_envs],
        tables_int=[t for t in arch.tables_int
                    if any(o.semantic_table == t.name for o in arch.operations if o.name in all_ops)],
        operations=[o for o in arch.operations if o.name in all_ops],
        snippets=[s for s in arch.snippets if s.name in all_snippets],
        instructions=keep,
        float_operations=[f for f in arch.float_operations if f.name in used_fops],
    )


def write_yaml(arch: Arch, path: Path):
    raw = path.with_suffix('.raw.yaml')
    arch_ser_yaml.write_arch(arch, raw)
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'yaml_canonicalize.py'),
                    str(raw), str(path)], check=True)
    raw.unlink()
    assert arch_ser_yaml.read_arch(path) == arch, 'YAML round trip mismatch'
    print(f'{path}: {len(arch.instructions)} instructions, '
          f'{len(arch.operations)} operations, {len(arch.snippets)} snippets')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--xml', type=Path, default=DEFAULT_XML)
    parser.add_argument('--output', type=Path, default=HERE / 'aarch64.yaml')
    parser.add_argument('--simgen', type=Path, help='also write the lira-simgen-lib subset here')
    args = parser.parse_args()

    arch = build_arch(args.xml)
    write_yaml(arch, args.output)
    if args.simgen:
        write_yaml(simgen_subset(arch), args.simgen)


if __name__ == '__main__':
    main()
