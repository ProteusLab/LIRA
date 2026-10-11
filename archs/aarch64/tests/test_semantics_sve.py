"""Differential test of the SVE instructions: LIRA semantics vs. QEMU.

The host CPU may lack SVE, so the reference is `qemu-system-aarch64 -cpu max`
running a bare-metal image at EL1: it sets the vector length (ZCR_EL1; SMCR_EL1
gives streaming mode the same length and FEAT_SME_FA64), enables an
identity-mapped MMU (Normal memory, so SVE accesses need no alignment), and
runs one stub per (case, state). Each stub loads x0..x7, z0..z7, p0..p7, FFR,
NZCV, FPCR and FPSR from a state block, executes the word and stores the state
back; a synchronous exception is recorded (ESR) and the word skipped. The
blocks come back through semihosting and are compared with the reference
interpreter run at the same VQ. SME states (`Layout.sme`, see
test_semantics_sme.py) also have x8..x15, SVCR and ZA.

Loads and stores access a window at the end of a mapped page, followed by an
unmapped guard page: a memory stub copies the state's window image in before
the word and out after it. Their states are drawn until the interpreter finds
every access inside the window or the guard page (a fault, or a suppressed
element of LDFF1/LDNF1).

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

# State block (bytes): x0..x7 (SME: x0..x15), NZCV, FPCR, FPSR, fault ESR,
# (SME: SVCR), then z0..z7 (VL / 8 bytes each), p0..p7 and FFR (16-byte aligned
# slots of VL / 64 bytes), (SME: ZA, VL / 8 rows of VL / 8 bytes); memory cases
# append the window image
WPAGE = 0x7f000000          # mapped page holding the window, above the image; the next page is unmapped
GUARD = WPAGE + 0x1000


class Layout:
    def __init__(self, vq, sme=False):
        self.vq, self.sme = vq, sme
        self.nx = 16 if sme else 8
        self.nzcv = 8 * self.nx
        self.fpcr, self.fpsr, self.fault, self.svcr = self.nzcv + 8, self.nzcv + 16, self.nzcv + 24, self.nzcv + 32
        self.z0 = self.nzcv + 64
        self.zb, self.pb = 16 * vq, 2 * vq
        self.zslot, self.pslot = 16 * vq, max(16, 2 * vq)
        self.p = self.z0 + 8 * self.zslot
        self.ffr = self.p + 8 * self.pslot
        self.za = self.ffr + self.pslot
        end = self.za + (self.zb * self.zb if sme else 0)
        self.size = (end + 63) // 64 * 64
        self.win = min(4096, 512 * vq)                    # window bytes
        self.w0 = GUARD - self.win

    def z(self, i):
        return self.z0 + self.zslot * i

    def pr(self, i):
        return self.p + self.pslot * i


FPCR_RANDOM = (3 << 22) | (1 << 24) | (1 << 19) | (1 << 25)
FPSR_MASK = 0x0800009F

REG_FIELDS = {'Zd', 'Zn', 'Zm', 'Za', 'Zda', 'Zdn', 'Zt', 'Pd', 'Pg', 'Pn', 'Pm', 'Pdm', 'Pdn', 'Pv',
              'Pt', 'Rd', 'Rn', 'Rm', 'Rdn', 'Vd', 'Vn', 'Vm', 'Vdn'}

RAM, LOAD = 0x40000000, 0x40080000

START = f"""
.section .text.start, "ax"
.globl _start
_start:
    ldr x0, =__stack_top
    mov sp, x0
    adr x0, vectors
    msr vbar_el1, x0
    // identity map: [0, 1G) Device, [1G, 4G) Normal write-back, the page at
    // {GUARD:#x} unmapped
    adrp x0, ttb_l1
    add x0, x0, :lo12:ttb_l1
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
    mov x0, #(3 << 20)                 // CPACR_EL1: FPEN, ZEN, SMEN
    orr x0, x0, #(3 << 16)
    orr x0, x0, #(3 << 24)
    msr cpacr_el1, x0
    isb
    adrp x0, vq_minus_1
    ldr x0, [x0, :lo12:vq_minus_1]
    msr S3_0_C1_C2_0, x0               // ZCR_EL1.LEN
    orr x0, x0, #(1 << 31)             // SMCR_EL1: FA64, LEN (SVL = VL)
    msr S3_0_C1_C2_6, x0
    isb
    adrp x19, run_table
    add x19, x19, :lo12:run_table
    adrp x21, run_count
    ldr x21, [x21, :lo12:run_count]
