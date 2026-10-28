"""Symbolic comparison of LIRA semantics with the Sail Arm model, run in Isla.

For an instruction and fixed register numbers, isla-footprint executes the
Sail model (rems-project/isla-snapshots armv9p4.ir: sail-arm v9.4, ASL 2023-03)
on the opcode with every other field symbolic, from a symbolic state, and
prints one trace per path (isla_trace.py reads it). lira_smt.py evaluates the
LIRA semantics over the same fields and state. Each path p is then a query

    PathCond_p and Bindings_p and not Agree(p, LIRA)

where Bindings_p ties the values the trace reads to the shared initial state
and Agree says that the outcome is the same: no exception and equal X0..X30,
SP, NZCV, next PC and memory, or the same exception (SVC/BRK immediate,
UNDEFINED, alignment fault). UNSAT for every path proves the two equal for all
field values, registers, PC and memory; a model is a counterexample. Data
aborts other than alignment faults are the environment's (LIRA's memory hooks
cannot fault) and are not compared. What Isla cannot execute symbolically,
or the solver cannot decide, gets fallback_runs: one run per field value
(still a proof) or concrete samples (a test, status 'sampled').

Setup (see archs/aarch64/README.md): build isla-footprint and isla-preprocess,
get armv9p4.ir, and run

    python -m archs.aarch64.tests.isla_oracle prepare <dir>/armv9p4.ir

which patches the model (IR_PATCHES) and preprocesses it with isla/lira.toml
into <dir>/lira-armv9p4.irx. $ISLA_FOOTPRINT names isla-footprint (default: on
PATH), $LIRA_ISLA_ARCH the .irx. Traces are cached in $LIRA_ISLA_CACHE
(default ~/.cache/lira-isla). $LIRA_ISLA_JOBS cases run at once, each in a
worker process with its Isla process (default 4, about 2 GB each).
"""
import argparse
import concurrent.futures
import ctypes
import gzip
import hashlib
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import z3

from python.lira.arch import Instruction

from . import isla_trace
from .lira_smt import MEM_SORT, REG_FIELDS, OutOfScope, Raised, SymMachine, concrete_step, in_scope, uses

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'isla' / 'lira.toml'
ISLA = os.environ.get('ISLA_FOOTPRINT') or shutil.which('isla-footprint')
ARCH = Path(os.environ['LIRA_ISLA_ARCH']) if os.environ.get('LIRA_ISLA_ARCH') else None
CACHE = Path(os.environ.get('LIRA_ISLA_CACHE') or Path.home() / '.cache' / 'lira-isla')
JOBS = int(os.environ.get('LIRA_ISLA_JOBS') or 4)
TIMEOUT = int(os.environ.get('LIRA_ISLA_TIMEOUT') or 600)
SOLVER_TIMEOUT = 120_000                       # ms per path query
QE_TIMEOUT = 5_000                             # ms per quantifier elimination
CHOICE_TIMEOUT = 20_000                        # ms per query of fixed_choice
CHOICE_BUDGET = 600                            # s for fixed_choice in all
# Isla's memory (physical footprint, compressed pages included) at which a run
# is stopped: symbolic CRC32H grows by 0.7 GB/s and takes the machine down
MEMORY_LIMIT = int(float(os.environ.get('LIRA_ISLA_MEMORY_GB') or 6) * 2**30)

# Edits of the model (exact text of armv9p4.ir, each found once), as
# asl/patches.asl is for the ASL:
# - LIRA's memory is Normal Write-Back memory (a Linux process): with the MMU
#   off, the ASL makes data accesses Device-nGnRnE, whose unaligned accesses
#   fault and whose unaligned ordered and atomic accesses are UNPREDICTABLE.
#   Stage 1 cannot be enabled without page tables in every trace, and setting
#   HCR_EL2.DC would also enable stage 2; AArch64_S1DisabledOutput takes its
#   HCR_EL2.DC branch instead (Normal Inner/Outer Write-Back, Non-shareable).
# - No devices: the snapshot was built with HAVE_DEVICES, whose GIC and UART
#   address checks fork every access on its physical address.
# - An instruction that is UNDEFINED takes the Undefined Instruction
#   exception, and one whose decoding says SEE another encoding is decoded
#   again (the SEE register holds where to go on), as the model's
#   __DecodeExecute does: isla_footprint catches the Sail exceptions of the
#   ASL's Undefined() and SEE and ends the path silently. Any other error it
#   catches but the end of a taken exception (a reserved encoding,
#   UNPREDICTABLE, an IMPLEMENTATION DEFINED choice not made) calls
#   lira_other_error, which the runs trace.
LIRA_CAUGHT = '''val zlira_other_error : (%unit) ->  %unit

fn zlira_other_error(zu) {
  return = ();
  end;
}

val zlira_caught : (%unit) ->  %bool

fn zlira_caught(zu) {
  zz40 : %unit;
  zz41 : %i;
  zz42 : %bv;
  have_exception = false;
  jump current_exception is zError_See goto 10;
  zz42 = z_PC;
  zz41 = zUInt0(zz42);
  zz40 = z__DecodeA64(zz41, z__ThisInstr);
  jump have_exception goto 3;
  goto 17;
  jump current_exception is zError_Undefined goto 14;
  zz40 = zAArch64_UndefinedFault(());
  have_exception = false;
  goto 17;
  jump current_exception is zError_ExceptionTaken goto 16;
  goto 17;
  zz40 = zlira_other_error(());
  return = false;
  end;
}

'''
DIV = 'zexecute_aarch64_instrs_integer_arithmetic_div'
IR_PATCHES = [
    ('zAArch64_S1DisabledOutput', '  jump zz431 goto 210 `10 24678:4-24736:5;\n', '  goto 210;\n'),
    ('zisla_footprint_common', '  zz40 = false `31 65:9-65:14;\n', '  zz40 = zlira_caught(());\n'),
    ('zPhysMemRead', '  jump zz41 goto 110 `18 179:2-189:3;\n', '  jump false goto 110;\n'),
    ('zPhysMemRead', '  jump zz413 goto 94 `18 182:9-189:3;\n', '  jump false goto 94;\n'),
    ('zPhysMemWrite', '  jump zz41 goto 100 `18 203:2-218:3;\n', '  jump false goto 100;\n'),
    ('zPhysMemWrite', '  jump zz49 goto 86 `18 206:9-218:3;\n', '  jump false goto 86;\n'),
    # UDIV/SDIV: Isla has no real numbers; for integers and b != 0 (the ASL
    # tests IsZero first), RoundTowardsZero(Real(a) / Real(b)) = tdiv_int(a, b)
    *[(DIV, f'  {line} `24 {loc};\n', '  goto {next};\n') for line, loc in [
        ('zz417 = zto_real(zz420)', '42735:34-42735:70'), ('zz418 = zto_real(zz419)', '42735:73-42735:109'),
        ('zz416 = zdiv_real(zz417, zz418)', '42735:34-42735:109')]],
    (DIV, '  zz42 = zRoundTowardsZero(zz416) `24 42735:17-42735:110;\n', '  zz42 = ztdiv_int(zz420, zz419);\n'),
]

