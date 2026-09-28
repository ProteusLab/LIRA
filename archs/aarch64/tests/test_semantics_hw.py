"""Differential test: LIRA semantics vs. the host CPU (arm64 only).

Every case is one encoded instruction wrapped in a stub that loads x0..x7,
q0..q7, NZCV, FPCR and FPSR from a state block, executes the word and stores
the state back. The same word is decoded with the LIRA decode snippets and run
by the reference interpreter; registers, flags and memory must match.
"""
import ctypes
import platform
import random
import shutil
import struct
import subprocess
import sys

import re

import pytest

from .conftest import sample_operands

pytestmark = pytest.mark.skipif(
    platform.machine() not in ('arm64', 'aarch64') or shutil.which('clang') is None,
    reason='needs an AArch64 host with clang')

# PC-changing and system instructions are covered by test_semantics.py
SKIP_FILES = ('B_', 'BL_', 'BR_', 'BLR_', 'RET_', 'CBZ_', 'CBNZ_', 'TBZ_', 'TBNZ_', 'SVC_')
# Not comparable on the host: features the CPU lacks (CSSC, HBC, MOPS), PAC
# values (implementation-defined algorithm, kernel keys) and instructions whose
# effect is the environment's (exceptions, system registers, SYS, waits)
HW_SKIP = re.compile(
    r'^(ABS|CNT|CTZ)_(32|64)_dp_1src|^(SMAX|SMIN|UMAX|UMIN)_\w+_(minmax_imm|dp_2src)|^BC_|'
    r'^(CPY|SET[PME])|^(PAC|AUT|XPAC|BLRA|BRA|RETA|ERET|LDRA)|'
    r'^(HINT|YIELD|WFE|WFI|SEV|SEVL|WFET|WFIT|BRK|HLT|HVC|SMC|UDF|DCPS|DRPS|SYS|SYSL)_|'
    r'^MSR_SI_|_systemmove_SYSREG$')
REG_FIELDS = ('Rd', 'Rn', 'Rm', 'Ra', 'Rt', 'Rt2', 'Rs')
EDGE = [0, 1, 2, 0x7F, 0x80, 0xFF, 0x7FFF, 0x8000, 0xFFFF, 0x7FFFFFFF, 0x80000000,
        0xFFFFFFFF, 0x100000000, 0x7FFFFFFFFFFFFFFF, 0x8000000000000000,
        0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF80000000]
CASES_PER_INSN = 6
STATES_PER_CASE = 12
MEM_SIZE, MEM_BASE_OFF = 8192, 4096
M64 = (1 << 64) - 1

# State block layout (8-byte words): x0..x7, nzcv, pc, fpcr, fpsr, q0..q7 (2 words each)
S_NZCV, S_PC, S_FPCR, S_FPSR, S_Q = 8, 9, 10, 11, 12
STATE_WORDS = S_Q + 16
FPCR_RANDOM = (3 << 22) | (1 << 24) | (1 << 19) | (1 << 25)    # RMode, FZ, FZ16, DN
FPSR_MASK = 0x0800009F


def _fp_specials(n):
    e, f = {16: (5, 10), 32: (8, 23), 64: (11, 52)}[n]
    inf = ((1 << e) - 1) << f
    one = ((1 << (e - 1)) - 1) << f
    vals = [0, inf, inf | (1 << (f - 1)), inf | 1, inf | (1 << (f - 1)) | 5,   # 0, inf, qNaN, sNaN
            1, (1 << f) - 1, 1 << f, one, one | 1, one + (1 << f),            # denormals, 1.0, 2.0
            inf - 1, (one + (1 << f)) | (1 << (f - 1)),                       # max, 3.0
            ((1 << (e - 1)) + f) << f, (((1 << (e - 1)) + f) << f) | 1,        # 2^(F+1) (+ulp)
            (((1 << (e - 1)) - 2 + f) << f) | ((1 << f) - 1)]                  # near integer
    return [v | (s << (n - 1)) for v in vals for s in (0, 1)]


SPECIALS = {n: _fp_specials(n) for n in (16, 32, 64)}


