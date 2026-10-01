"""Differential test of the SVE instructions: LIRA semantics vs. QEMU.

The host CPU may lack SVE, so the reference is `qemu-system-aarch64 -cpu max`
running a bare-metal image at EL1: it sets the vector length (ZCR_EL1), enables
an identity-mapped MMU (Normal memory, so SVE accesses need no alignment), and
runs one stub per (case, state). Each stub loads x0..x7, z0..z7, p0..p7, FFR,
NZCV, FPCR and FPSR from a state block, executes the word and stores the state
back; a synchronous exception is recorded (ESR) and the word skipped. The
blocks come back through semihosting and are compared with the reference
interpreter run at the same VQ.

Needs qemu-system-aarch64, a clang that targets aarch64 and ld.lld.
$LIRA_SVE_VQS selects the vector lengths (in quadwords, default `1,4`) and
$LIRA_SVE_ONLY (a regex) the instructions.
"""
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import sample_operands
from .test_programs import CC, LD
from .test_semantics_hw import EDGE, SPECIALS

QEMU = shutil.which('qemu-system-aarch64')
VQS = [int(v) for v in os.environ.get('LIRA_SVE_VQS', '1,4').split(',')]
ONLY = re.compile(os.environ.get('LIRA_SVE_ONLY', ''))     # instruction name filter

pytestmark = pytest.mark.skipif(QEMU is None or CC is None or LD is None,
                                reason='needs qemu-system-aarch64, aarch64 clang and ld.lld')

CASES_PER_INSN = 6
STATES_PER_CASE = 8
M64 = (1 << 64) - 1

# State block (bytes): x0..x7, NZCV, FPCR, FPSR, fault ESR, then z0..z7
# (VL / 8 bytes each), p0..p7 and FFR (16-byte aligned slots of VL / 64 bytes)
S_X, S_NZCV, S_FPCR, S_FPSR, S_FAULT = 0, 64, 72, 80, 88
S_Z = 128


class Layout:
    def __init__(self, vq):
        self.zb, self.pb = 16 * vq, 2 * vq
        self.zslot, self.pslot = 16 * vq, max(16, 2 * vq)
        self.p = S_Z + 8 * self.zslot
        self.ffr = self.p + 8 * self.pslot
        self.size = (self.ffr + self.pslot + 63) // 64 * 64

    def z(self, i):
        return S_Z + self.zslot * i

    def pr(self, i):
        return self.p + self.pslot * i

FPCR_RANDOM = (3 << 22) | (1 << 24) | (1 << 19) | (1 << 25)
FPSR_MASK = 0x0800009F

REG_FIELDS = {'Zd', 'Zn', 'Zm', 'Za', 'Zda', 'Zdn', 'Pd', 'Pg', 'Pn', 'Pm', 'Pdm', 'Pdn', 'Pv',
              'Rd', 'Rn', 'Rm', 'Rdn', 'Vn'}

RAM, LOAD = 0x40000000, 0x40080000