# Sail exceptions and the LIRA outcomes they correspond to
SVC, BRK, UNDEFINED, DATA_ABORT = ('Exception_SupervisorCall', 'Exception_SoftwareBreakpoint',
                                   'Exception_Uncategorized', 'Exception_DataAbort')
DFSC_ALIGNMENT = 0b100001
STATE = [f'X{i}' for i in range(31)] + ['SP', 'NZCV']
ADDR = z3.BitVec('cmp_addr', 64)
MEM_HOOKS = re.compile(r'mem_(read|write)_\d+$')
# Results that are not failures: proved equal, tested equal on samples (what
# the solver could not decide), or outside what is compared
PASS = ('equivalent', 'sampled', 'skipped')


def available() -> bool:
    return bool(ISLA) and ARCH is not None and ARCH.exists()


def config_digest() -> str:
    return hashlib.sha256(CONFIG.read_bytes()).hexdigest()


# -----------------------------------------------------------------------------
# Model preparation

def patch_ir(text: str) -> str:
    for name, old, new in IR_PATCHES:
        m = re.search(r'^fn ' + name + r'\(([^)]*)\) \{\n.*?^\}\n', text, re.S | re.M)
        if not m:
            raise ValueError(f'IR patch: no function {name}')
        if old is None:
            fn = f'fn {name}({m.group(1)}) {{\n{new}}}\n'
        else:
            if m.group(0).count(old) != 1:
                raise ValueError(f'IR patch: {name} does not contain {old!r} once')
            body = m.group(0).split('\n')[1:]                 # one instruction a line
            fn = m.group(0).replace(old, new.format(next=body.index(old.rstrip('\n')) + 1))
        text = text[:m.start()] + fn + text[m.end():]
    at = text.index('val zisla_footprint_common ')
    return text[:at] + LIRA_CAUGHT + text[at:]


def prepare(ir: Path, out: Path):
    """Patch `ir` and preprocess it with the config into `out` (.irx)."""
    patched = out.with_suffix('.ir')
    patched.write_text(patch_ir(ir.read_text()))
    preprocess = Path(ISLA).with_name('isla-preprocess')
    subprocess.run([str(preprocess), '-A', str(patched), '-C', str(CONFIG), '-o', str(out.with_suffix(''))],
                   check=True)
    patched.unlink()
    out.with_name(out.name + '.config').write_text(config_digest())


def check_prepared():
    stamp = ARCH.with_name(ARCH.name + '.config')
    if not stamp.exists() or stamp.read_text() != config_digest():
        raise RuntimeError(f'{ARCH} was not prepared with the current {CONFIG}: rerun '
                           f'`python -m archs.aarch64.tests.isla_oracle prepare <armv9p4.ir>`')


# -----------------------------------------------------------------------------
# Opcodes

@dataclass
class Pattern:
    """A partially symbolic opcode: `text` for isla-footprint --partial, the
    symbolic segments, and the LIRA operands as terms over them."""
    text: str
    segments: Dict[str, z3.BitVecRef]
    operands: List[z3.BitVecRef]


