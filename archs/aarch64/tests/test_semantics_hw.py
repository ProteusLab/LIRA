"""Differential test: LIRA semantics vs. the host CPU (arm64 only).

Every case is one encoded instruction wrapped in a stub that loads x0..x7 and
NZCV from a state block, executes the word and stores the state back. The same
word is decoded with the LIRA decode snippets and run by the reference
interpreter; registers, flags and memory must match.
"""
import ctypes
import platform
import random
import shutil
import subprocess
import sys

import pytest

from .conftest import sample_operands

pytestmark = pytest.mark.skipif(
    platform.machine() not in ('arm64', 'aarch64') or shutil.which('clang') is None,
    reason='needs an AArch64 host with clang')

# PC-changing and system instructions are covered by test_semantics.py
SKIP_FILES = ('B_', 'BL_', 'BR_', 'BLR_', 'RET_', 'CBZ_', 'CBNZ_', 'TBZ_', 'TBNZ_', 'SVC_')
REG_FIELDS = ('Rd', 'Rn', 'Rm', 'Ra', 'Rt', 'Rt2')
EDGE = [0, 1, 2, 0x7F, 0x80, 0xFF, 0x7FFF, 0x8000, 0xFFFF, 0x7FFFFFFF, 0x80000000,
        0xFFFFFFFF, 0x100000000, 0x7FFFFFFFFFFFFFFF, 0x8000000000000000,
        0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF80000000]
CASES_PER_INSN = 6
STATES_PER_CASE = 12
MEM_SIZE, MEM_BASE_OFF = 8192, 4096
M64 = (1 << 64) - 1


def _is_mem(ins):
    return '_ldst' in ins.name


def _pick_operands(machine, ins, rng):
    regs = rng.sample(range(8), 6)
    fixed = {n: regs[i] for i, n in enumerate(REG_FIELDS) if n in ins.operand_names}
    if _is_mem(ins):
        for f, lim in (('imm12', 64), ('imm9', 512), ('imm7', 128)):
            if f in ins.operand_names:
                fixed[f] = rng.randrange(lim)
    return sample_operands(machine, ins, rng, fixed)


def _stub(label, word):
    return f"""
.globl _{label}
.p2align 2
_{label}:
    mov x16, x0
    ldr x17, [x16, #64]
    msr nzcv, x17
    ldp x0, x1, [x16, #0]
    ldp x2, x3, [x16, #16]
    ldp x4, x5, [x16, #32]
    ldp x6, x7, [x16, #48]
    adr x17, 1f
    str x17, [x16, #72]
1:  .inst {word:#010x}
    stp x0, x1, [x16, #0]
    stp x2, x3, [x16, #16]
    stp x4, x5, [x16, #32]
    stp x6, x7, [x16, #48]
    mrs x17, nzcv
    str x17, [x16, #64]
    ret
"""


@pytest.fixture(scope='module')
def cases(arch, tmp_path_factory):
    from .lira_interp import Machine
    machine = Machine(arch)
    rng = random.Random(7)
    cases = []
    for ins in arch.instructions:
        if ins.name.startswith(SKIP_FILES) or 'loadlit' in ins.name:
            continue
        for _ in range(CASES_PER_INSN):
            ops = _pick_operands(machine, ins, rng)
            cases.append((f'case_{len(cases)}', ins, ops, machine.encode(ins, ops)))
    d = tmp_path_factory.mktemp('hw')
    (d / 'cases.s').write_text('.text\n' + ''.join(_stub(l, w) for l, _, _, w in cases))
    cc = ['xcrun', 'clang'] if sys.platform == 'darwin' else ['clang']
    subprocess.run([*cc, '-shared', '-o', d / 'cases.dylib', d / 'cases.s'], check=True)
    lib = ctypes.CDLL(str(d / 'cases.dylib'))
    return [(getattr(lib, l), ins, ops, w) for l, ins, ops, w in cases]


def _random_state(rng, ins, ops, mem_addr):
    regs = [rng.choice(EDGE) if rng.random() < 0.3 else rng.getrandbits(64) for _ in range(8)]
    if _is_mem(ins):
        names = dict(zip(ins.operand_names, ops))
        regs[names['Rn']] = mem_addr + MEM_BASE_OFF
        if 'Rm' in names:
            regs[names['Rm']] = rng.randrange(256)
    return regs, rng.getrandbits(4) << 28


def interp_step(arch, ins, word, x, nzcv, pc, mem_base, mem_init):
    """Run one instruction word in the reference interpreter with memory
    [mem_base, mem_base + len(mem_init)). Returns (x, nzcv, memory, next_pc)."""
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
    m.regs['X'][:] = x
    m.regs['NZCV'][0] = nzcv
    m.execute(ins, m.decode(ins, word))
    return list(m.regs['X']), m.regs['NZCV'][0], bytes(smem), branch[-1] if branch else pc + 4


def test_semantics_match_hardware(arch, cases):
    rng = random.Random(11)
    mem = (ctypes.c_uint8 * MEM_SIZE)()
    base = ctypes.addressof(mem)
    failures = []
    for fn, ins, ops, word in cases:
        for _ in range(STATES_PER_CASE):
            regs, nzcv = _random_state(rng, ins, ops, base)
            init_mem = bytes(rng.getrandbits(8) for _ in range(MEM_SIZE))
            ctypes.memmove(mem, init_mem, MEM_SIZE)
            state = (ctypes.c_uint64 * 10)(*regs, nzcv, 0)
            fn(state)
            hw_regs, hw_nzcv, pc = list(state[:8]), state[8] >> 28, state[9]
            hw_mem = bytes(mem)

            lira_x, lira_nzcv, smem, _ = interp_step(arch, ins, word, regs + [0] * 24, nzcv >> 28,
                                                      pc, base, init_mem)
            got = (lira_x[:8], lira_nzcv, smem)
            if got != (hw_regs, hw_nzcv, hw_mem):
                failures.append((ins.name, hex(word), dict(zip(ins.operand_names, ops)),
                                 [hex(r) for r in regs], hex(nzcv >> 28),
                                 'hw', [hex(r) for r in hw_regs], hex(hw_nzcv),
                                 'lira', [hex(r) for r in got[0]], hex(got[1]),
                                 'mem differs' if got[2] != hw_mem else ''))
                break
    assert not failures, '\n'.join(map(str, failures[:20])) + f'\n({len(failures)} failing cases)'
