"""Scalar floating-point instructions, SIMD&FP loads/stores and FPCR/FPSR access.

FP arithmetic uses standard float operations (`fop` statements, LIRA
docs/float_ops.md): they read FPCR (rounding mode, FZ, FZ16, DN) and set the
cumulative exception flags in FPSR. FPCR.AH/FIZ/NEP (FEAT_AFP) are not modeled
(treated as 0), nor are FPCR.AHP and trapped exceptions.
"""
from python.lira import float_ops as F

from .insns import _offset, sem
from .lib import S
from .xmlspec import Encoding

CMP_NZCV = {F.CMP_EQ: 0b0110, F.CMP_LT: 0b1000, F.CMP_GT: 0b0010, F.CMP_UN: 0b0011}
# Architected AArch64 FPCR/FPSR fields (without FEAT_AFP/FEAT_EBF16)
FPCR_MASK = 0x07FF9F00
FPSR_MASK = 0x0800009F


def fsize(e: Encoding, field: str = 'ftype') -> int:
    """8 << UInt(ftype XOR '10'): 00 -> 32, 01 -> 64, 11 -> 16."""
    return 8 << (e.fixed(field) ^ 0b10)


def fneg(s: S, x):
    return s.xor(x, s.c(1 << (x.width - 1), x.width))


def fabs(s: S, x):
    return s.and_(x, s.c((1 << (x.width - 1)) - 1, x.width))


def cmp_to_nzcv(s: S, rel):
    r = s.c(CMP_NZCV[F.CMP_UN], 4)
    for code in (F.CMP_GT, F.CMP_LT, F.CMP_EQ):
        r = s.select(s.eqc(rel, code), s.c(CMP_NZCV[code], 4), r)
    return r


def vfp_expand_imm(s: S, imm8, n: int):
    e, f = F.FORMATS[n][0], F.FORMATS[n][1]
    b6 = s.bits(imm8, 6, 1)
    exp = s.concat(s.not_(b6), s.replicate1(b6, e - 3), s.bits(imm8, 4, 2))
    return s.concat(s.bits(imm8, 7, 1), exp, s.bits(imm8, 0, 4), s.c(0, f - 4))


# -----------------------------------------------------------------------------
# Data processing
# -----------------------------------------------------------------------------
BINARY = {'fadd_float': 'fadd', 'fsub_float': 'fsub', 'fmul_float': 'fmul',
          'fdiv_float': 'fdiv', 'fnmul_float': 'fmul'}
MINMAX = {'fmax_float': 'fmax', 'fmin_float': 'fmin',
          'fmaxnm_float': 'fmaxnm', 'fminnm_float': 'fminnm'}


@sem(*BINARY)
def _fbinary(s: S, e: Encoding, F_):
    n = fsize(e)
    r = s.fop(BINARY[e.file], n, [s.v_read(F_('Rn'), n), s.v_read(F_('Rm'), n), s.rm(F.DYN)])
    s.v_write(F_('Rd'), fneg(s, r) if e.file == 'fnmul_float' else r)


@sem(*MINMAX)
def _fminmax(s: S, e: Encoding, F_):
    n = fsize(e)
    s.v_write(F_('Rd'), s.fop(MINMAX[e.file], n, [s.v_read(F_('Rn'), n), s.v_read(F_('Rm'), n)]))


@sem('fmadd_float', 'fmsub_float', 'fnmadd_float', 'fnmsub_float')
def _fmadd(s: S, e: Encoding, F_):
    n = fsize(e)
    a, x, y = s.v_read(F_('Ra'), n), s.v_read(F_('Rn'), n), s.v_read(F_('Rm'), n)
    if e.fixed('o1'):                          # FNMADD / FNMSUB: negated addend
        a = fneg(s, a)
    if e.fixed('o0') != e.fixed('o1'):         # FMSUB / FNMADD: negated product
        x = fneg(s, x)
    s.v_write(F_('Rd'), s.fop('fmuladd', n, [a, x, y, s.rm(F.DYN)]))