def pattern(ins: Instruction, fixed: Dict[str, int]) -> Pattern:
    enc = ins.encoding
    owner = {}
    for k, d in enumerate(enc.decode):
        lo, w = map(int, re.fullmatch(r'decode_field_(\d+)_(\d+)', d).groups())
        for b in range(w):
            owner[lo + b] = (k, b)

    def constant(pos):
        if enc.const_mask >> pos & 1:
            return enc.const_encoding_part >> pos & 1
        k, b = owner[pos]
        name = ins.operand_names[k]
        return fixed[name] >> b & 1 if name in fixed else None

    tokens, segments, bit = [], {}, {}
    pos = 31
    while pos >= 0:
        c = constant(pos)
        if c is not None:
            if not tokens or ':' in tokens[-1]:
                tokens.append('')
            tokens[-1] += str(c)
            bit[pos] = z3.BitVecVal(c, 1)
            pos -= 1
            continue
        k, b = owner[pos]
        n = 1
        while pos - n >= 0 and constant(pos - n) is None and owner[pos - n] == (k, b - n):
            n += 1
        name, w = ins.operand_names[k], ins.operand_sizes[k]
        seg = name if n == w else f'{name}_{b - n + 1}'
        var = segments[seg] = z3.BitVec(seg, n)
        tokens.append(f'{seg}:{n}')
        for i in range(n):
            bit[pos - i] = z3.Extract(n - 1 - i, n - 1 - i, var)
        pos -= n
    operands = []
    for k, d in enumerate(enc.decode):
        lo, w = map(int, re.fullmatch(r'decode_field_(\d+)_(\d+)', d).groups())
        bits = [bit[lo + b] for b in reversed(range(w))]
        operands.append(z3.simplify(z3.Concat(*bits)) if w > 1 else bits[0])
    return Pattern(' '.join(tokens), segments, operands)


def combos(ins: Instruction) -> List[Dict[str, int]]:
    """Register numbers to try: all different (even, so that pairs fit), each
    one 31 (SP or ZR) in turn, all the same."""
    regs = [n for n in ins.operand_names if n in REG_FIELDS]
    base = {n: 2 + 2 * i for i, n in enumerate(regs)}
    out = [base] + [{**base, n: 31} for n in regs] + ([{n: 4 for n in regs}] if len(regs) > 1 else [])
    return [dict(c) for c in dict.fromkeys(tuple(sorted(c.items())) for c in out)]


def selected(ins: Instruction) -> bool:
    """The instructions compared: those lira_smt models, without SVE/SME."""
    return in_scope(ins) and not any(a.startswith('instr-class.') and a.split('.')[1] in ('sve', 'sve2', 'mortlach')
                                     for a in ins.attributes)


# -----------------------------------------------------------------------------
# Isla runs

def isla_args(opcode: str, constraint: Optional[str], reset: List[str], registers=(), simplify=True) -> List[str]:
    args = ['-A', str(ARCH), '-C', str(CONFIG), '-T', '1', '--timeout', str(TIMEOUT), '--partial', '-i', opcode]
    if constraint:
        args += ['--instruction-constraint', constraint]
    for r in reset:
        args += ['--reset-constraint', r]
    for r in registers:
        args += ['-R', r]
    for f in isla_trace.UNPREDICTABLE + (isla_trace.OTHER_ERROR,):
        args += ['--trace-function', f]
    return args + (['-s'] if simplify else [])


def _footprint(pid: int) -> int:
    """The physical footprint of a process in bytes (macOS: with its
    compressed pages, which the resident size leaves out), 0 if unknown."""
    try:
        if sys.platform == 'darwin':
            buf = ctypes.create_string_buffer(512)
            if ctypes.CDLL('/usr/lib/libSystem.B.dylib').proc_pid_rusage(pid, 0, buf) == 0:   # RUSAGE_INFO_V0
                return int.from_bytes(buf.raw[72:80], 'little')                            # ri_phys_footprint
        else:
            return int(Path(f'/proc/{pid}/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    except (OSError, AttributeError, ValueError):
        pass
    return 0


def run_isla(args: List[str]) -> dict:
    """{'rc', 'out', 'err'} of isla-footprint, cached; rc 'timeout' or
    'memory' when the run was stopped at TIMEOUT or MEMORY_LIMIT."""
    st = ARCH.stat()
    key = hashlib.sha256(json.dumps([str(ARCH), st.st_size, st.st_mtime, config_digest(), args]).encode())
    path = CACHE / key.hexdigest()[:2] / (key.hexdigest() + '.json.gz')
    if path.exists():
        return json.loads(gzip.decompress(path.read_bytes()))
    with tempfile.TemporaryFile('w+') as out, tempfile.TemporaryFile('w+') as err:
        proc = subprocess.Popen([ISLA] + args, stdout=out, stderr=err, text=True)
        start, rc = time.monotonic(), None
        while (rc := proc.poll()) is None:
            if _footprint(proc.pid) > MEMORY_LIMIT or time.monotonic() - start > TIMEOUT + 60:
                rc = 'memory' if _footprint(proc.pid) > MEMORY_LIMIT else 'timeout'
                proc.kill()
                proc.wait()
                break
            time.sleep(0.5)
        out.seek(0)
        err.seek(0)
        res = {'rc': rc, 'out': out.read() if rc == 0 else '', 'err': err.read()[-4000:]}
    if isinstance(res['rc'], int) and res['rc'] < 0:          # killed by a signal: not a result
        res['err'] += f'\nkilled by signal {-res["rc"]}'
        return res
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(res).encode()))
    return res


# -----------------------------------------------------------------------------
# Comparison

@dataclass
class Case:
    """An instruction with fixed register numbers, ready to run."""
    ins: Instruction
    fixed: Dict[str, int]
    pat: Pattern = None
    lira: SymMachine = None
    constraint: z3.BoolRef = None
    assumptions: List[z3.BoolRef] = field(default_factory=list)
    reset: List[str] = field(default_factory=list)
    ranges: list = field(default_factory=list)       # address_ranges
    args: List[str] = None
    skip: Optional[str] = None