def random_v(rng):
    """128-bit register value whose low bits are an interesting FP number."""
    v = rng.getrandbits(128)
    r = rng.random()
    if r < 0.6:
        n = rng.choice((16, 32, 64))
        low = rng.choice(SPECIALS[n]) if rng.random() < 0.6 else rng.getrandbits(n)
        v = (v >> n << n) | low
    elif r < 0.7:
        v = struct.unpack('<Q', struct.pack('<d', rng.uniform(-1e6, 1e6)))[0] | (v >> 64 << 64)
    return v


def _is_mem(ins):
    return any(k in ins.name for k in ('_ldst', 'asisdls', 'comswap', 'memop', 'ldapstl'))


def _multi_reg(ins):
    """Instructions using up to 4 consecutive V registers from Rt / Rn."""
    return 'asisdls' in ins.name or 'asimdtbl' in ins.name


def _pick_operands(machine, ins, rng):
    regs = rng.sample(range(8), 7)
    fixed = {n: regs[i] for i, n in enumerate(REG_FIELDS) if n in ins.operand_names}
    if _multi_reg(ins):                     # keep Vt..Vt+3 / Vn..Vn+3 within v0..v7
        fixed['Rt' if 'Rt' in fixed else 'Rn'] = rng.randrange(4)
        if 'Rt' in fixed and 'Rn' in fixed:
            fixed['Rn'] = rng.choice([r for r in range(8) if r != fixed['Rt']])
        if 'Rm' in fixed:
            fixed['Rm'] = rng.choice([r for r in range(8) if r not in (fixed.get('Rn'), fixed.get('Rt'))])
    if 'comswappr' in ins.name:              # CASP: even pairs Rs:Rs+1, Rt:Rt+1
        rs, rt = rng.sample((0, 2, 4, 6), 2)
        fixed.update(Rs=rs, Rt=rt, Rn=rng.choice([r for r in range(8) if r not in (rs, rs + 1, rt, rt + 1)]))
    if 'M' in ins.operand_names and ins.name.endswith(('2S', '4S', '_S')):
        fixed['M'] = 0                       # Rm = M:Rm must stay within v0..v7
    if _is_mem(ins):
        for f, lim in (('imm12', 64), ('imm9', 512), ('imm7', 64)):
            if f in ins.operand_names:
                fixed[f] = rng.randrange(lim)
        if 'ldapstl' in ins.name:            # ordered: stay within 16 bytes (no alignment fault)
            fixed['imm9'] = rng.randrange(32) * 16
    return sample_operands(machine, ins, rng, fixed)


def _stub(label, word):
    return f"""
.globl _{label}
.p2align 2
_{label}:
    clrex
    mov x16, x0
    ldr x17, [x16, #{8 * S_NZCV}]
    msr nzcv, x17
    ldr x17, [x16, #{8 * S_FPCR}]
    msr fpcr, x17
    ldr x17, [x16, #{8 * S_FPSR}]
    msr fpsr, x17
    ldp q0, q1, [x16, #{8 * S_Q}]
    ldp q2, q3, [x16, #{8 * S_Q + 32}]
    ldp q4, q5, [x16, #{8 * S_Q + 64}]
    ldp q6, q7, [x16, #{8 * S_Q + 96}]
    ldp x0, x1, [x16, #0]
    ldp x2, x3, [x16, #16]
    ldp x4, x5, [x16, #32]
    ldp x6, x7, [x16, #48]
    adr x17, 1f
    str x17, [x16, #{8 * S_PC}]
1:  .inst {word:#010x}
    stp x0, x1, [x16, #0]
    stp x2, x3, [x16, #16]
    stp x4, x5, [x16, #32]
    stp x6, x7, [x16, #48]
    stp q0, q1, [x16, #{8 * S_Q}]
    stp q2, q3, [x16, #{8 * S_Q + 32}]
    stp q4, q5, [x16, #{8 * S_Q + 64}]
    stp q6, q7, [x16, #{8 * S_Q + 96}]
    mrs x17, nzcv
    str x17, [x16, #{8 * S_NZCV}]
    mrs x17, fpcr
    str x17, [x16, #{8 * S_FPCR}]
    mrs x17, fpsr
    str x17, [x16, #{8 * S_FPSR}]
    msr fpcr, xzr
    msr fpsr, xzr
    ret
"""