@sem('fabs_float', 'fneg_float', 'fmov_float', 'fsqrt_float')
def _funary(s: S, e: Encoding, F_):
    n = fsize(e)
    x = s.v_read(F_('Rn'), n)
    r = {'fabs_float': lambda: fabs(s, x), 'fneg_float': lambda: fneg(s, x), 'fmov_float': lambda: x,
         'fsqrt_float': lambda: s.fop('fsqrt', n, [x, s.rm(F.DYN)])}[e.file]()
    s.v_write(F_('Rd'), r)


FRINT = {'frintn_float': ('frint', F.RNE), 'frintp_float': ('frint', F.RTP),
         'frintm_float': ('frint', F.RTN), 'frintz_float': ('frint', F.RTZ),
         'frinta_float': ('frint', F.RNA), 'frinti_float': ('frint', F.DYN),
         'frintx_float': ('frintx', F.DYN)}


@sem(*FRINT)
def _frint(s: S, e: Encoding, F_):
    n = fsize(e)
    base, mode = FRINT[e.file]
    s.v_write(F_('Rd'), s.fop(base, n, [s.v_read(F_('Rn'), n), s.rm(mode)]))


@sem('fcvt_float')
def _fcvt(s: S, e: Encoding, F_):
    n, m = fsize(e), fsize(e, 'opc')
    s.v_write(F_('Rd'), s.fop('fcvtf', n, [s.v_read(F_('Rn'), n), s.rm(F.DYN)], m))


@sem('fcmp_float', 'fcmpe_float')
def _fcmp(s: S, e: Encoding, F_):
    n = fsize(e)
    op1 = s.v_read(F_('Rn'), n)
    op2 = s.c(0, n) if e.fixed('opc') & 1 else s.v_read(F_('Rm'), n)
    rel = s.fop('fcmps' if e.file == 'fcmpe_float' else 'fcmpq', n, [op1, op2])
    s.flags_write(cmp_to_nzcv(s, rel))


@sem('fccmp_float', 'fccmpe_float')
def _fccmp(s: S, e: Encoding, F_):
    n = fsize(e)
    holds = s.condition_holds(F_('cond'))
    # The comparison (and its exceptions) only happens when the condition holds
    op1, op2 = s.v_read(F_('Rn'), n), s.v_read(F_('Rm'), n)
    rel = s.fop('fcmps' if e.file == 'fccmpe_float' else 'fcmpq', n,
                [s.select(holds, op1, s.c(0, n)), s.select(holds, op2, s.c(0, n))])
    s.flags_write(s.select(holds, cmp_to_nzcv(s, rel), F_('nzcv')))


@sem('fcsel_float')
def _fcsel(s: S, e: Encoding, F_):
    n = fsize(e)
    s.v_write(F_('Rd'), s.select(s.condition_holds(F_('cond')),
                                 s.v_read(F_('Rn'), n), s.v_read(F_('Rm'), n)))


@sem('fmov_float_imm')
def _fmov_imm(s: S, e: Encoding, F_):
    n = fsize(e)
    s.v_write(F_('Rd'), vfp_expand_imm(s, F_('imm8'), n))


# -----------------------------------------------------------------------------
# Conversions between FP and general registers
# -----------------------------------------------------------------------------
FTOI = {}
for _r, _mode in (('n', F.RNE), ('a', F.RNA), ('p', F.RTP), ('m', F.RTN), ('z', F.RTZ)):
    FTOI[f'fcvt{_r}s_float'] = ('ftosi', _mode)
    FTOI[f'fcvt{_r}u_float'] = ('ftoui', _mode)
FTOI['fcvtzs_float_int'] = FTOI.pop('fcvtzs_float')
FTOI['fcvtzu_float_int'] = FTOI.pop('fcvtzu_float')
FTOI['fcvtzs_float_fix'] = ('ftosi', F.RTZ)
FTOI['fcvtzu_float_fix'] = ('ftoui', F.RTZ)
ITOF = {'scvtf_float_int': 'sitof', 'ucvtf_float_int': 'uitof',
        'scvtf_float_fix': 'sitof', 'ucvtf_float_fix': 'uitof'}