@dataclass
class Result:
    name: str
    fixed: Dict[str, int]
    status: str                  # equivalent, mismatch, unknown, isla-error, timeout, no-paths, skipped
    paths: int = 0
    compared: int = 0
    env_faults: int = 0
    detail: List[str] = field(default_factory=list)
    unpredictable: bool = False
    cex: Optional[tuple] = None      # (field values, register values) of a counterexample


def address_ranges(fixed: Dict[str, int]):
    """[(register, hi, lo, allowed values of bits hi:lo)] that keep a memory
    access below 2^48: the base (Rn, SP, or PC for literals) below 2^48; with a
    register offset Rm (extended, shifted by up to 4), the base in [2^46, 2^47)
    and Rm within +-2^40, or, when Rn is Rm, the register below 2^36 and
    positive as a W register."""
    rn, rm = fixed.get('Rn'), fixed.get('Rm')
    base = 'PC' if rn is None else 'SP' if rn == 31 else f'X{rn}'
    if rm is None or rm == 31:
        return [(base, 63, 48, [0])]
    if rm == rn:
        return [(base, 63, 36, [0]), (base, 31, 31, [0])]
    return [(base, 63, 46, [1]), (f'X{rm}', 63, 40, [0, (1 << 24) - 1])]


def make_case(arch, ins: Instruction, fixed: Dict[str, int]) -> Case:
    c = Case(ins, fixed)
    c.pat = pattern(ins, fixed)
    c.lira = SymMachine(arch)
    c.constraint = z3.simplify(SymMachine(arch).operand_constraint(ins, c.pat.operands))
    if z3.Solver().check(c.constraint) == z3.unsat:
        c.skip = 'register numbers not allowed by constraint_encode'
        return c
    try:
        c.lira.execute(ins, c.pat.operands)
    except OutOfScope as e:
        c.skip = f'out of scope: {e}'
        return c
    reset = c.reset
    if any(MEM_HOOKS.match(h) for h in uses(ins)[1]):
        # addresses below 2^48: no address size faults, which are the
        # environment's, and far fewer paths
        c.ranges = address_ranges(fixed)
        for r, hi, lo, values in c.ranges:
            sail = {'SP': 'SP_EL0', 'PC': '_PC'}.get(r, 'R' + r[1:])
            bits = z3.Extract(hi, lo, c.lira.input(r))
            w = hi - lo + 1
            lits = [f'#x{v:0{w // 4}x}' if w % 4 == 0 else f'#b{v:0{w}b}' for v in values]
            eqs = [f'(= ((_ extract {hi} {lo}) {sail}) {lit})' for lit in lits]
            reset.append(eqs[0] if len(eqs) == 1 else f'(or {" ".join(eqs)})')
            c.assumptions.append(z3.Or(*[bits == v for v in values]))
    con = None if z3.is_true(c.constraint) else isla_trace.to_isla(c.constraint)
    c.args = isla_args(c.pat.text, con, reset)
    return c


# -----------------------------------------------------------------------------
# What Isla cannot execute symbolically: a slice whose bounds are fields
# (EXTR) runs once per value of the fields, still a proof; real arithmetic
# (the ASL's UDIV and SDIV) runs on concrete samples, a test.

SYMBOLIC_LENGTH = 'Symbolic (bit)vector length'
UNIMPLEMENTED = 'error: Unimplemented'
ENUM_BITS = 8
SAMPLES = 24
EDGE64 = [0, 1, 2, 0x7f, 0x80, 0xff, 0x7fff_ffff, 0x8000_0000, 0xffff_ffff, 0x1_0000_0000,
          0x7fff_ffff_ffff_ffff, 0x8000_0000_0000_0000, 0xffff_ffff_ffff_ffff, 0xffff_ffff_8000_0000]


@dataclass
class Run:
    """One isla-footprint run of a case, under `extra`: the field and
    register values the run fixes."""
    label: str
    args: List[str]
    extra: List[z3.BoolRef] = field(default_factory=list)


def _concrete_text(pat: Pattern, values: Dict[str, int]) -> str:
    return re.sub(r'(\w+):(\d+)', lambda m: format(values[m[1]], f'0{m[2]}b'), pat.text)


def _register_values(case: Case, rng) -> Dict[str, int]:
    """Random (edge-biased) initial values of LIRA's inputs, within the
    case's address ranges."""
    values = {}
    for r in case.lira.inputs:
        if r == 'NZCV':
            values[r] = rng.getrandbits(4)
        elif r in STATE or r == 'PC':
            v = rng.choice(EDGE64 + [rng.getrandbits(64)] * 4)
            v = v & 0xffff_ffff_fffc if r == 'PC' else v
            for rr, hi, lo, allowed in case.ranges:
                if rr == r:
                    v = v & ~(((1 << (hi - lo + 1)) - 1) << lo) | rng.choice(allowed) << lo
            values[r] = v
    return values


def concrete_run(case: Case, assign: Dict[str, int], values: Dict[str, int], label: str) -> Run:
    """A run with the fields and LIRA's input registers set (-R)."""
    sets = []
    for r, v in values.items():
        if r == 'NZCV':
            sets += [f'PSTATE.{f}=0b{v >> (3 - i) & 1}' for i, f in enumerate(isla_trace.NZCV_FIELDS)]
        else:
            sets.append(f'{ {"SP": "SP_EL0", "PC": "_PC"}.get(r, "R" + r[1:]) }=0x{v:016x}')
    extra = [case.pat.segments[n] == v for n, v in assign.items()]
    extra += [initial(case.lira, r) == v for r, v in values.items()]
    return Run(label, isla_args(_concrete_text(case.pat, assign), None, case.reset, sets), extra)


