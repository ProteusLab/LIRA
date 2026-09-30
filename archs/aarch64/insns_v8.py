"""ARMv8.1-8.9 general-purpose instructions and system instructions.

Behaviour that belongs to the memory system, pointer-authentication keys,
exception levels or system registers is delegated to environment functions
(see lib.Ctx): the exclusive monitor, PAC computation, MOPS copy/set,
barriers, hints, exceptions, SYS/SYSL and MRS/MSR of other system registers.
Acquire/release ordering has no effect on a single-threaded execution and
unprivileged (LDTR/STTR) accesses behave as normal accesses at EL0.
"""
from python.lira.ir import Shape

from . import insns
from .insns import LDST, LDST_ORDERED, _offset, sem
from .lib import S
from .xmlspec import Encoding

# -----------------------------------------------------------------------------
# Loads/stores reusing the base handlers
# -----------------------------------------------------------------------------
_V8_LDST = {
    'ldtr': (None, False, True), 'sttr': (None, False, False),
    'ldtrb': (8, False, True), 'sttrb': (8, False, False),
    'ldtrh': (16, False, True), 'sttrh': (16, False, False),
    'ldtrsb': (8, True, True), 'ldtrsh': (16, True, True), 'ldtrsw': (32, True, True),
    'ldapur_gen': (None, False, True), 'stlur_gen': (None, False, False),
    'ldapurb': (8, False, True), 'stlurb': (8, False, False),
    'ldapurh': (16, False, True), 'stlurh': (16, False, False),
    'ldapursb': (8, True, True), 'ldapursh': (16, True, True), 'ldapursw': (32, True, True),
}
LDST.update(_V8_LDST)
LDST_ORDERED.update(f for f in _V8_LDST if f.startswith(('ldapur', 'stlur')))
sem(*_V8_LDST)(insns._ldst)                                  # imm9 forms ('unpriv', 'unscaled')
sem('ldnp_gen', 'stnp_gen')(insns._ldstp)                    # signed offset pair, no writeback

# LRCPC3 writeback forms of LDAPR/STLR are an optional feature
insns.EXCLUDE.update({'LDAPR_32L_ldapstl_writeback', 'LDAPR_64L_ldapstl_writeback',
                      'STLR_32S_ldapstl_writeback', 'STLR_64S_ldapstl_writeback'})


def _size(e: Encoding) -> int:
    for f in ('size', 'sz'):
        if f in e.fields and e.fixed(f) is not None:
            return 8 << e.fixed(f)
    raise AssertionError(e.name)


def _regsize(bits):
    return 64 if bits == 64 else 32


ORDERED_LOAD = ('ldar', 'ldarb', 'ldarh', 'ldlar', 'ldlarb', 'ldlarh', 'ldapr', 'ldaprb', 'ldaprh')
ORDERED_STORE = ('stlr', 'stlrb', 'stlrh', 'stllr', 'stllrb', 'stllrh')


@sem(*ORDERED_LOAD, *ORDERED_STORE)
def _ordered(s: S, e: Encoding, F):
    bits = _size(e)
    address = s.xsp_read(F('Rn'), 64)
    s.check_alignment(address, bits)
    if e.file in ORDERED_LOAD:
        s.x_write(F('Rt'), s.zext(s.mem_read(address, bits), _regsize(bits)))
    else:
        s.mem_write(address, s.x_read(F('Rt'), bits))


@sem('prfm_imm', 'prfm_lit', 'prfm_reg', 'prfum')
def _prefetch(s: S, e: Encoding, F):
    """Prefetch hints have no architectural effect."""


# -----------------------------------------------------------------------------
# Exclusives (the monitor is part of the memory system: environment hooks)
# -----------------------------------------------------------------------------
LDX = ('ldxr', 'ldxrb', 'ldxrh', 'ldaxr', 'ldaxrb', 'ldaxrh', 'ldxp', 'ldaxp')
STX = ('stxr', 'stxrb', 'stxrh', 'stlxr', 'stlxrb', 'stlxrh', 'stxp', 'stlxp')


def _excl_size(e: Encoding):
    pair = e.file.endswith('p')
    el = (32 << e.fixed('sz')) if pair else _size(e)
    return el, pair