START = f"""
.section .text.start, "ax"
.globl _start
_start:
    ldr x0, =__stack_top
    mov sp, x0
    adr x0, vectors
    msr vbar_el1, x0
    // identity map: 1 GiB blocks, [0, 1G) Device, [1G, 4G) Normal write-back
    adrp x0, ttb
    add x0, x0, :lo12:ttb
    msr ttbr0_el1, x0
    mov x1, #0xff00                    // MAIR: attr0 Device-nGnRnE, attr1 Normal WB
    msr mair_el1, x1
    ldr x1, =0x80803519                // TCR: T0SZ 25, WB/WB inner shareable, 4K, EPD1, IPS 40 bits
    orr x1, x1, #(2 << 32)
    msr tcr_el1, x1
    isb
    mrs x1, sctlr_el1
    orr x1, x1, #(1 << 0)              // M
    orr x1, x1, #(1 << 2)              // C
    orr x1, x1, #(1 << 12)             // I
    bic x1, x1, #(1 << 1)              // no alignment checks
    msr sctlr_el1, x1
    isb
    mov x0, #(3 << 20)                 // CPACR_EL1: FPEN, ZEN
    orr x0, x0, #(3 << 16)
    msr cpacr_el1, x0
    isb
    adrp x0, vq_minus_1
    ldr x0, [x0, :lo12:vq_minus_1]
    msr S3_0_C1_C2_0, x0               // ZCR_EL1.LEN
    isb
    adrp x19, run_table
    add x19, x19, :lo12:run_table
    adrp x20, states
    add x20, x20, :lo12:states
    adrp x21, run_count
    ldr x21, [x21, :lo12:run_count]
1:  ldr x9, [x19], #8
    mov x0, x20
    blr x9
    add x20, x20, #STATE_SIZE
    subs x21, x21, #1
    b.ne 1b
    // semihosting: write the state blocks to the output file and exit
    adrp x1, sh_open
    add x1, x1, :lo12:sh_open
    mov w0, #0x01
    hlt #0xf000
    adrp x1, sh_write
    add x1, x1, :lo12:sh_write
    str x0, [x1]
    mov w0, #0x05
    hlt #0xf000
    adrp x1, sh_write
    add x1, x1, :lo12:sh_write
    mov w0, #0x02
    hlt #0xf000
    adrp x1, sh_exit
    add x1, x1, :lo12:sh_exit
    mov w0, #0x18
    hlt #0xf000
2:  b 2b
.ltorg

// a synchronous exception records ESR_EL1 and skips the faulting instruction
.balign 2048
vectors:
.rept 16
    .balign 128
    b exc
.endr
exc:
    msr tpidr_el1, x0
    msr tpidrro_el0, x1
    adrp x0, fault_esr
    mrs x1, esr_el1
    str x1, [x0, :lo12:fault_esr]
    mrs x1, elr_el1
    add x1, x1, #4
    msr elr_el1, x1
    mrs x0, tpidr_el1
    mrs x1, tpidrro_el0
    eret

.data
.balign 8
fault_esr: .quad 0
out_name: .asciz "out.bin"
.balign 8
sh_open: .quad out_name, 5, 7         // "wb"
sh_write: .quad 0, states, states_end - states
sh_exit: .quad 0x20026, 0
.balign 4096
ttb:
    .quad 0x0000000000000401           // [0, 1G): block, AF, attr0
    .quad 0x0000000040000705           // [1G, 2G): block, AF, inner shareable, attr1
    .quad 0x0000000080000705
    .quad 0x00000000c0000705
    .fill 508, 8, 0
"""

LINK = f"""
ENTRY(_start)
SECTIONS {{
    . = {LOAD:#x};
    .text : {{ *(.text.start) *(.text*) }}
    .rodata : {{ *(.rodata*) }}
    .data : {{ *(.data*) }}
    .bss : {{ *(.bss*) *(COMMON) }}
    . = ALIGN(16);
    . = . + 0x10000;
    __stack_top = .;
}}
"""


def _stub(label, word, L: Layout):
    lines = [f'.globl {label}', '.p2align 2', f'{label}:',
             '    mov x16, x0',
             f'    ldr x17, [x16, #{S_NZCV}]', '    msr nzcv, x17',
             f'    ldr x17, [x16, #{S_FPCR}]', '    msr fpcr, x17',
             f'    ldr x17, [x16, #{S_FPSR}]', '    msr fpsr, x17',
             f'    add x17, x16, #{L.ffr}', '    ldr p0, [x17]', '    wrffr p0.b']
    for i in range(8):
        lines += [f'    add x17, x16, #{L.pr(i)}', f'    ldr p{i}, [x17]',
                  f'    add x17, x16, #{L.z(i)}', f'    ldr z{i}, [x17]']
    lines += ['    adrp x17, fault_esr', '    str xzr, [x17, :lo12:fault_esr]']
    lines += [f'    ldp x{i}, x{i + 1}, [x16, #{8 * i}]' for i in range(0, 8, 2)]
    lines += [f'    .inst {word:#010x}']
    lines += [f'    stp x{i}, x{i + 1}, [x16, #{8 * i}]' for i in range(0, 8, 2)]
    lines += ['    mrs x17, nzcv', f'    str x17, [x16, #{S_NZCV}]',
              '    mrs x17, fpcr', f'    str x17, [x16, #{S_FPCR}]',
              '    mrs x17, fpsr', f'    str x17, [x16, #{S_FPSR}]']
    for i in range(8):
        lines += [f'    add x17, x16, #{L.pr(i)}', f'    str p{i}, [x17]',
                  f'    add x17, x16, #{L.z(i)}', f'    str z{i}, [x17]']
    lines += ['    rdffr p0.b', f'    add x17, x16, #{L.ffr}', '    str p0, [x17]',
              '    adrp x17, fault_esr', '    ldr x17, [x17, :lo12:fault_esr]',
              f'    str x17, [x16, #{S_FAULT}]',
              '    msr fpcr, xzr', '    msr fpsr, xzr', '    ret']
    return '\n'.join(lines) + '\n'