def fallback_runs(case: Case, err: str, unknown=False, why=None) -> Optional[Tuple[str, str, List[Run]]]:
    """(mode, why, runs) for a case Isla could not run symbolically, or whose
    queries the solver could not decide (`unknown`)."""
    err = re.sub(r'\x1b\[[0-9;]*m', '', err)            # Isla colours its messages
    segs = case.pat.segments
    runs = []
    if SYMBOLIC_LENGTH in err and sum(v.size() for v in segs.values()) <= ENUM_BITS:
        for values in itertools.product(*[range(1 << v.size()) for v in segs.values()]):
            assign = dict(zip(segs, values))
            extra = [segs[n] == v for n, v in assign.items()]
            if z3.Solver().check(case.constraint, *extra) == z3.sat:
                runs.append(Run(str(assign), isla_args(_concrete_text(case.pat, assign), None, case.reset), extra))
        return 'enumerated', 'slice bounds are fields', runs
    if UNIMPLEMENTED in err or unknown:
        rng = random.Random(case.ins.name + str(case.fixed))
        while len(runs) < SAMPLES:
            assign = {n: rng.getrandbits(v.size()) for n, v in segs.items()}
            extra = [segs[n] == v for n, v in assign.items()]
            if z3.Solver().check(case.constraint, *extra) == z3.unsat:
                continue
            values = _register_values(case, rng)
            runs.append(concrete_run(case, assign, values,
                                     f'{assign} {dict((r, hex(v)) for r, v in values.items())}'))
        return 'sampled', why or ('solver timeout' if unknown else 'real arithmetic'), runs
    return None


def lira_exception(lira: SymMachine, kinds) -> z3.BoolRef:
    """LIRA's first exception is one of `kinds` ({kind: extra condition})."""
    taken, earlier = [], z3.BoolVal(False)
    for e in lira.exceptions:
        first = z3.And(e.cond, z3.Not(earlier))
        if e.kind in kinds:
            taken.append(z3.And(first, kinds[e.kind](e)))
        earlier = z3.Or(earlier, e.cond)
    return z3.Or(*taken) if taken else z3.BoolVal(False)


def initial(lira: SymMachine, r: str) -> z3.BitVecRef:
    return lira.input(r, z3.BitVecSort(4 if r == 'NZCV' else 64))


def finals(p: isla_trace.Path, lira: SymMachine):
    """(register, Sail value, LIRA value) of the registers either side writes."""
    lw = lira.written()
    return [(r, p.final.get(r, initial(lira, r)), lw.get(r, initial(lira, r)))
            for r in STATE if r in p.final or r in lw]


def agree_parts(p: isla_trace.Path, lira: SymMachine):
    """(conjuncts of Agree, whether the path is an environment fault) for a path."""
    if p.exception is None:
        no_exc = z3.Not(z3.Or(*[e.cond for e in lira.exceptions])) if lira.exceptions else z3.BoolVal(True)
        eqs = [s == lv for _, s, lv in finals(p, lira)]
        pc = p.next_pc if p.next_pc is not None else lira.input('PC') + 4
        # the memories are equal iff they are at a free address (extensionality)
        mem = z3.BoolVal(True) if p.mem_writes == 0 and not lira.writes else p.mem[ADDR] == lira.mem[ADDR]
        return [no_exc, *eqs, pc == lira.next_pc, mem], False
    esr = p.esr if p.esr is not None else z3.BitVecVal(0, 64)
    iss16 = z3.Extract(15, 0, esr)
    imm = lambda e: z3.BoolVal(True) if e.imm is None else z3.Extract(15, 0, z3.ZeroExt(16, e.imm)) == iss16  # noqa
    if p.exception == SVC:
        return [lira_exception(lira, {'svc': imm})], False
    if p.exception == BRK:
        return [lira_exception(lira, {'brk': imm})], False
    if p.exception == UNDEFINED:
        return [lira_exception(lira, {'undefined': lambda e: z3.BoolVal(True)})], False
    if p.exception == DATA_ABORT:
        alignment = z3.Extract(5, 0, esr) == DFSC_ALIGNMENT
        return [z3.If(alignment, lira_exception(lira, {'alignment': lambda e: z3.BoolVal(True)}), True)], True
    return [z3.BoolVal(False)], False


def agree(p: isla_trace.Path, lira: SymMachine):
    """(Agree formula, whether the path is an environment fault) for a path."""
    parts, env = agree_parts(p, lira)
    return z3.And(*parts), env


def describe(model: z3.ModelRef, case: Case, p: isla_trace.Path) -> List[str]:
    ev = lambda t: model.eval(t, model_completion=True)               # noqa: E731
    lira = case.lira
    out = ['fields: ' + ', '.join(f'{n}={ev(v)}' for n, v in case.pat.segments.items()) +
           f' (fixed {case.fixed}; Sail path {p.index}{", ConstrainUnpredictable" if p.unpredictable else ""})']
    out.append('inputs: ' + ', '.join(f'{k}={hex(ev(v).as_long())}' for k, v in sorted(lira.inputs.items())
                                      if k != 'MEM' and z3.is_bv(v)))
    if p.exception is not None:
        out.append(f'Sail: {p.exception} ESR={ev(p.esr) if p.esr is not None else "?"}')
    lexc = [f'{e.kind}' for e in lira.exceptions if z3.is_true(ev(e.cond))]
    out.append(f'LIRA exceptions: {lexc or "none"}')
    for r, s, lv in finals(p, lira):
        s, lv = ev(s).as_long(), ev(lv).as_long()
        if p.exception is None and s != lv:
            out.append(f'{r}: Sail {hex(s)} LIRA {hex(lv)}')
    if p.exception is None:
        s_pc = ev(p.next_pc if p.next_pc is not None else lira.input('PC') + 4).as_long()
        l_pc = ev(lira.next_pc).as_long()
        if s_pc != l_pc:
            out.append(f'next PC: Sail {hex(s_pc)} LIRA {hex(l_pc)}')
        if not z3.is_true(ev(p.mem[ADDR] == lira.mem[ADDR])):
            out.append(f'memory[{hex(ev(ADDR).as_long())}]: Sail {ev(p.mem[ADDR])} LIRA {ev(lira.mem[ADDR])}')
    if p.unmapped_writes:
        out.append(f'Sail also writes {p.unmapped_writes}')
    out.append('LIRA replay: ' + replay(model, case))
    return out