@pytest.fixture(scope='module')
def cases(arch, tmp_path_factory):
    return build_cases(arch, tmp_path_factory.mktemp('hw'))


def build_cases(arch, d):
    """Encode sample instructions and compile them into hardware stubs."""
    from .lira_interp import Machine
    machine = Machine(arch)
    rng = random.Random(7)
    cases = []
    for ins in arch.instructions:
        if ins.name.startswith(SKIP_FILES) or 'loadlit' in ins.name or HW_SKIP.search(ins.name):
            continue
        for _ in range(CASES_PER_INSN):
            ops = _pick_operands(machine, ins, rng)
            cases.append((f'case_{len(cases)}', ins, ops, machine.encode(ins, ops)))
    (d / 'cases.s').write_text('.text\n' + ''.join(_stub(l, w) for l, _, _, w in cases))
    cc = ['xcrun', 'clang'] if sys.platform == 'darwin' else ['clang']
    subprocess.run([*cc, '-shared', '-o', d / 'cases.dylib', d / 'cases.s'], check=True)
    lib = ctypes.CDLL(str(d / 'cases.dylib'))
    out = [(getattr(lib, l), ins, ops, w) for l, ins, ops, w in cases]
    unimplemented = _host_unimplemented(out)
    return [c for c in out if c[1].name not in unimplemented]


HOST_UNIMPLEMENTED: set = set()


def _host_unimplemented(cases):
    """Instructions the host CPU does not implement (SIGILL), probed once each
    in a forked child with a harmless state."""
    import os
    import signal
    seen = {}
    mem = (ctypes.c_uint8 * MEM_SIZE)()
    for fn, ins, ops, word in cases:
        if ins.name in seen:
            continue
        st = random_state(random.Random(0), ins, ops, ctypes.addressof(mem))
        pid = os.fork()
        if pid == 0:
            try:
                import faulthandler
                faulthandler.disable()                           # no crash report
                os.dup2(os.open(os.devnull, os.O_WRONLY), 2)
                run_hw(fn, st)
            finally:
                os._exit(0)
        _, status = os.waitpid(pid, 0)
        seen[ins.name] = os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGILL
    HOST_UNIMPLEMENTED.update(n for n, ill in seen.items() if ill)
    return HOST_UNIMPLEMENTED


def random_state(rng, ins, ops, mem_addr):
    """dict with X (8 regs), V (8 regs), NZCV, FPCR, FPSR."""
    x = [rng.choice(EDGE) if rng.random() < 0.3 else rng.getrandbits(64) for _ in range(8)]
    if _is_mem(ins):
        names = dict(zip(ins.operand_names, ops))
        x[names['Rn']] = mem_addr + MEM_BASE_OFF
        if 'Rm' in names:
            x[names['Rm']] = rng.randrange(256)
    fpcr = rng.getrandbits(32) & FPCR_RANDOM if rng.random() < 0.6 else 0
    fpsr = rng.getrandbits(32) & FPSR_MASK if rng.random() < 0.3 else 0
    return {'X': x, 'V': [random_v(rng) for _ in range(8)], 'NZCV': rng.getrandbits(4),
            'FPCR': fpcr, 'FPSR': fpsr}


def run_hw(fn, st):
    words = list(st['X']) + [st['NZCV'] << 28, 0, st['FPCR'], st['FPSR']]
    for v in st['V']:
        words += [v & M64, v >> 64]
    block = (ctypes.c_uint64 * STATE_WORDS)(*words)
    fn(block)
    out = {'X': list(block[:8]), 'NZCV': block[S_NZCV] >> 28, 'FPCR': block[S_FPCR],
           'FPSR': block[S_FPSR],
           'V': [block[S_Q + 2 * i] | (block[S_Q + 2 * i + 1] << 64) for i in range(8)]}
    return out, block[S_PC]


class AlignmentFault(Exception):
    pass


def check_alignment(addr, size, exclusive):
    """Exclusives are naturally aligned; ordered and atomic accesses stay
    within 16 bytes (FEAT_LSE2)."""
    if not (addr % size == 0 if exclusive else addr % 16 + size <= 16):
        raise AlignmentFault(f'{size}-byte access at {addr:#x}')