def _undef_fix(s: S, e: Encoding, F_):
    if e.fixed('sf') == 0:
        return s.not_(s.bits(F_('scale'), 5, 1))     # sf == '0' && scale[5] == '0'
    return None


def _fbits(s: S, e: Encoding, F_):
    if 'scale' in e.fields:
        return s.sub(s.c(64, 8), s.zext(F_('scale'), 8))
    return s.c(0, 8)


@sem(*[f for f in FTOI if f.endswith('_fix')], undef=_undef_fix)
@sem(*[f for f in FTOI if not f.endswith('_fix')])
def _ftoi(s: S, e: Encoding, F_):
    n, intsize = fsize(e), 32 << e.fixed('sf')
    base, mode = FTOI[e.file]
    r = s.fop(base, n, [s.v_read(F_('Rn'), n), _fbits(s, e, F_), s.rm(mode)], intsize)
    s.x_write(F_('Rd'), r)


@sem('scvtf_float_fix', 'ucvtf_float_fix', undef=_undef_fix)
@sem('scvtf_float_int', 'ucvtf_float_int')
def _itof(s: S, e: Encoding, F_):
    n, intsize = fsize(e), 32 << e.fixed('sf')
    r = s.fop(ITOF[e.file], intsize, [s.x_read(F_('Rn'), intsize), _fbits(s, e, F_), s.rm(F.DYN)], n)
    s.v_write(F_('Rd'), r)


@sem('fmov_float_gen')
def _fmov_gen(s: S, e: Encoding, F_):
    intsize = 32 << e.fixed('sf')
    to_fp = e.fixed('opcode') & 1
    if e.fixed('rmode') & 1:                   # V.D[1]
        if to_fp:
            low = s.v_read(F_('Rd'), 64)
            s.v_write(F_('Rd'), s.concat(s.x_read(F_('Rn'), 64), low))
        else:
            s.x_write(F_('Rd'), s.bits(s.b.read(s.ctx.rf_v, F_('Rn')), 64, 64))
        return
    n = fsize(e)
    if to_fp:
        s.v_write(F_('Rd'), s.trunc(s.x_read(F_('Rn'), intsize), n))
    else:
        s.x_write(F_('Rd'), s.v_read(F_('Rn'), n))


# -----------------------------------------------------------------------------
# SIMD&FP loads and stores
# -----------------------------------------------------------------------------
def _ldst_size(e: Encoding) -> int:
    return 128 if e.fixed('opc') >> 1 else 8 << e.fixed('size')


def _mem_read(s: S, addr, bits):
    if bits <= 128:
        return s.mem_read(addr, bits)
    lo = s.mem_read(addr, 128)
    hi = s.mem_read(s.add(addr, s.c(16, 64)), 128)
    return s.concat(hi, lo)


def _mem_write(s: S, addr, v):
    if v.width <= 128:
        return s.mem_write(addr, v)
    s.mem_write(addr, s.trunc(v, 128))
    s.mem_write(s.add(addr, s.c(16, 64)), s.bits(v, 128, 128))


def _undef_ldst_reg(s: S, e: Encoding, F_):
    return s.not_(s.bits(F_('option'), 1, 1)) if e.name.split('_')[-1].startswith('regoff') else None


@sem('ldr_imm_fpsimd', 'str_imm_fpsimd', 'ldur_fpsimd', 'stur_fpsimd')
@sem('ldr_reg_fpsimd', 'str_reg_fpsimd', undef=_undef_ldst_reg)
def _ldst_fp(s: S, e: Encoding, F_):
    bits = _ldst_size(e)
    scale = bits.bit_length() - 4
    load = e.fixed('opc') & 1
    mode = e.name.rsplit('_', 1)[1]
    if mode in ('immpost', 'immpre', 'unscaled'):
        offset = s.sext(F_('imm9'), 64)
    elif mode == 'pos':
        offset = s.lsl(s.zext(F_('imm12'), 64), s.c(scale, 64))
    else:
        shift = s.select(F_('S'), s.c(scale, 3), s.c(0, 3))
        offset = s.extend_reg(s.x_read(F_('Rm'), 64), F_('option'), shift)
    post, wback = mode == 'immpost', mode in ('immpost', 'immpre')
    base = s.xsp_read(F_('Rn'), 64)
    address = base if post else s.add(base, offset)
    if load:
        s.v_write(F_('Rt'), _mem_read(s, address, bits))
    else:
        _mem_write(s, address, s.v_read(F_('Rt'), bits))
    if wback:
        s.xsp_write(F_('Rn'), s.add(address, offset) if post else address)