def replay(model: z3.ModelRef, case: Case) -> str:
    """Run the counterexample in lira_interp: it must give what the walker's
    terms give under the model (else the walker, not LIRA, is wrong)."""
    ev = lambda t: model.eval(t, model_completion=True)               # noqa: E731
    lira = case.lira
    init = lambda r: ev(initial(lira, r)).as_long()                   # noqa: E731
    mem = lira.input('MEM', MEM_SORT)
    byte = lambda a: ev(z3.Select(mem, z3.BitVecVal(a, 64))).as_long()  # noqa: E731
    ops = [ev(o).as_long() for o in case.pat.operands]
    got = concrete_step(lira.arch, case.ins, ops, [init(f'X{i}') for i in range(31)] + [init('SP')],
                        init('NZCV'), init('PC'), byte)
    first = next((e for e in lira.exceptions if z3.is_true(ev(e.cond))), None)
    if isinstance(got, Raised) or first:
        same = isinstance(got, Raised) and first and got.kind == first.kind
        return 'agrees' if same else f'walker {first and first.kind}, interpreter {getattr(got, "kind", None)}'
    x, nzcv, next_pc, written = got
    lw = lira.written()
    want = [ev(lw.get(r, initial(lira, r))).as_long() for r in STATE]
    if want != x[:31] + [x[31], nzcv]:
        return f'walker {[hex(v) for v in want]}, interpreter {[hex(v) for v in x + [nzcv]]}'
    if ev(lira.next_pc).as_long() != next_pc:
        return f'walker next PC {ev(lira.next_pc)}, interpreter {hex(next_pc)}'
    bad = [a for a, b in written.items() if ev(z3.Select(lira.mem, z3.BitVecVal(a, 64))).as_long() != b]
    return f'walker memory differs at {[hex(a) for a in bad[:4]]}' if bad else 'agrees'


def trace_vars(*es) -> List[z3.ExprRef]:
    """The variables of Isla traces (isla_vN) in the expressions."""
    return [v for v in isla_trace.consts(*es) if v.decl().name().startswith('isla_')]


def _eliminate(e: z3.BoolRef) -> z3.BoolRef:
    """`e` (an Exists) without its quantifier, when z3 can eliminate it."""
    try:
        return z3.TryFor(z3.Tactic('qe'), QE_TIMEOUT).apply(e).as_expr()
    except z3.Z3Exception:
        return e


def _exists(us: List[z3.ExprRef], e: z3.BoolRef) -> z3.BoolRef:
    """Exists us. e, without the quantifier when possible: z3's elimination,
    else, for one variable in an equation `s == t` (an UNKNOWN value written
    to a register), the disjunction of `e` with the variable replaced by each
    slice of `t` of its width (a witness; sound, as Agree only needs one)."""
    q = _eliminate(z3.Exists(us, e))
    if not z3.is_quantifier(q):
        return q
    if len(us) == 1 and z3.is_eq(e):
        u = us[0]
        a, b = e.arg(0), e.arg(1)
        s_, t = (a, b) if any(v.eq(u) for v in isla_trace.consts(a)) else (b, a)
        if not any(v.eq(u) for v in isla_trace.consts(t)) and z3.is_bv(t) and u.size() <= t.size():
            w = u.size()
            return z3.Or(*[z3.substitute(e, (u, z3.Extract(lo + w - 1, lo, t))) for lo in range(t.size() - w + 1)])
    return q