@sem(*LDX)
def _ldx(s: S, e: Encoding, F):
    el, pair = _excl_size(e)
    total = 2 * el if pair else el
    address = s.xsp_read(F('Rn'), 64)
    s.check_alignment(address, total, exclusive=True)
    data = s.mem_read(address, total)
    s.env(s.ctx.envs['exclusive_mark'], [address, s.c(total // 8, 8)])
    if pair:
        s.x_write(F('Rt'), s.trunc(data, el))
        s.x_write(F('Rt2'), s.bits(data, el, el))
    else:
        s.x_write(F('Rt'), s.zext(data, _regsize(el)))


@sem(*STX)
def _stx(s: S, e: Encoding, F):
    el, pair = _excl_size(e)
    total = 2 * el if pair else el
    address = s.xsp_read(F('Rn'), 64)
    s.check_alignment(address, total, exclusive=True)
    data = s.concat(s.x_read(F('Rt2'), el), s.x_read(F('Rt'), el)) if pair else s.x_read(F('Rt'), el)
    ok = s.env(s.ctx.envs['exclusive_check'], [address, s.c(total // 8, 8)])[0]
    s.cond_env(s.ctx.envs[f'mem_write_{total}'], ok, [address, data], [])
    s.x_write(F('Rs'), s.zext(s.not_(ok), 32))


@sem('clrex')
def _clrex(s: S, e: Encoding, F):
    s.env(s.ctx.envs['exclusive_clear'], [])


# -----------------------------------------------------------------------------
# LSE atomics
# -----------------------------------------------------------------------------
def _undef_casp(s: S, e: Encoding, F):
    return s.orr(s.bits(F('Rs'), 0, 1), s.bits(F('Rt'), 0, 1))


@sem('cas', 'casb', 'cash')
def _cas(s: S, e: Encoding, F):
    bits = _size(e)
    address = s.xsp_read(F('Rn'), 64)
    s.check_alignment(address, bits)
    data = s.mem_read(address, bits)
    hit = s.eq(data, s.x_read(F('Rs'), bits))
    s.cond_env(s.ctx.envs[f'mem_write_{bits}'], hit, [address, s.x_read(F('Rt'), bits)], [])
    s.x_write(F('Rs'), s.zext(data, _regsize(bits)))


def _next_reg(s: S, r):
    return s.add(r, s.c(1, 5))


@sem('casp', undef=_undef_casp)
def _casp(s: S, e: Encoding, F):
    n = 32 << e.fixed('sz')
    address = s.xsp_read(F('Rn'), 64)
    compare = s.concat(s.x_read(_next_reg(s, F('Rs')), n), s.x_read(F('Rs'), n))
    new = s.concat(s.x_read(_next_reg(s, F('Rt')), n), s.x_read(F('Rt'), n))
    s.check_alignment(address, 2 * n)
    data = s.mem_read(address, 2 * n)
    s.cond_env(s.ctx.envs[f'mem_write_{2 * n}'], s.eq(data, compare), [address, new], [])
    s.x_write(F('Rs'), s.trunc(data, n))
    s.x_write(_next_reg(s, F('Rs')), s.bits(data, n, n))


ATOMIC = {'ldadd': lambda s, a, b: s.add(a, b), 'ldclr': lambda s, a, b: s.and_(a, s.not_(b)),
          'ldeor': lambda s, a, b: s.xor(a, b), 'ldset': lambda s, a, b: s.orr(a, b),
          'ldsmax': lambda s, a, b: s.select(s.sgt(a, b), a, b),
          'ldsmin': lambda s, a, b: s.select(s.slt(a, b), a, b),
          'ldumax': lambda s, a, b: s.select(s.ugt(a, b), a, b),
          'ldumin': lambda s, a, b: s.select(s.ult(a, b), a, b),
          'swp': lambda s, a, b: b}
ATOMIC_FILES = {f + sfx: f for f in ATOMIC for sfx in ('', 'b', 'h')}


@sem(*ATOMIC_FILES)
def _atomic(s: S, e: Encoding, F):
    bits = _size(e)
    address = s.xsp_read(F('Rn'), 64)
    s.check_alignment(address, bits)
    data = s.mem_read(address, bits)
    s.mem_write(address, ATOMIC[ATOMIC_FILES[e.file]](s, data, s.x_read(F('Rs'), bits)))
    s.x_write(F('Rt'), s.zext(data, _regsize(bits)))              # Rt == 31: discarded


# -----------------------------------------------------------------------------
# CRC32, CSSC, flag manipulation, BC.cond
# -----------------------------------------------------------------------------
def _poly32_mod2(s: S, a):
    """Poly32Mod2(data, poly): reduce `data` (N bits) modulo the polynomial `poly`."""
    data, poly = a
    n = data.width
    p = s.zext(poly, n)
    for i in range(n - 1, 31, -1):
        reduced = s.xor(data, s.lsl(p, s.c(i - 32, n)))
        data = s.select(s.bits(data, i, 1), reduced, data)
    return [s.trunc(data, 32)]


@sem('crc32', 'crc32c')
def _crc32(s: S, e: Encoding, F):
    size = 8 << e.fixed('sz')
    poly = 0x1EDC6F41 if e.file == 'crc32c' else 0x04C11DB7
    acc = s.x_read(F('Rn'), 32)
    val = s.x_read(F('Rm'), size)
    n = 32 + size
    data = s.xor(s.lsl(s.zext(s.reverse(acc), n), s.c(size, n)),
                 s.lsl(s.zext(s.reverse(val), n), s.c(32, n)))
    mod = s.ctx.func_op(f'poly32_mod2_{n}', [n, 32], [32], _poly32_mod2)
    s.x_write(F('Rd'), s.reverse(s.call(mod, [data, s.c(poly, 32)])[0]))


def _ds(e):
    return 32 << e.fixed('sf')


@sem('abs', 'cnt', 'ctz')
def _cssc1(s: S, e: Encoding, F):
    n = _ds(e)
    x = s.x_read(F('Rn'), n)
    r = {'abs': lambda: s.select(s.slt(x, s.c(0, n)), s.neg(x), x),
         'cnt': lambda: s.popcnt(x), 'ctz': lambda: s.ctz(x)}[e.file]()
    s.x_write(F('Rd'), r)


MINMAX = {'smax': ('sgt', True), 'smin': ('slt', True), 'umax': ('ugt', False), 'umin': ('ult', False)}


@sem('smax_imm', 'smin_imm', 'umax_imm', 'umin_imm', 'smax_reg', 'smin_reg', 'umax_reg', 'umin_reg')
def _cssc_minmax(s: S, e: Encoding, F):
    n = _ds(e)
    cmp, signed = MINMAX[e.file[:4]]
    a = s.x_read(F('Rn'), n)
    if e.file.endswith('_imm'):
        b = (s.sext if signed else s.zext)(F('imm8'), n)
    else:
        b = s.x_read(F('Rm'), n)
    s.x_write(F('Rd'), s.select(getattr(s, cmp)(a, b), a, b))


def _nzcv_bits(s: S):
    f = s.flags_read()
    return [s.bits(f, i, 1) for i in (3, 2, 1, 0)]       # N, Z, C, V


@sem('cfinv', 'axflag', 'xaflag')
def _flagm(s: S, e: Encoding, F):
    n, z, c, v = _nzcv_bits(s)
    zero = s.c(0, 1)
    if e.file == 'cfinv':
        s.flags_write(s.concat(n, z, s.not_(c), v))
    elif e.file == 'axflag':
        s.flags_write(s.concat(zero, s.orr(z, v), s.and_(c, s.not_(v)), zero))
    else:
        s.flags_write(s.concat(s.and_(s.not_(c), s.not_(z)), s.and_(z, c), s.orr(c, z),
                               s.and_(s.not_(c), z)))


@sem('rmif')
def _rmif(s: S, e: Encoding, F):
    reg = s.x_read(F('Rn'), 64)
    flags = s.trunc(s.ror(reg, s.zext(F('imm6'), 64)), 4)
    mask = F('mask')
    s.flags_write(s.orr(s.and_(flags, mask), s.and_(s.flags_read(), s.not_(mask))))


@sem('setf')
def _setf(s: S, e: Encoding, F):
    size = 8 << e.fixed('sz')
    reg = s.x_read(F('Rn'), 32)
    n, z, c, v = _nzcv_bits(s)
    top = s.bits(reg, size - 1, 1)
    s.flags_write(s.concat(top, s.eqc(s.trunc(reg, size), 0), c, s.xor(s.bits(reg, size, 1), top)))


@sem('bc_cond')
def _bc(s: S, e: Encoding, F):
    target = s.add(s.pc(), _offset(s, F('imm19')))
    s.branch_if(s.condition_holds(F('cond')), target)


# -----------------------------------------------------------------------------
# MOPS: CPY*/SET*. Implementation choice (Option B): the prologue performs the
# whole operation through the environment; main/epilogue then have nothing
# left (Xn == 0) or finish a copy left by another prologue.
# -----------------------------------------------------------------------------
CPY_FILES = [p + opts for p in ('cpyf', 'cpy') for opts in
             ('p', 'pn', 'prn', 'prt', 'prtn', 'prtrn', 'prtwn', 'pt', 'ptn', 'ptrn', 'ptwn',
              'pwn', 'pwt', 'pwtn', 'pwtrn', 'pwtwn')]
SET_FILES = ['setp', 'setpn', 'setpt', 'setptn']
MOPS_CPY_MAX = 0x007FFFFFFFFFFFFF                           # ArchMaxMOPSCPYSize
MOPS_SET_MAX = 0x7FFFFFFFFFFFFFFF                           # ArchMaxMOPSBlockSize


def _undef_mops(s: S, e: Encoding, F):
    """sz != 00; overlapping registers or register 31 (CONSTRAINED UNPREDICTABLE:
    UNDEFINED chosen). For SET*, Xs may be XZR."""
    d, src, n = F('Rd'), F('Rs'), F('Rn')
    bad = [s.eq(src, n), s.eq(src, d), s.eq(n, d), s.eqc(d, 31), s.eqc(n, 31)]
    if not e.file.startswith('set'):
        bad.append(s.eqc(src, 31))
    if 'sz' in {f.name for f in e.operands}:
        bad.append(s.not_(s.eqc(F('sz'), 0)))
    return s.or1(*bad)


@sem(*CPY_FILES, undef=_undef_mops)
def _cpy(s: S, e: Encoding, F):
    stage = e.fixed('op1')                                  # 0 prologue, 1 main, 2 epilogue
    forward_only = e.file.startswith('cpyf')
    d, src, n = s.x_read(F('Rd'), 64), s.x_read(F('Rs'), 64), s.x_read(F('Rn'), 64)
    if stage == 0:
        size = s.select(s.ugt(n, s.c(MOPS_CPY_MAX, 64)), s.c(MOPS_CPY_MAX, 64), n)
        s.env(s.ctx.envs['mem_copy'], [d, src, size, s.c(0 if forward_only else 1, 1)])
        end_d, end_s = s.add(d, size), s.add(src, size)
        if forward_only:
            s.flags_write(s.c(0b0010, 4))
        else:
            # IsMemCpyForward: backward if the source overlaps the start of the
            # destination (addresses [55:0]); a backward copy ends at Xd, Xs
            src56, d56 = s.zext(s.trunc(src, 56), 64), s.zext(s.trunc(d, 56), 64)
            backward = s.and_(s.ult(src56, d56), s.ugt(s.add(src56, size), d56))
            end_d, end_s = s.select(backward, d, end_d), s.select(backward, src, end_s)
            s.flags_write(s.select(backward, s.c(0b1010, 4), s.c(0b0010, 4)))
        s.x_write(F('Rd'), end_d)
        s.x_write(F('Rs'), end_s)
        s.x_write(F('Rn'), s.c(0, 64))
    else:
        # Remaining Xn bytes: forward from Xd/Xs, or backward below them (N set)
        back = s.bits(s.flags_read(), 3, 1)
        lo_d = s.select(back, s.sub(d, n), d)
        lo_s = s.select(back, s.sub(src, n), src)
        s.env(s.ctx.envs['mem_copy'], [lo_d, lo_s, n, s.c(0 if forward_only else 1, 1)])
        s.x_write(F('Rd'), s.select(back, s.sub(d, n), s.add(d, n)))
        s.x_write(F('Rs'), s.select(back, s.sub(src, n), s.add(src, n)))
        s.x_write(F('Rn'), s.c(0, 64))


@sem(*SET_FILES, undef=_undef_mops)
def _set(s: S, e: Encoding, F):
    d, n = s.x_read(F('Rd'), 64), s.x_read(F('Rn'), 64)
    size = s.select(s.ugt(n, s.c(MOPS_SET_MAX, 64)), s.c(MOPS_SET_MAX, 64), n)
    s.env(s.ctx.envs['mem_set'], [d, size, s.x_read(F('Rs'), 8)])
    s.x_write(F('Rd'), s.add(d, size))
    s.x_write(F('Rn'), s.c(0, 64))
    if e.fixed('op2') >> 2 == 0:                            # prologue sets the option flags
        s.flags_write(s.c(0b0010, 4))


# -----------------------------------------------------------------------------
# Pointer authentication (PAC computation and keys: environment)
# -----------------------------------------------------------------------------
KEYS = {'ia': 0, 'ib': 1, 'da': 2, 'db': 3}


def _key(e: Encoding) -> int:
    name = e.name.split('_')[0].lower()
    for k, v in KEYS.items():
        if name[3:5] == k:
            return v
    raise AssertionError(e.name)


def _pac_regs(s: S, e: Encoding, F):
    """(destination index, value, modifier) of PAC*/AUT* forms."""
    variant = e.name.split('_')[0][5:]           # '', 'Z', '1716', 'SP'
    if variant == '1716':
        return s.c(17, 5), s.x_read(s.c(17, 5), 64), s.x_read(s.c(16, 5), 64)
    if variant in ('SP', 'Z') and 'hints' in e.name:
        mod = s.xsp_read(s.c(31, 5), 64) if variant == 'SP' else s.c(0, 64)
        return s.c(30, 5), s.x_read(s.c(30, 5), 64), mod
    if e.name.split('_')[0][3] == 'Z' or e.name.split('_')[0][4] == 'Z':   # PACIZA, AUTDZB, ...
        return F('Rd'), s.x_read(F('Rd'), 64), s.c(0, 64)
    return F('Rd'), s.x_read(F('Rd'), 64), s.xsp_read(F('Rn'), 64)


def _pac_key(e: Encoding) -> int:
    m = e.name.split('_')[0]                     # PACIA, PACIZA, AUTDZB, PACIA1716 ...
    letters = m[3:].replace('Z', '')[:2].lower()
    return KEYS[letters]


@sem('pacia', 'pacib', 'pacda', 'pacdb', 'autia', 'autib', 'autda', 'autdb')
def _pac(s: S, e: Encoding, F):
    idx, value, mod = _pac_regs(s, e, F)
    fn = 'pac_add' if e.file.startswith('pac') else 'pac_auth'
    s.x_write(idx, s.env(s.ctx.envs[fn], [value, mod, s.c(_pac_key(e), 3)])[0])


@sem('xpac')
def _xpac(s: S, e: Encoding, F):
    if 'hints' in e.name:                        # XPACLRI
        idx, data = s.c(30, 5), 0
    else:
        idx, data = F('Rd'), int(e.name.startswith('XPACD'))
    s.x_write(idx, s.env(s.ctx.envs['pac_strip'], [s.x_read(idx, 64), s.c(data, 1)])[0])


@sem('pacga')
def _pacga(s: S, e: Encoding, F):
    r = s.env(s.ctx.envs['pac_generic'], [s.x_read(F('Rn'), 64), s.xsp_read(F('Rm'), 64)])[0]
    s.x_write(F('Rd'), r)


@sem('blra', 'bra')
def _bra(s: S, e: Encoding, F):
    m = e.name.split('_')[0]                     # BLRAA, BLRAAZ, BRAB, ...
    key = 0 if m.rstrip('Z')[-1] == 'A' else 1
    mod = s.c(0, 64) if m.endswith('Z') else s.xsp_read(F('Rm'), 64)
    target = s.env(s.ctx.envs['pac_auth'], [s.x_read(F('Rn'), 64), mod, s.c(key, 3)])[0]
    if e.file == 'blra':
        s.x_write_n(30, s.add(s.pc(), s.c(4, 64)))
    s.branch(target)


@sem('reta')
def _reta(s: S, e: Encoding, F):
    key = 0 if e.name.startswith('RETAA') else 1
    lr = s.x_read(s.c(30, 5), 64)
    s.branch(s.env(s.ctx.envs['pac_auth'], [lr, s.xsp_read(s.c(31, 5), 64), s.c(key, 3)])[0])


@sem('ldra')
def _ldra(s: S, e: Encoding, F):
    key = 2 if e.name.startswith('LDRAA') else 3
    base = s.env(s.ctx.envs['pac_auth'], [s.xsp_read(F('Rn'), 64), s.c(0, 64), s.c(key, 3)])[0]
    offset = s.lsl(s.sext(s.concat(F('S'), F('imm9')), 64), s.c(3, 64))
    address = s.add(base, offset)
    s.x_write(F('Rt'), s.mem_read(address, 64))
    if e.name.split('_')[1] == '64W':
        s.xsp_write(F('Rn'), address)


# -----------------------------------------------------------------------------
# System instructions (environment hooks)
# -----------------------------------------------------------------------------
@sem('hint')
def _hint_other(s: S, e: Encoding, F):
    """Hints without a separate description (unallocated, or optional
    features that are not modeled) execute as NOP."""


HINTS = {'yield': 0b0000001, 'wfe': 0b0000010, 'wfi': 0b0000011, 'sev': 0b0000100,
         'sevl': 0b0000101}


@sem(*HINTS)
def _hint(s: S, e: Encoding, F):
    s.env(s.ctx.envs['hint'], [s.c(HINTS[e.file], 7)])


@sem('wfet', 'wfit')
def _wfxt(s: S, e: Encoding, F):
    s.env(s.ctx.envs['wait_timeout'], [s.c(int(e.file == 'wfit'), 1), s.x_read(F('Rd'), 64)])


BARRIERS = {'dmb': 0, 'dsb': 1, 'isb': 2, 'sb': 3, 'csdb': 4, 'esb': 5, 'clrbhb': 6}


@sem(*BARRIERS)
def _barrier(s: S, e: Encoding, F):
    kind = BARRIERS[e.file]
    if e.name == 'DSB_BOn_barriers':                        # DSB <option>nXS
        kind, option = 7, s.zext(F('imm2'), 4)
    elif 'CRm' in {f.name for f in e.operands}:
        option = F('CRm')
    else:
        option = s.c(0, 4)
    s.env(s.ctx.envs['barrier'], [s.c(kind, 4), option])


@sem('bti')
def _bti(s: S, e: Encoding, F):
    s.env(s.ctx.envs['branch_target'], [s.bits(F('op2'), 1, 2)])


EXCEPTIONS = {'brk': 0, 'hlt': 1, 'hvc': 2, 'smc': 3, 'udf_perm_undef': 4}


@sem(*EXCEPTIONS)
def _exception(s: S, e: Encoding, F):
    s.env(s.ctx.envs['exception_call'], [s.c(EXCEPTIONS[e.file], 3), F('imm16')])


@sem('dcps1', 'dcps2', 'dcps3')
def _dcps(s: S, e: Encoding, F):
    s.env(s.ctx.envs['debug_state'], [s.c(int(e.file[-1]), 2)])


@sem('eret', 'ereta', 'drps')
def _eret(s: S, e: Encoding, F):
    kind = {'ERET_64E_branch_reg': 0, 'ERETAA_64E_branch_reg': 1, 'ERETAB_64E_branch_reg': 2,
            'DRPS_64E_branch_reg': 3}[e.name]
    s.env(s.ctx.envs['exception_return'], [s.c(kind, 2)])


def _sysfields(F):
    return [F('op1'), F('CRn'), F('CRm'), F('op2')]


@sem('sys')
def _sys(s: S, e: Encoding, F):
    s.env(s.ctx.envs['sys_op'], _sysfields(F) + [s.x_read(F('Rt'), 64)])


@sem('sysl')
def _sysl(s: S, e: Encoding, F):
    s.x_write(F('Rt'), s.env(s.ctx.envs['sys_op_read'], _sysfields(F))[0])


# op1:op2 of the PSTATE fields MSR (immediate) can write: UAO, PAN, SPSel, SSBS,
# DIT, DAIFSet, DAIFClr. ALLINT (op1:op2 = 001:000) also needs CRm = 000x. The
# fields of optional features that are not described (TCO/MTE, SVCR/SME, PM)
# are UNDEFINED, like unallocated values; the EL checks are the environment's
# (`pstate_write`)
MSR_IMM_FIELDS = (0o03, 0o04, 0o05, 0o31, 0o32, 0o36, 0o37)
MSR_IMM_ALLINT = 0o10


def _undef_msr_imm(s: S, e: Encoding, F):
    field = s.concat(F('op1'), F('op2'))
    ok = [s.eqc(field, v) for v in MSR_IMM_FIELDS]
    ok.append(s.and_(s.eqc(field, MSR_IMM_ALLINT), s.eqc(s.bits(F('CRm'), 1, 3), 0)))
    return s.not_(s.or1(*ok))


@sem('msr_imm', undef=_undef_msr_imm)
def _msr_imm(s: S, e: Encoding, F):
    s.env(s.ctx.envs['pstate_write'], [F('op1'), F('op2'), F('CRm')])