@sem('ldp_fpsimd', 'stp_fpsimd', 'ldnp_fpsimd', 'stnp_fpsimd')
def _ldstp_fp(s: S, e: Encoding, F_):
    scale = 2 + e.fixed('opc')
    n = 8 << scale
    offset = s.lsl(s.sext(F_('imm7'), 64), s.c(scale, 64))
    mode = e.name.rsplit('_', 1)[1]
    post, wback = mode == 'post', mode in ('post', 'pre')
    base = s.xsp_read(F_('Rn'), 64)
    address = base if post else s.add(base, offset)
    if e.fixed('L'):
        data = _mem_read(s, address, 2 * n)
        s.v_write(F_('Rt'), s.trunc(data, n))
        s.v_write(F_('Rt2'), s.bits(data, n, n))
    else:
        _mem_write(s, address, s.concat(s.v_read(F_('Rt2'), n), s.v_read(F_('Rt'), n)))
    if wback:
        s.xsp_write(F_('Rn'), s.add(address, offset) if post else address)


@sem('ldr_lit_fpsimd')
def _ldr_lit_fp(s: S, e: Encoding, F_):
    address = s.add(s.pc(), _offset(s, F_('imm19')))
    s.v_write(F_('Rt'), s.mem_read(address, 32 << e.fixed('opc')))


# -----------------------------------------------------------------------------
# MRS / MSR for NZCV, FPCR, FPSR
# -----------------------------------------------------------------------------
# (o0, op1, CRn, CRm, op2) of op0=3 system registers
SYSREGS = {'NZCV': (1, 3, 4, 2, 0), 'FPCR': (1, 3, 4, 4, 0), 'FPSR': (1, 3, 4, 4, 1)}
SYSREG_SPECS = [(name, dict(zip(('o0', 'op1', 'CRn', 'CRm', 'op2'), v))) for name, v in SYSREGS.items()]
# Other system registers go to the environment; the specific ones above win
SYSREG_SPECS.append(('SYSREG', {}))


@sem('mrs', 'msr_reg', spec=SYSREG_SPECS)
def _mrs_msr(s: S, e: Encoding, F_):
    reg = e.name.rsplit('_', 1)[1]
    if reg == 'SYSREG':
        fields = [F_('o0'), F_('op1'), F_('CRn'), F_('CRm'), F_('op2')]
        if e.file == 'mrs':
            s.x_write(F_('Rt'), s.env(s.ctx.envs['sysreg_read'], fields)[0])
        else:
            s.env(s.ctx.envs['sysreg_write'], fields + [s.x_read(F_('Rt'), 64)])
        return
    if e.file == 'mrs':
        if reg == 'NZCV':
            v = s.lsl(s.zext(s.flags_read(), 64), s.c(28, 64))
        else:
            v = s.sysreg_read(s.ctx.rf_fpcr if reg == 'FPCR' else s.ctx.rf_fpsr)
        s.x_write(F_('Rt'), v)
    else:
        x = s.x_read(F_('Rt'), 64)
        if reg == 'NZCV':
            s.flags_write(s.bits(x, 28, 4))
        else:
            mask = FPCR_MASK if reg == 'FPCR' else FPSR_MASK
            s.sysreg_write(s.ctx.rf_fpcr if reg == 'FPCR' else s.ctx.rf_fpsr,
                           s.and_(s.trunc(x, 32), s.c(mask, 32)))