def fixed_choice(case: Case, paths: List[isla_trace.Path], extra=()):
    """(verdict, choice): whether LIRA always behaves as the Sail model does
    with one fixed value of its CONSTRAINED UNPREDICTABLE choices (the UNKNOWN
    enumeration values of the paths: paths are grouped by them, and the paths
    without a choice belong to every group); verdict True, False or None
    (undecided). A free value that only the results use (an UNKNOWN value)
    may be anything: Agree has it existentially quantified."""
    base = [case.constraint, *case.assumptions, *extra]
    deadline = time.monotonic() + CHOICE_BUDGET

    def query(*fs):
        left = deadline - time.monotonic()
        if left <= 0:
            return z3.unknown, None
        return solve(*fs, timeout=int(min(CHOICE_TIMEOUT, left * 1000)))

    prepared = []
    for p in paths:
        # the variables bound to the shared state are terms of it
        subs, rest = [], []
        for b in p.binds:
            lhs = b.arg(0)
            if z3.is_const(lhs) and lhs.decl().name().startswith('isla_') and \
                    not any(lhs.eq(v) for v, _ in subs):
                subs.append((lhs, b.arg(1)))
            else:
                rest.append(b)
        sub = (lambda e: z3.substitute(e, *subs)) if subs else (lambda e: e)
        cond = sub(z3.And(*p.cond, *rest))
        key = ()
        # the choices the path branches on (an UNKNOWN field of a fault record
        # it does not test is data, not a choice)
        names = {v.decl().name() for v in isla_trace.consts(cond)}
        choices = [c for c in p.choices if all(v.decl().name() in names for v in isla_trace.consts(c))]
        if choices:
            v, s = query(*base, cond)
            if v == z3.unknown:
                return None, None
            if v != z3.sat:
                continue
            values = [s.model().eval(sub(c), model_completion=True) for c in choices]
            key = tuple(map(str, values))
            cond = z3.And(cond, *[sub(c) == x for c, x in zip(choices, values)])
        in_cond = [v for v in trace_vars(cond) if v.decl().name() not in p.init_vars]
        if p.other_error or p.exception is None and p.unmapped_writes:
            parts = [z3.BoolVal(False)]
        else:
            parts = [sub(x) for x in agree_parts(p, case.lira)[0]]
        ok = []
        for part in parts:
            unknown = [v for v in trace_vars(part) if v.decl().name() not in p.init_vars and
                       not any(v.eq(u) for u in in_cond)]
            ok.append(_exists(unknown, part) if unknown else part)
        prepared.append((key, cond, z3.And(*ok)))
    verdict = False
    # a candidate is a path's choices; a path follows it when they agree on the
    # choices both make (an unaligned access makes one more than an aligned)
    follows = lambda key, choice: all(a == b for a, b in zip(key, choice))   # noqa: E731
    for choice in sorted({k for k, _, _ in prepared if k}, key=len, reverse=True) or [()]:
        good = True
        for key, cond, ok in prepared:
            if not follows(key, choice):
                continue
            v = query(*base, cond, z3.Not(ok))[0]
            if v == z3.sat:
                good = False
                break
            if v == z3.unknown:                    # cannot confirm this choice
                good = None
                break
        if good:
            return True, choice
        if good is None:
            verdict = None
    return verdict, None


def solve(*fs, timeout=SOLVER_TIMEOUT):
    """(verdict, solver) of the formulas, with a fresh solver: z3's one-shot
    bit-vector tactics are much faster than its incremental core."""
    s = z3.Solver()
    s.set('timeout', timeout)
    s.add(*fs)
    return s.check(), s


def compare(case: Case, res: dict, extra=()) -> Result:
    r = Result(case.ins.name, case.fixed, 'equivalent')
    if res['rc'] in ('timeout', 'memory') or 'Timeout' in res['err'] and not res['out']:
        r.status = 'timeout' if res['rc'] != 'memory' else 'isla-memory'
        return r
    if res['rc'] != 0:
        r.status, r.detail = 'isla-error', res['err'].strip().splitlines()[-3:]
        return r
    paths = isla_trace.paths(res['out'], case.lira.inputs, case.pat.segments)
    r.paths = len(paths)
    for p in paths:
        base = [case.constraint, *case.assumptions, *extra, *p.cond, *p.binds]
        problem = ('ends in a Sail error (SEE, reserved, UNPREDICTABLE)' if p.other_error else
                   f'writes {p.unmapped_writes}' if p.exception is None and p.unmapped_writes else None)
        if problem:
            if solve(*base)[0] != z3.unsat:
                r.status = 'mismatch'
                r.unpredictable |= p.unpredictable
                r.detail.append(f'Sail path {p.index} {problem}')
            continue
        ok, env = agree(p, case.lira)
        verdict, s = solve(*base, z3.Not(ok))
        if verdict == z3.unknown:
            r.status = 'unknown'
            r.detail.append(f'Sail path {p.index}: solver {s.reason_unknown()}')
            continue
        if verdict == z3.unsat:
            if solve(*base)[0] == z3.unsat:     # the bindings contradict the path: a reader bug
                r.status = 'mismatch'
                r.detail.append(f'Sail path {p.index} is infeasible over the shared state')
                continue
            if env and solve(*base, z3.Extract(5, 0, p.esr) != DFSC_ALIGNMENT)[0] != z3.unsat:
                r.env_faults += 1
            r.compared += 1
            continue
        r.compared += 1
        r.status = 'mismatch'
        r.unpredictable |= p.unpredictable
        m = s.model()
        r.detail += describe(m, case, p)
        r.cex = ({n: m.eval(v, model_completion=True).as_long() for n, v in case.pat.segments.items()},
                 {k: m.eval(initial(case.lira, k), model_completion=True).as_long()
                  for k in case.lira.inputs if k in STATE or k == 'PC'})
        break
    if r.status == 'mismatch' and r.unpredictable:
        # CONSTRAINED UNPREDICTABLE: LIRA needs to make one of the choices
        verdict, choice = fixed_choice(case, paths, extra)
        if verdict:
            r.status = 'equivalent'
            r.detail = [f'LIRA makes the CONSTRAINED UNPREDICTABLE choice {choice}']
            r.cex = None
        elif verdict is None:
            r.status = 'unknown'
            r.detail.insert(0, 'with the UNPREDICTABLE choices: solver unknown')
        else:
            r.detail.insert(0, 'no fixed CONSTRAINED UNPREDICTABLE choice of the Sail model agrees:')
    if r.status == 'equivalent' and r.compared == 0:
        r.status = 'no-paths'
    return r