def interp_step(arch, ins, word, st, pc, mem_base, mem_init):
    """Run one instruction word in the reference interpreter with memory
    [mem_base, mem_base + len(mem_init)). `st` has 8 or 32 X/V registers.
    Returns (state, memory, next_pc)."""
    from .lira_interp import Machine
    m = Machine(arch)
    smem = bytearray(mem_init)
    branch = []

    def rd(n):
        def f(addr):
            o = addr - mem_base
            assert 0 <= o and o + n // 8 <= len(smem), hex(addr)
            return [int.from_bytes(smem[o:o + n // 8], 'little')]
        return f

    def wr(n):
        def f(addr, v):
            o = addr - mem_base
            assert 0 <= o and o + n // 8 <= len(smem), hex(addr)
            smem[o:o + n // 8] = v.to_bytes(n // 8, 'little')
        return f

    for n in (8, 16, 32, 64, 128):
        m.env[f'mem_read_{n}'], m.env[f'mem_write_{n}'] = rd(n), wr(n)
    m.env['pc_read'] = lambda: [pc]
    m.env['pc_write'] = lambda t: branch.append(t)
    m.env['supervisor_call'] = lambda imm: None
    monitor = []                                  # single-core exclusive monitor
    m.env['exclusive_mark'] = lambda a, n: monitor.__setitem__(slice(None), [(a, n)])
    m.env['exclusive_clear'] = lambda: monitor.clear()

    def check(a, n):
        ok = monitor == [(a, n)]
        monitor.clear()
        return [int(ok)]
    m.env['exclusive_check'] = check
    m.env['check_alignment'] = check_alignment
    for name in ('barrier', 'hint', 'branch_target', 'wait_timeout'):
        m.env[name] = lambda *a: None
    for k in ('X', 'V'):                         # descriptions may lack V/FPCR/FPSR
        if k in m.regs:
            m.regs[k][:len(st[k])] = st[k]
    for k in ('NZCV', 'FPCR', 'FPSR'):
        if k in m.regs:
            m.regs[k][0] = st[k]
    m.execute(ins, m.decode(ins, word))
    out = dict(st)
    for k in ('X', 'V'):
        if k in m.regs:
            out[k] = list(m.regs[k][:len(st[k])])
    for k in ('NZCV', 'FPCR', 'FPSR'):
        if k in m.regs:
            out[k] = m.regs[k][0]
    return out, bytes(smem), branch[-1] if branch else pc + 4


def diff_state(a, b):
    d = []
    for k in ('X', 'V'):
        d += [f'{k}{i}: {x:#x} vs {y:#x}' for i, (x, y) in enumerate(zip(a[k], b[k])) if x != y]
    d += [f'{k}: {a[k]:#x} vs {b[k]:#x}' for k in ('NZCV', 'FPCR', 'FPSR') if a[k] != b[k]]
    return d


def test_semantics_match_hardware(arch, cases):
    rng = random.Random(11)
    mem = (ctypes.c_uint8 * MEM_SIZE)()
    base = ctypes.addressof(mem)
    failures = []
    for fn, ins, ops, word in cases:
        for _ in range(STATES_PER_CASE):
            st = random_state(rng, ins, ops, base)
            init_mem = bytes(rng.getrandbits(8) for _ in range(MEM_SIZE))
            ctypes.memmove(mem, init_mem, MEM_SIZE)
            hw, pc = run_hw(fn, st)
            hw_mem = bytes(mem)
            got, smem, _ = interp_step(arch, ins, word, st, pc, base, init_mem)
            d = diff_state(hw, got) + (['memory'] if smem != hw_mem else [])
            if d:
                failures.append((ins.name, hex(word), dict(zip(ins.operand_names, ops)),
                                 {k: ([hex(v) for v in st[k]] if isinstance(st[k], list) else hex(st[k]))
                                  for k in st}, 'hw vs lira:', d))
                break
    if HOST_UNIMPLEMENTED:
        print(f'\nnot implemented by the host (skipped): {" ".join(sorted(HOST_UNIMPLEMENTED))}')
    summary = ' '.join(sorted({f[0] for f in failures}))
    assert not failures, '\n'.join(map(str, failures[:20])) + f'\n({len(failures)} failing cases)\n' + summary