1:  ldp x9, x0, [x19], #16             // stub, state block
    blr x9
    subs x21, x21, #1
    b.ne 1b
    // semihosting: write the state blocks to the output file (1 MiB at a
    // time) and exit
    adrp x1, sh_open
    add x1, x1, :lo12:sh_open
    mov w0, #0x01
    hlt #0xf000
    adrp x19, sh_write
    add x19, x19, :lo12:sh_write
    str x0, [x19]
    adrp x20, states
    add x20, x20, :lo12:states
    adrp x21, states_end
    add x21, x21, :lo12:states_end
3:  sub x22, x21, x20
    cbz x22, 4f
    mov x23, #0x100000
    cmp x22, x23
    csel x22, x22, x23, lo
    stp x20, x22, [x19, #8]
    mov x1, x19
    mov w0, #0x05
    hlt #0xf000
    add x20, x20, x22
    b 3b
4:  adrp x1, sh_write
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
ttb_l1:
    .quad 0x0000000000000401           // [0, 1G): block, AF, attr0
    .quad ttb_l2 + 3                   // [1G, 2G): 2 MiB blocks
    .quad 0x0000000080000705           // block, AF, inner shareable, attr1
    .quad 0x00000000c0000705
    .fill 508, 8, 0
ttb_l2:
.set i, 0
.rept 512
.if i == {(WPAGE - RAM) >> 21}
    .quad ttb_l3 + 3
.else
    .quad {RAM:#x} + (i << 21) + 0x705
.endif
.set i, i + 1
.endr
ttb_l3:
.set i, 0
.rept 512
.if i == {(GUARD - WPAGE) >> 12}
    .quad 0
.else
    .quad {WPAGE:#x} + (i << 12) + 0x707
.endif
.set i, i + 1
.endr
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


def _mov64(reg, value):
    """movz/movk of a 32-bit address (no literal pool: the assembler may share a
    far one between stubs)."""
    return f'mov {reg}, #{value & 0xffff:#x}\n    movk {reg}, #{value >> 16:#x}, lsl #16'


def _add16(reg, off):
    """reg = x16 + off (an offset in the state block)."""
    if off < 4096:
        return f'add {reg}, x16, #{off}'
    return f'{_mov64(reg, off)}\n    add {reg}, x16, {reg}'


def _copy(src, dst, n):
    """Copy n (a multiple of 16) bytes; x9..x13 are scratch."""
    return [f'    {src}', f'    {dst}', f'    mov x11, #{n}',
            '1:  ldp x12, x13, [x9], #16', '    stp x12, x13, [x10], #16',
            '    subs x11, x11, #16', '    b.ne 1b']


def _za_rows(L: Layout, op):
    """LDR/STR of every ZA vector if PSTATE.ZA (the SVCR in the block) is set;
    x12, x14, x17 are scratch."""
    rows = L.zb
    return [f'    ldr x17, [x16, #{L.svcr}]', '    tbz x17, #1, 5f',
            f'    add x14, x16, #{L.za}', '    mov w12, #0',
            f'4:  {op} za[w12, 0], [x14]', f'    add x14, x14, #{L.zb}',
            '    add w12, w12, #1', f'    cmp w12, #{rows}', '    b.ne 4b', '5:']


def _stub(label, word, L: Layout, mem: bool):
    lines = [f'.globl {label}', '.p2align 2', f'{label}:', '    mov x16, x0']
    if mem:
        lines += _copy(_add16('x9', L.size), _mov64('x10', L.w0), L.win)
    if L.sme:                                              # first: changing SM resets Z, P, FFR, FPSR
        lines += [f'    ldr x17, [x16, #{L.svcr}]', '    msr svcr, x17']
    lines += [f'    ldr x17, [x16, #{L.fpcr}]', '    msr fpcr, x17',
              f'    ldr x17, [x16, #{L.fpsr}]', '    msr fpsr, x17',
              f'    add x17, x16, #{L.ffr}', '    ldr p0, [x17]', '    wrffr p0.b']
    for i in range(8):
        lines += [f'    add x17, x16, #{L.pr(i)}', f'    ldr p{i}, [x17]',
                  f'    add x17, x16, #{L.z(i)}', f'    ldr z{i}, [x17]']
    if L.sme:
        lines += _za_rows(L, 'ldr')
    lines += [f'    ldr x17, [x16, #{L.nzcv}]', '    msr nzcv, x17',
              '    adrp x17, fault_esr', '    str xzr, [x17, :lo12:fault_esr]']
    lines += [f'    ldp x{i}, x{i + 1}, [x16, #{8 * i}]' for i in range(0, L.nx, 2)]
    lines += [f'    .inst {word:#010x}']
    lines += [f'    stp x{i}, x{i + 1}, [x16, #{8 * i}]' for i in range(0, L.nx, 2)]
    lines += ['    mrs x17, nzcv', f'    str x17, [x16, #{L.nzcv}]',
              '    mrs x17, fpcr', f'    str x17, [x16, #{L.fpcr}]',
              '    mrs x17, fpsr', f'    str x17, [x16, #{L.fpsr}]']
    if L.sme:
        lines += ['    mrs x17, svcr', f'    str x17, [x16, #{L.svcr}]']
    for i in range(8):
        lines += [f'    add x17, x16, #{L.pr(i)}', f'    str p{i}, [x17]',
                  f'    add x17, x16, #{L.z(i)}', f'    str z{i}, [x17]']
    lines += ['    rdffr p0.b', f'    add x17, x16, #{L.ffr}', '    str p0, [x17]']
    if L.sme:
        lines += _za_rows(L, 'str')
    lines += ['    adrp x17, fault_esr', '    ldr x17, [x17, :lo12:fault_esr]',
              f'    str x17, [x16, #{L.fault}]',
              '    msr fpcr, xzr', '    msr fpsr, xzr']
    if L.sme:
        lines += ['    smstop']
    if mem:
        lines += _copy(_mov64('x9', L.w0), _add16('x10', L.size), L.win)
    lines += ['    ret']
    return '\n'.join(lines) + '\n'


def is_sve(ins):
    return 'instr-class.sve' in ins.attributes


def is_mem(ins):
    return is_sve(ins) and ins.name.startswith(('ld', 'st', 'prf'))


def _mnemonic(ins):
    return next(a for a in ins.attributes if a.startswith('mnemonic.')).split('.', 1)[1]


# Memory operand immediates kept small so the accesses can stay in the window
SMALL_IMM = {'imm4': (0, 1, 15), 'imm6': range(8), 'imm5': range(8), 'imm9h': (0,), 'imm9l': range(4)}


def pick_operands(machine, ins, rng):
    fixed = {n: rng.randrange(8) for n in ins.operand_names if n in REG_FIELDS}
    if is_mem(ins):
        for f, vals in SMALL_IMM.items():
            if f in ins.operand_names:
                fixed[f] = rng.choice(vals)
        m = re.match(r'(LD|ST)([234])', _mnemonic(ins))
        if m:                                              # Zt..Zt+n-1 within z0..z7
            fixed['Zt'] = rng.randrange(9 - int(m.group(2)))
        if 'Rm' in fixed and 'Rn' in fixed:               # base and offset in different registers
            fixed['Rm'] = rng.choice([r for r in range(8) if r != fixed['Rn']])
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


def _vector_of(rng, vq, esize, gen):
    return sum((gen() & ((1 << esize) - 1)) << (i * esize) for i in range(128 * vq // esize))


def random_mem_state(rng, vq, ins, ops):
    """A state whose base registers and vector offsets point into the window."""
    L = Layout(vq)
    st = random_state(rng, vq)
    names = dict(zip(ins.operand_names, ops))
    if 'Rn' in names:
        st['X'][names['Rn']] = L.w0 + rng.randrange(L.win)
    if 'Rm' in names:
        st['X'][names['Rm']] = rng.randrange(L.win // 16)
    m = re.search(r'_(bz|ai)_([sd])', ins.name)
    if m:
        esize = 32 if m.group(2) == 's' else 64
        if m.group(1) == 'ai':                             # vector of addresses
            st['Z'][names['Zn']] = _vector_of(rng, vq, esize, lambda: L.w0 + rng.randrange(L.win))
        else:                                              # vector of offsets
            st['Z'][names['Zm']] = _vector_of(rng, vq, esize, lambda: rng.randrange(L.win // 8))
    if re.match(r'LD(NF|FF)1', _mnemonic(ins)) and not m:
        # QEMU (seen in 10.0.2, sve_ldnfff1_r) tests the predicate of contiguous
        # LDNF1/LDFF1 at the wrong offset unless the first active element starts
        # a 64-bit predicate word: keep element 0 active
        st['P'][names['Pg']] |= 1
    st['MEM'] = bytes(rng.getrandbits(8) for _ in range(L.win))
    return st


def pack_state(st, L: Layout):
    b = bytearray(L.size)
    for i, v in enumerate(st['X']):
        b[8 * i:8 * i + 8] = v.to_bytes(8, 'little')
    for off, v in ((L.nzcv, st['NZCV'] << 28), (L.fpcr, st['FPCR']), (L.fpsr, st['FPSR'])):
        b[off:off + 8] = v.to_bytes(8, 'little')
    for i, v in enumerate(st['Z']):
        b[L.z(i):L.z(i) + L.zb] = v.to_bytes(L.zb, 'little')
    for i, v in enumerate(st['P']):
        b[L.pr(i):L.pr(i) + L.pb] = v.to_bytes(L.pb, 'little')
    b[L.ffr:L.ffr + L.pb] = st['FFR'].to_bytes(L.pb, 'little')
    if L.sme:
        b[L.svcr:L.svcr + 8] = st['SVCR'].to_bytes(8, 'little')
        b[L.za:L.za + L.zb * L.zb] = st['ZA'].to_bytes(L.zb * L.zb, 'little')
    return bytes(b) + st.get('MEM', b'')


def unpack_state(b, L: Layout, mem: bool):
    q = lambda off, n=8: int.from_bytes(b[off:off + n], 'little')
    st = {'X': [q(8 * i) for i in range(L.nx)], 'NZCV': q(L.nzcv) >> 28, 'FPCR': q(L.fpcr),
          'FPSR': q(L.fpsr), 'Z': [q(L.z(i), L.zb) for i in range(8)],
          'P': [q(L.pr(i), L.pb) for i in range(8)], 'FFR': q(L.ffr, L.pb), 'fault': q(L.fault)}
    if L.sme:
        # QEMU (seen in 10.0.2) keeps the RES0 bits MSR SVCR writes; SVCR reads
        # as Zeros(62):ZA:SM
        st['SVCR'], st['ZA'] = q(L.svcr) & 3, q(L.za, L.zb * L.zb)
    if mem:
        st['MEM'] = bytes(b[L.size:L.size + L.win])
    return st


def run_qemu(d: Path, cases, vq, sme=False):
    """cases: [(word, is_mem, [state, ...])] -> [[state after, ...]]"""
    L = Layout(vq, sme)
    blobs, runs, off = [], [], 0
    for i, (_, _, sts) in enumerate(cases):
        for st in sts:
            blobs.append(pack_state(st, L))
            runs.append((f'case_{i}', off))
            off += len(blobs[-1])
    states = b''.join(blobs)
    (d / 'states.bin').write_bytes(states)
    asm = [START, '.text']
    asm += [_stub(f'case_{i}', w, L, mem) for i, (w, mem, _) in enumerate(cases)]
    asm += ['.data', '.balign 8', f'vq_minus_1: .quad {vq - 1}', f'run_count: .quad {len(runs)}',
            'run_table:'] + [f'    .quad {r}, states + {o}' for r, o in runs]
    asm += ['.balign 16', 'states:', '    .incbin "states.bin"', 'states_end:']
    (d / 'cases.s').write_text('\n'.join(asm) + '\n')
    (d / 'link.ld').write_text(LINK)
    subprocess.run([CC, '--target=aarch64-none-elf', '-march=armv9-a+sme', '-c', 'cases.s',
                    '-o', 'cases.o'], cwd=d, check=True)
    subprocess.run([LD, '-T', 'link.ld', 'cases.o', '-o', 'cases.elf'], cwd=d, check=True)
    out = d / 'out.bin'
    if out.exists():
        out.unlink()
    subprocess.run([QEMU, '-M', 'virt', '-cpu', 'max', '-m', '1024', '-nographic', '-monitor', 'none',
                    '-serial', 'none', '-semihosting-config', 'enable=on,target=native',
                    '-kernel', 'cases.elf'], cwd=d, check=True, timeout=1200)
    data = out.read_bytes()
    assert len(data) == len(states), (len(data), len(states))
    res, k = [], 0
    for _, mem, sts in cases:
        res.append([])
        for _ in sts:
            o = runs[k][1]
            res[-1].append(unpack_state(data[o:o + len(blobs[k])], L, mem))
            k += 1
    return res


class Fault(Exception):
    """A synchronous data abort (an access to the guard page)."""


class SmeTrap(Exception):
    """An SME access trap (`sme_access_trap`): ESR EC 0x1D, ISS = the type."""

    def __init__(self, kind):
        super().__init__(kind)
        self.esr = 0x1D << 26 | 1 << 25 | kind


def _sme_trap(kind):
    raise SmeTrap(kind)


class OutOfWindow(Exception):
    """An access outside the window and the guard page: the state is not usable."""


class Memory:
    """The window [w0, GUARD) and the unmapped guard page after it."""

    def __init__(self, L: Layout, image: bytes):
        self.w0, self.data = L.w0, bytearray(image)
        self.straddle = False                              # an access crossed into the guard page

    def _check(self, addr, n):
        if self.w0 <= addr and addr + n <= GUARD:
            return True
        if self.w0 <= addr + n - 1 and addr < GUARD + 0x1000 and addr + n > GUARD:
            self.straddle |= addr < GUARD
            return False                                   # touches the guard page
        raise OutOfWindow(hex(addr))

    def read(self, n):
        def f(addr):
            if not self._check(addr, n // 8):
                raise Fault(hex(addr))
            o = addr - self.w0
            return [int.from_bytes(self.data[o:o + n // 8], 'little')]
        return f

    def read_nf(self, n):
        def f(addr):
            if not self._check(addr, n // 8):
                return [0, 0]
            return self.read(n)(addr) + [1]
        return f

    def write(self, n):
        def f(addr, v):
            if not self._check(addr, n // 8):
                raise Fault(hex(addr))
            o = addr - self.w0
            self.data[o:o + n // 8] = v.to_bytes(n // 8, 'little')
        return f


def interp_sve(arch, ins, word, st, vq):
    """The state after the word, 'fault', or ('sme', ESR) for an SME access
    trap; raises OutOfWindow."""
    return _interp_sve(arch, ins, word, st, vq)[0]


SCALARS = ('NZCV', 'FPCR', 'FPSR', 'SVCR', 'ZA')


def _interp_sve(arch, ins, word, st, vq):
    """(state after the word, 'fault' or ('sme', ESR), the Memory or None)."""
    from .lira_interp import Machine
    m = Machine(arch, vq)
    m.regs['X'][:len(st['X'])] = st['X']
    m.regs['Z'][:8] = st['Z']
    m.regs['P'][:8] = st['P']
    m.regs['FFR'][0] = st['FFR']
    scalars = [k for k in SCALARS if k in st]
    for k in scalars:
        m.regs[k][0] = st[k]
    m.env['sme_access_trap'] = _sme_trap
    mem = Memory(Layout(vq), st['MEM']) if 'MEM' in st else None
    if mem:
        for n in (8, 16, 32, 64, 128):
            m.env[f'mem_read_{n}'], m.env[f'mem_write_{n}'] = mem.read(n), mem.write(n)
        for n in (8, 16, 32, 64):
            m.env[f'mem_read_nf_{n}'] = mem.read_nf(n)
    try:
        m.execute(ins, m.decode(ins, word))
    except Fault:
        return 'fault', mem
    except SmeTrap as e:
        return ('sme', e.esr), mem
    out = {'X': m.regs['X'][:len(st['X'])], 'Z': m.regs['Z'][:8], 'P': m.regs['P'][:8],
           'FFR': m.regs['FFR'][0], **{k: m.regs[k][0] for k in scalars}}
    if mem:
        out['MEM'] = bytes(mem.data)
    return out, mem


def mem_case_states(arch, rng, vq, ins, ops, word, n, make_state=random_mem_state):
    """n (state, expected) pairs of a load/store: accesses stay in the window or
    the guard page; about a quarter fault.

    QEMU (seen in 10.0.2) differs on LDNF1 when an element crosses into an
    unmapped page: it takes a data abort if that is the first active element (a
    non-fault load must not fault) and otherwise suppresses all the elements
    (allowed, but not the per-element choice of the description). LDNF1 states
    with such an element are not used."""
    nf = _mnemonic(ins).startswith('LDNF1')
    out = []
    while len(out) < n:
        for _ in range(200):
            st = make_state(rng, vq, ins, ops)
            try:
                got, mem = _interp_sve(arch, ins, word, st, vq)
            except OutOfWindow:
                continue
            if got == 'fault' and rng.random() < 0.75 or nf and mem.straddle:
                continue
            break
        else:
            raise AssertionError(f'{ins.name}: no state with accesses in the window')
        out.append((st, got))
    return out


def diff_state(a, b):
    d = []
    for k in ('X', 'Z', 'P'):
        d += [f'{k}{i}: {x:#x} vs {y:#x}' for i, (x, y) in enumerate(zip(a[k], b[k])) if x != y]
    d += [f'{k}: {a[k]:#x} vs {b[k]:#x}' for k in ('FFR', 'NZCV', 'FPCR', 'FPSR', 'SVCR')
          if k in a and a[k] != b[k]]
    if 'ZA' in a and a['SVCR'] & 2 and a['ZA'] != b['ZA']:     # ZA is ARBITRARY when off
        x = a['ZA'] ^ b['ZA']
        bad = [i for i in range((x.bit_length() + 7) // 8) if x >> (8 * i) & 0xff]
        d.append('ZA bytes: ' + ', '.join(f'{i:#x}: {a["ZA"] >> 8 * i & 0xff:#04x} vs '
                                           f'{b["ZA"] >> 8 * i & 0xff:#04x}' for i in bad[:4]))
    if 'MEM' in a and a['MEM'] != b['MEM']:
        bad = [f'{i:#x}: {x:#04x} vs {y:#04x}' for i, (x, y) in enumerate(zip(a['MEM'], b['MEM'])) if x != y]
        d.append('memory: ' + ', '.join(bad[:4]))
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
            if is_mem(ins):
                pairs = mem_case_states(arch, rng, vq, ins, ops, word, STATES_PER_CASE)
            else:
                pairs = [(random_state(rng, vq), None) for _ in range(STATES_PER_CASE)]
            cases.append((word, is_mem(ins), [st for st, _ in pairs]))
            meta.append((ins, ops, [exp for _, exp in pairs]))
    assert cases, 'no SVE instruction selected'
    check_results(arch, vq, cases, meta, run_qemu(tmp_path, cases, vq))


def _fault_mismatch(hw, got):
    """None if QEMU and LIRA agree on taking an exception (an SME access trap
    must have the same syndrome), else a description."""
    lira = 'fault' if got == 'fault' else f'SME trap {got[1]:#x}' if isinstance(got, tuple) else None
    if not hw['fault'] and lira is None:
        return None
    if hw['fault'] and (got == 'fault' or isinstance(got, tuple) and got[1] == hw['fault']):
        return ''
    return f'QEMU ESR {hw["fault"]:#x}, LIRA {lira or "no exception"}'


def check_results(arch, vq, cases, meta, results):
    failures = []
    for (word, _, sts), (ins, ops, exps), outs in zip(cases, meta, results):
        for st, exp, hw in zip(sts, exps, outs):
            got = exp or interp_sve(arch, ins, word, st, vq)
            f = _fault_mismatch(hw, got)
            if f == '':
                continue
            d = [f] if f else diff_state(hw, got)
            if d:
                failures.append((ins.name, hex(word), dict(zip(ins.operand_names, ops)),
                                 'qemu vs lira:', d[:6]))
                break
    summary = ' '.join(sorted({f[0] for f in failures}))
    assert not failures, '\n'.join(map(str, failures[:30])) + f'\n({len(failures)} failing cases)\n' + summary