def merge(case: Case, mode: str, why: str, runs: List[Run], results: List[Result]) -> Result:
    """One result for the runs of a fallback."""
    r = Result(case.ins.name, case.fixed, 'equivalent' if mode == 'enumerated' else 'sampled')
    r.detail = [f'{mode}: {len(runs)} runs ({why})']
    for run, x in zip(runs, results):
        r.paths += x.paths
        r.compared += x.compared
        r.env_faults += x.env_faults
        r.unpredictable |= x.unpredictable
        if x.status not in ('equivalent', 'no-paths') and r.status in ('equivalent', 'sampled'):
            r.status = x.status
            r.detail += [f'run {run.label}:'] + x.detail
    if not runs:
        r.status = 'no-paths'
    return r


def run_case(c: Case) -> Result:
    """Isla, the comparison, the fallbacks and the check without -s of one case."""
    if c.skip:
        return Result(c.ins.name, c.fixed, 'skipped', detail=[c.skip])
    res = run_isla(c.args)
    if res['rc'] == 'memory':
        fb = fallback_runs(c, '', unknown=True, why=f'Isla needs over {MEMORY_LIMIT / 2**30:.0f} GB')
    else:
        fb = fallback_runs(c, res['err']) if res['rc'] not in (0, 'timeout') else None
    if not fb:
        r = compare(c, res)
        # samples help a query the solver cannot decide, not the choices of
        # CONSTRAINED UNPREDICTABLE (every sample would make them again)
        if r.status == 'unknown' and not r.unpredictable:
            fb = fallback_runs(c, '', unknown=True)
    if fb:
        mode, why, runs = fb
        r = merge(c, mode, why, runs, [compare(c, run_isla(run.args), run.extra) for run in runs])
    # a mismatch must not be the work of Isla's simplification of symbolic
    # terms (-s): it must also be one with the counterexample's fields and
    # registers concrete
    if r.status == 'mismatch' and r.cex:
        run = concrete_run(c, *r.cex, 'counterexample')
        x = compare(c, run_isla(run.args), run.extra)
        if x.status == 'mismatch':
            r.detail.append('confirmed by a concrete Isla run')
        else:
            r.status = 'isla-simplifier'
            r.detail.insert(0, f'a concrete Isla run of the counterexample: {x.status}')
    return r


def run_cases(cases: List[Case]) -> List[Result]:
    """Run cases in this process (for instructions not in aarch64.yaml)."""
    return [run_case(c) for c in cases]


_WORKER = {}


def _work(item) -> Result:
    name, fixed = item
    if not _WORKER:
        from python.lira.arch_ser_yaml import read_arch
        arch = read_arch(HERE.parent / 'aarch64.yaml')
        _WORKER.update(arch=arch, ins={i.name: i for i in arch.instructions})
    return run_case(make_case(_WORKER['arch'], _WORKER['ins'][name], fixed))


def compare_all(arch, only=None, jobs: int = JOBS, progress=None) -> List[Result]:
    """Compare the selected instructions (names matching `only`), every
    register choice in its own worker process (z3 and Isla are CPU-bound)."""
    items = [(ins.name, f) for ins in arch.instructions
             if selected(ins) and (only is None or only.search(ins.name)) for f in combos(ins)]
    results = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_work, it): k for k, it in enumerate(items)}
        for f in concurrent.futures.as_completed(futures):
            results[futures[f]] = r = f.result()
            if progress:
                progress(r, len(results), len(items))
    return [results[k] for k in range(len(items))]


# -----------------------------------------------------------------------------
# Command line

def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m archs.aarch64.tests.isla_oracle')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prepare', help='patch and preprocess the Sail model')
    p.add_argument('ir', type=Path)
    p.add_argument('-o', '--out', type=Path)
    c = sub.add_parser('compare', help='compare instructions')
    c.add_argument('--only', help='instruction name regex')
    c.add_argument('--report', type=Path, help='write a Markdown report')
    c.add_argument('-j', '--jobs', type=int, default=JOBS)
    a = ap.parse_args(argv)
    if a.cmd == 'prepare':
        out = a.out or a.ir.with_name('lira-' + a.ir.stem + '.irx')
        prepare(a.ir, out)
        print(f'export LIRA_ISLA_ARCH={out}')
        return 0
    if not available():
        sys.exit('needs isla-footprint ($ISLA_FOOTPRINT) and the prepared model ($LIRA_ISLA_ARCH)')
    check_prepared()
    from python.lira.arch_ser_yaml import read_arch
    arch = read_arch(HERE.parent / 'aarch64.yaml')

    def progress(r, done, total):
        print(f'[{done}/{total}] {r.name} {r.fixed} {r.status} paths={r.paths}', flush=True)
        for line in r.detail:
            print('    ' + line, flush=True)
    results = compare_all(arch, re.compile(a.only) if a.only else None, a.jobs, progress)
    by = {}
    for r in results:
        by.setdefault(r.status, set()).add(r.name)
    print({k: len(v) for k, v in by.items()})
    if a.report:
        a.report.write_text(report(results))
    return 0 if by.keys() <= set(PASS) else 1


def report(results: List[Result]) -> str:
    lines = ['| instruction | registers | status | paths | compared | env faults | detail |',
             '|---|---|---|---|---|---|---|']
    for r in sorted(results, key=lambda r: (r.status == 'equivalent', r.name)):
        lines.append(f'| {r.name} | {r.fixed} | {r.status} | {r.paths} | {r.compared} | {r.env_faults} | '
                     + '<br>'.join(d.replace('|', '\\|') for d in r.detail) + ' |')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    sys.exit(main())
