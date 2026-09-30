"""Interpreter checks for behaviour the hardware test cannot cover: branches,
register 31 (SP vs. XZR), PC-relative loads and exceptions."""
import pytest

from .lira_interp import Machine

PC = 0x10000
SP = 0x7FFF0000
M64 = (1 << 64) - 1


class Run:
    def __init__(self, arch, name, **fields):
        ins = next(i for i in arch.instructions if i.name == name)
        self.m = Machine(arch)
        self.branches, self.svc, self.mem = [], [], {}
        self.m.env['pc_read'] = lambda: [PC]
        self.m.env['pc_write'] = lambda t: self.branches.append(t)
        self.m.env['supervisor_call'] = lambda imm: self.svc.append(imm)
        for n in (8, 16, 32, 64, 128):
            self.m.env[f'mem_read_{n}'] = self._rd(n)
            self.m.env[f'mem_write_{n}'] = self._wr(n)
        self.m.regs['X'][31] = SP
        # Every other environment function records its calls and returns zeros
        self.calls = []
        for env in arch.environment_functions:
            if env.name not in self.m.env:
                self.m.env[env.name] = self._recorder(env)
        self.ins = ins
        self.ops = [fields[n] for n in ins.operand_names]
        # the encoding must be valid and decode back to the same operands
        word = self.m.encode(ins, self.ops)
        assert self.m.valid_word(ins, word) and self.m.decode(ins, word) == self.ops

    def _recorder(self, env):
        def f(*args):
            self.calls.append((env.name,) + args)
            return [0] * len(env.outputs)
        return f

    def _rd(self, n):
        return lambda a: [sum(self.mem.get(a + i, 0) << (8 * i) for i in range(n // 8))]

    def _wr(self, n):
        def f(a, v):
            for i in range(n // 8):
                self.mem[a + i] = (v >> (8 * i)) & 0xFF
        return f

    def x(self, **regs):
        for k, v in regs.items():
            self.m.regs['X'][int(k[1:])] = v & M64
        return self

    def flags(self, nzcv):
        self.m.regs['NZCV'][0] = nzcv
        return self

    def go(self):
        self.m.execute(self.ins, self.ops)
        return self

    def reg(self, i):
        return self.m.regs['X'][i]


def enc19(off):
    return (off >> 2) & ((1 << 19) - 1)


# -- register 31 --------------------------------------------------------------
def test_add_imm_uses_sp(arch):
    r = Run(arch, 'ADD_64_addsub_imm', sh=0, imm12=16, Rn=31, Rd=31).go()
    assert r.reg(31) == SP + 16


def test_adds_imm_discards_to_xzr(arch):
    r = Run(arch, 'ADDS_64S_addsub_imm', sh=0, imm12=1, Rn=31, Rd=31).go()   # CMN sp, #1
    assert r.reg(31) == SP
    assert r.m.regs['NZCV'][0] == 0


def test_add_shift_reads_xzr(arch):
    r = Run(arch, 'ADD_64_addsub_shift', shift=0, Rm=1, imm6=0, Rn=31, Rd=2).x(x1=5).go()
    assert r.reg(2) == 5 and r.reg(31) == SP


def test_subs_to_xzr_is_cmp(arch):
    r = Run(arch, 'SUBS_64_addsub_shift', shift=0, Rm=1, imm6=0, Rn=0, Rd=31).x(x0=3, x1=3).go()
    assert r.reg(31) == SP
    assert r.m.regs['NZCV'][0] == 0b0110                                      # Z, C


def test_w_write_zero_extends_and_sp_32(arch):
    r = Run(arch, 'ADD_32_addsub_imm', sh=1, imm12=1, Rn=0, Rd=31).x(x0=0xFFFFFFFF_FFFFFFFF).go()
    assert r.reg(31) == (0xFFFFFFFF + 0x1000) & 0xFFFFFFFF


def test_orr_imm_writes_sp(arch):
    # ORR SP, XZR, #0xff
    r = Run(arch, 'ORR_64_log_imm', N=1, immr=0, imms=7, Rn=31, Rd=31).go()
    assert r.reg(31) == 0xFF


def test_ldr_sp_base_and_writeback(arch):
    r = Run(arch, 'LDR_64_ldst_immpre', imm9=(-16) & 0x1FF, Rn=31, Rt=0)
    r._wr(64)(SP - 16, 0x1122334455667788)
    r.go()
    assert r.reg(0) == 0x1122334455667788 and r.reg(31) == SP - 16


def test_str_xzr_stores_zero(arch):
    r = Run(arch, 'STR_64_ldst_pos', imm12=1, Rn=31, Rt=31)
    r._wr(64)(SP + 8, M64)
    r.go()
    assert r._rd(64)(SP + 8) == [0]


def test_ldr_to_xzr_discarded(arch):
    r = Run(arch, 'LDR_64_ldst_pos', imm12=0, Rn=1, Rt=31).x(x1=0x1000)
    r._wr(64)(0x1000, 42)
    r.go()
    assert r.reg(31) == SP


# -- branches -----------------------------------------------------------------
def test_b_and_bl(arch):
    r = Run(arch, 'B_only_branch_imm', imm26=(-8 >> 2) & ((1 << 26) - 1)).go()
    assert r.branches == [PC - 8]
    r = Run(arch, 'BL_only_branch_imm', imm26=0x100).go()
    assert r.branches == [PC + 0x400] and r.reg(30) == PC + 4


@pytest.mark.parametrize('cond,nzcv,taken', [
    (0b0000, 0b0100, True), (0b0001, 0b0100, False),          # EQ / NE
    (0b1010, 0b1001, True), (0b1011, 0b1001, False),          # GE / LT (N == V)
    (0b1100, 0b0000, True), (0b1100, 0b0100, False),          # GT
    (0b1000, 0b0010, True), (0b1001, 0b0010, False),          # HI / LS
    (0b1110, 0b0000, True), (0b1111, 0b0000, True),           # AL / NV
])
def test_b_cond(arch, cond, nzcv, taken):
    r = Run(arch, 'B_only_condbranch', imm19=enc19(0x40), cond=cond).flags(nzcv).go()
    assert r.branches == ([PC + 0x40] if taken else [])


@pytest.mark.parametrize('name,value,taken', [
    ('CBZ_64_compbranch', 0, True), ('CBZ_64_compbranch', 1 << 40, False),
    ('CBZ_32_compbranch', 1 << 40, True), ('CBNZ_32_compbranch', 1 << 40, False),
    ('CBNZ_64_compbranch', 1 << 40, True),
])
def test_cbz(arch, name, value, taken):
    r = Run(arch, name, imm19=enc19(-4), Rt=3).x(x3=value).go()
    assert r.branches == ([PC - 4] if taken else [])


def test_cbz_xzr_always_taken(arch):
    r = Run(arch, 'CBZ_64_compbranch', imm19=enc19(8), Rt=31).go()
    assert r.branches == [PC + 8]


@pytest.mark.parametrize('name,bit,taken', [
    ('TBZ_only_testbranch', 40, False), ('TBZ_only_testbranch', 39, True),
    ('TBNZ_only_testbranch', 40, True), ('TBNZ_only_testbranch', 3, False),
])
def test_tbz(arch, name, bit, taken):
    r = Run(arch, name, b5=bit >> 5, b40=bit & 31, imm14=4, Rt=2).x(x2=1 << 40).go()
    assert r.branches == ([PC + 16] if taken else [])


def test_indirect_branches(arch):
    assert Run(arch, 'BR_64_branch_reg', Rn=5).x(x5=0xABC0).go().branches == [0xABC0]
    r = Run(arch, 'BLR_64_branch_reg', Rn=30).x(x30=0xABC0).go()      # target read before link
    assert r.branches == [0xABC0] and r.reg(30) == PC + 4
    assert Run(arch, 'RET_64R_branch_reg', Rn=30).x(x30=0x1234).go().branches == [0x1234]


# -- PC-relative, system ---------------------------------------------------------
def test_adr_adrp(arch):
    r = Run(arch, 'ADR_only_pcreladdr', immlo=0b11, immhi=(1 << 19) - 1, Rd=1).go()
    assert r.reg(1) == PC - 1
    r = Run(arch, 'ADRP_only_pcreladdr', immlo=1, immhi=0, Rd=1).go()
    assert r.reg(1) == (PC & ~0xFFF) + 0x1000


def test_ldr_literal(arch):
    r = Run(arch, 'LDRSW_64_loadlit', imm19=enc19(-8), Rt=4)
    r._wr(32)(PC - 8, 0x80000000)
    assert r.go().reg(4) == 0xFFFFFFFF80000000
    r = Run(arch, 'LDR_32_loadlit', imm19=enc19(12), Rt=4)
    r._wr(32)(PC + 12, 0xCAFEBABE)
    assert r.go().reg(4) == 0xCAFEBABE


def test_svc_and_nop(arch):
    assert Run(arch, 'SVC_EX_exception', imm16=0x80).go().svc == [0x80]
    r = Run(arch, 'NOP_HI_hints').go()
    assert r.branches == [] and r.reg(31) == SP


# -- ARMv8.1-8.9 general purpose (not all implemented by the test host) -----------
def test_cssc(arch):
    assert Run(arch, 'ABS_64_dp_1src', Rn=1, Rd=2).x(x1=-5).go().reg(2) == 5
    assert Run(arch, 'ABS_32_dp_1src', Rn=1, Rd=2).x(x1=0xFFFFFFFF_80000000).go().reg(2) == 0x80000000
    assert Run(arch, 'CNT_64_dp_1src', Rn=1, Rd=2).x(x1=0xF0F0).go().reg(2) == 8
    assert Run(arch, 'CTZ_32_dp_1src', Rn=1, Rd=2).x(x1=0).go().reg(2) == 32
    assert Run(arch, 'CTZ_64_dp_1src', Rn=1, Rd=2).x(x1=0x80).go().reg(2) == 7
    assert Run(arch, 'SMAX_64_minmax_imm', imm8=0x80, Rn=1, Rd=2).x(x1=-200).go().reg(2) == M64 - 127
    assert Run(arch, 'UMIN_32U_minmax_imm', imm8=0xFF, Rn=1, Rd=2).x(x1=0x1000).go().reg(2) == 0xFF
    assert Run(arch, 'SMIN_64_dp_2src', Rm=3, Rn=1, Rd=2).x(x1=-1, x3=1).go().reg(2) == M64
    assert Run(arch, 'UMAX_64_dp_2src', Rm=3, Rn=1, Rd=2).x(x1=-1, x3=1).go().reg(2) == M64


def test_bc_cond(arch):
    r = Run(arch, 'BC_only_condbranch', imm19=enc19(0x20), cond=0b0000).flags(0b0100).go()
    assert r.branches == [PC + 0x20]
    assert Run(arch, 'BC_only_condbranch', imm19=enc19(0x20), cond=0b0001).flags(0b0100).go().branches == []


def test_exclusive_pair_success(arch):
    """LDXR marks the monitor, a matching STXR stores and returns status 0."""
    r = Run(arch, 'LDXR_LR64_ldstexclr', Rn=1, Rt=2).x(x1=0x2000)
    r._wr(64)(0x2000, 77)
    r.go()
    assert r.reg(2) == 77
    assert ('exclusive_mark', 0x2000, 8) in r.calls
    s = Run(arch, 'STXR_SR64_ldstexclr', Rs=3, Rn=1, Rt=2).x(x1=0x2000, x2=99, x3=5)
    s.m.env['exclusive_check'] = lambda a, n: [1]
    s.go()
    assert s._rd(64)(0x2000) == [99] and s.reg(3) == 0


def test_mops_prologue_does_everything(arch):
    r = Run(arch, 'CPYP_CPY_memcms', sz=0, Rs=2, Rn=3, Rd=1).x(x1=0x100, x2=0x80, x3=0x40).go()
    assert ('mem_copy', 0x100, 0x80, 0x40, 1) in r.calls
    assert (r.reg(1), r.reg(2), r.reg(3)) == (0x140, 0xC0, 0)
    assert r.m.regs['NZCV'][0] == 0b0010
    back = Run(arch, 'CPYP_CPY_memcms', sz=0, Rs=2, Rn=3, Rd=1).x(x1=0x90, x2=0x80, x3=0x40).go()
    assert back.m.regs['NZCV'][0] == 0b1010                 # overlapping: backward
    assert ('mem_copy', 0x90, 0x80, 0x40, 1) in back.calls
    assert (back.reg(1), back.reg(2), back.reg(3)) == (0x90, 0x80, 0)   # copied down to the start
    # only address bits 55:0 decide the direction (tagged source)
    tagged = Run(arch, 'CPYP_CPY_memcms', sz=0, Rs=2, Rn=3, Rd=1).x(x1=0x90, x2=0x2A << 56 | 0x80, x3=0x40).go()
    assert tagged.m.regs['NZCV'][0] == 0b1010
    # ArchMaxMOPSCPYSize limits a copy; ArchMaxMOPSBlockSize a set
    big = Run(arch, 'CPYFP_CPY_memcms', sz=0, Rs=2, Rn=3, Rd=1).x(x1=0x100, x2=0x80, x3=-1).go()
    assert ('mem_copy', 0x100, 0x80, 0x007F_FFFF_FFFF_FFFF, 0) in big.calls
    assert (big.reg(1), big.reg(3)) == (0x100 + 0x007F_FFFF_FFFF_FFFF, 0)
    big = Run(arch, 'SETP_SET_memcms', sz=0, Rs=2, Rn=3, Rd=1).x(x1=0x100, x2=0, x3=-1).go()
    assert ('mem_set', 0x100, 0x7FFF_FFFF_FFFF_FFFF, 0) in big.calls
    s = Run(arch, 'SETP_SET_memcms', sz=0, Rs=2, Rn=3, Rd=1).x(x1=0x100, x2=0xAB, x3=0x10).go()
    assert ('mem_set', 0x100, 0x10, 0xAB) in s.calls and (s.reg(1), s.reg(3)) == (0x110, 0)


def test_pauth_uses_environment(arch):
    r = Run(arch, 'PACIASP_HI_hints').x(x30=0x1234)
    r.m.env['pac_add'] = lambda p, m, k: [p | (k << 56) | (m & 0xF) << 52]
    r.go()
    assert r.reg(30) == 0x1234 | (SP & 0xF) << 52                 # key IA = 0, modifier SP
    r = Run(arch, 'AUTDZB_64Z_dp_1src', Rd=4).x(x4=0x5555)
    r.m.env['pac_auth'] = lambda p, m, k: [p + m + k]
    assert r.go().reg(4) == 0x5555 + 0 + 3                         # zero modifier, key DB
    r = Run(arch, 'BLRAA_64P_branch_reg', Rn=1, Rm=2).x(x1=0x4000, x2=7)
    r.m.env['pac_auth'] = lambda p, m, k: [p ^ m]
    r.go()
    assert r.branches == [0x4000 ^ 7] and r.reg(30) == PC + 4


def test_system_hooks(arch):
    r = Run(arch, 'MRS_RS_systemmove_SYSREG', o0=1, op1=3, CRn=13, CRm=0, op2=2, Rt=5)   # TPIDR_EL0
    r.m.env['sysreg_read'] = lambda *f: [0xABC]
    assert r.go().reg(5) == 0xABC
    r = Run(arch, 'MSR_SR_systemmove_SYSREG', o0=1, op1=3, CRn=13, CRm=0, op2=2, Rt=5).x(x5=9).go()
    assert ('sysreg_write', 1, 3, 13, 0, 2, 9) in r.calls
    r = Run(arch, 'DMB_BO_barriers', CRm=0b1011).go()
    assert ('barrier', 0, 0b1011) in r.calls
    r = Run(arch, 'SYS_CR_systeminstrs', op1=3, CRn=7, CRm=4, op2=1, Rt=2).x(x2=0x8000).go()  # DC ZVA
    assert ('sys_op', 3, 7, 4, 1, 0x8000) in r.calls
    r = Run(arch, 'HVC_EX_exception', imm16=0x42).go()
    assert ('exception_call', 2, 0x42) in r.calls
    r = Run(arch, 'CFINV_M_pstate').flags(0b0010).go()
    assert r.m.regs['NZCV'][0] == 0b0000


def test_msr_immediate_fields(arch):
    """MSR (immediate) decodes only the PSTATE fields of the described profile."""
    m = Machine(arch)
    ins = next(i for i in arch.instructions if i.name == 'MSR_SI_pstate')
    def ok(op1, op2, crm=0):
        return m.valid_operands(ins, [op1, crm, op2])
    # UAO, PAN, SPSel, SSBS, DIT, DAIFSet, DAIFClr, ALLINT (CRm = 000x)
    assert all(ok(*f) for f in ((0, 3), (0, 4), (0, 5), (3, 1), (3, 2), (3, 6, 0xF), (3, 7, 0xF),
                                (1, 0, 1)))
    # PM (ALLINT's op1:op2 with CRm = 001x), TCO, SVCR (optional features), unallocated
    assert not any(ok(*f) for f in ((1, 0, 2), (3, 4), (3, 3, 2), (2, 0), (7, 7), (0, 6)))
    r = Run(arch, 'MSR_SI_pstate', op1=3, CRm=0b0010, op2=6).go()          # MSR DAIFSet, #2
    assert ('pstate_write', 3, 6, 0b0010) in r.calls