def is_sve(ins):
    return 'instr-class.sve' in ins.attributes


def pick_operands(machine, ins, rng):
    fixed = {n: rng.randrange(8) for n in ins.operand_names if n in REG_FIELDS}
    return sample_operands(machine, ins, rng, fixed)


def _lanes(rng, nbits):
    """A VL-bit value of random elements of one size, biased to edge values."""
    esize = rng.choice((8, 16, 32, 64))
    v = 0
    for i in range(nbits // esize):
        r = rng.random()
        if r < 0.25:
            x = rng.choice((0, 1, (1 << (esize - 1)) - 1, 1 << (esize - 1), (1 << esize) - 1, 2, esize))
        elif r < 0.4 and esize >= 16:
            x = rng.choice(SPECIALS[16 if esize == 16 else 32 if esize == 32 else 64])
        elif r < 0.5:
            x = rng.randrange(256)
        else:
            x = rng.getrandbits(esize)
        v |= x << (i * esize)
    return v


def _pred(rng, nbits):
    """A predicate: random, all/none, a prefix of elements or a single element."""
    esize = rng.choice((8, 16, 32, 64))
    k = esize // 8
    elems = nbits // k
    r = rng.random()
    if r < 0.4:
        return rng.getrandbits(nbits)
    if r < 0.55:
        bits = [1] * elems
    elif r < 0.65:
        bits = [0] * elems
    elif r < 0.85:
        n = rng.randrange(elems + 1)
        bits = [int(i < n) for i in range(elems)]
    else:
        bits = [0] * elems
        bits[rng.randrange(elems)] = 1
    return sum(b << (i * k) for i, b in enumerate(bits))


def random_state(rng, vq):
    vl = 128 * vq
    x = []
    for _ in range(8):
        r = rng.random()
        x.append(rng.choice(EDGE) if r < 0.3 else rng.randrange(-300, 300) & M64 if r < 0.5
                 else rng.getrandbits(64))
    fpcr = rng.getrandbits(32) & FPCR_RANDOM if rng.random() < 0.6 else 0
    fpsr = rng.getrandbits(32) & FPSR_MASK if rng.random() < 0.3 else 0
    return {'X': x, 'NZCV': rng.getrandbits(4), 'FPCR': fpcr, 'FPSR': fpsr,
            'Z': [_lanes(rng, vl) for _ in range(8)], 'P': [_pred(rng, vl // 8) for _ in range(8)],
            'FFR': _pred(rng, vl // 8)}


def pack_state(st, L: Layout):
    b = bytearray(L.size)
    for i, v in enumerate(st['X']):
        b[8 * i:8 * i + 8] = v.to_bytes(8, 'little')
    for off, v in ((S_NZCV, st['NZCV'] << 28), (S_FPCR, st['FPCR']), (S_FPSR, st['FPSR'])):
        b[off:off + 8] = v.to_bytes(8, 'little')
    for i, v in enumerate(st['Z']):
        b[L.z(i):L.z(i) + L.zb] = v.to_bytes(L.zb, 'little')
    for i, v in enumerate(st['P']):
        b[L.pr(i):L.pr(i) + L.pb] = v.to_bytes(L.pb, 'little')
    b[L.ffr:L.ffr + L.pb] = st['FFR'].to_bytes(L.pb, 'little')
    return bytes(b)


def unpack_state(b, L: Layout):
    q = lambda off, n=8: int.from_bytes(b[off:off + n], 'little')
    return {'X': [q(8 * i) for i in range(8)], 'NZCV': q(S_NZCV) >> 28, 'FPCR': q(S_FPCR),
            'FPSR': q(S_FPSR), 'Z': [q(L.z(i), L.zb) for i in range(8)],
            'P': [q(L.pr(i), L.pb) for i in range(8)], 'FFR': q(L.ffr, L.pb),
            'fault': q(S_FAULT)}


def run_qemu(d: Path, cases, vq):
    """cases: [(word, [state, ...])] -> [[state after, ...]]"""
    L = Layout(vq)
    states = b''.join(pack_state(st, L) for _, sts in cases for st in sts)
    (d / 'states.bin').write_bytes(states)
    asm = [START.replace('STATE_SIZE', str(L.size)), '.text']
    asm += [_stub(f'case_{i}', w, L) for i, (w, _) in enumerate(cases)]
    runs = [f'case_{i}' for i, (_, sts) in enumerate(cases) for _ in sts]
    asm += ['.data', '.balign 8', f'vq_minus_1: .quad {vq - 1}', f'run_count: .quad {len(runs)}',
            'run_table:'] + [f'    .quad {r}' for r in runs]
    asm += ['.balign 16', 'states:', '    .incbin "states.bin"', 'states_end:']
    (d / 'cases.s').write_text('\n'.join(asm) + '\n')
    (d / 'link.ld').write_text(LINK)
    subprocess.run([CC, '--target=aarch64-none-elf', '-march=armv8.2-a+sve', '-c', 'cases.s',
                    '-o', 'cases.o'], cwd=d, check=True)
    subprocess.run([LD, '-T', 'link.ld', 'cases.o', '-o', 'cases.elf'], cwd=d, check=True)
    out = d / 'out.bin'
    if out.exists():
        out.unlink()
    subprocess.run([QEMU, '-M', 'virt', '-cpu', 'max', '-m', '1024', '-nographic', '-monitor', 'none',
                    '-serial', 'none', '-semihosting-config', 'enable=on,target=native',
                    '-kernel', 'cases.elf'], cwd=d, check=True, timeout=600)
    data = out.read_bytes()
    assert len(data) == len(states), (len(data), len(states))
    res, k = [], 0
    for _, sts in cases:
        res.append([unpack_state(data[(k + j) * L.size:(k + j + 1) * L.size], L)
                    for j in range(len(sts))])
        k += len(sts)
    return res


def interp_sve(arch, ins, word, st, vq):
    from .lira_interp import Machine
    m = Machine(arch, vq)
    m.regs['X'][:8] = st['X']
    m.regs['Z'][:8] = st['Z']
    m.regs['P'][:8] = st['P']
    m.regs['FFR'][0] = st['FFR']
    for k in ('NZCV', 'FPCR', 'FPSR'):
        m.regs[k][0] = st[k]
    m.execute(ins, m.decode(ins, word))
    return {'X': m.regs['X'][:8], 'Z': m.regs['Z'][:8], 'P': m.regs['P'][:8], 'FFR': m.regs['FFR'][0],
            **{k: m.regs[k][0] for k in ('NZCV', 'FPCR', 'FPSR')}}


def diff_state(a, b):
    d = []
    for k in ('X', 'Z', 'P'):
        d += [f'{k}{i}: {x:#x} vs {y:#x}' for i, (x, y) in enumerate(zip(a[k], b[k])) if x != y]
    d += [f'{k}: {a[k]:#x} vs {b[k]:#x}' for k in ('FFR', 'NZCV', 'FPCR', 'FPSR') if a[k] != b[k]]
    return d


@pytest.mark.parametrize('vq', VQS)
def test_sve_semantics_match_qemu(arch, machine, vq, tmp_path):
    rng = random.Random(100 + vq)
    cases, meta = [], []
    for ins in arch.instructions:
        if not is_sve(ins) or not ONLY.search(ins.name):
            continue
        for _ in range(CASES_PER_INSN):
            ops = pick_operands(machine, ins, rng)
            word = machine.encode(ins, ops)
            cases.append((word, [random_state(rng, vq) for _ in range(STATES_PER_CASE)]))
            meta.append((ins, ops))
    assert cases, 'no SVE instruction selected'
    results = run_qemu(tmp_path, cases, vq)
    failures = []
    for (word, sts), (ins, ops), outs in zip(cases, meta, results):
        for st, hw in zip(sts, outs):
            if hw['fault']:
                failures.append((ins.name, hex(word), f'QEMU exception, ESR {hw["fault"]:#x}'))
                break
            got = interp_sve(arch, ins, word, st, vq)
            d = diff_state(hw, got)
            if d:
                failures.append((ins.name, hex(word), dict(zip(ins.operand_names, ops)),
                                 'qemu vs lira:', d[:6]))
                break
    summary = ' '.join(sorted({f[0] for f in failures}))
    assert not failures, '\n'.join(map(str, failures[:30])) + f'\n({len(failures)} failing cases)\n' + summary
