"""SVE instructions (FEAT_SVE).

Vectors are scalable: VL = 128 * VQ bits, and an operand of esize-bit elements
has the shape `<128/esize>VQ` (`zs(esize)`), so one description serves every
vector length. Encodings with an element size (`size`, `tszh:tszl`, ...) are
split into one LIRA instruction per size, like the Advanced SIMD arrangements
(e.g. `add_z_zz_S`); reserved sizes are not generated.

Predicates: `S.p_read` gives one bit per element (the lowest bit of each
esize/8-bit predicate element) and `S.p_write` writes elements with the other
bits cleared, as the ASL does. Element loops become lane-wise statements; the
ASL helpers that scan a predicate (FirstActive, LastActive, PredTest,
DecodePredCount, ...) are `fold`s over the lanes. The ASL reads of inactive
operands (`if AnyActiveElement(...) then Z[m] else Zeros()`) do not change the
result and are not modeled.

Only the FEAT_SVE encodings of the XML files are described; the encodings of
later extensions in the same files (e.g. the FEAT_SVE2p2 zeroing forms) are
left out.
"""
from typing import Callable, Dict

from python.lira.ir import Shape
from python.lira.ir_ops import Add, Orr

from . import insns
from .insns import sem
from .insns_simd import _binop, _fits, ext, sat, smax, smin, umax, umin
from .lib import S, VQ
from .xmlspec import Encoding

BASE_FEATURES = {'FEAT_SVE || FEAT_SME', 'FEAT_SVE', 'FEAT_SVE || FEAT_SSVE_FEXPA'}
SVE_FILES: set = set()
insns.KEEP.append(lambda e: e.file not in SVE_FILES or e.feature in BASE_FEATURES)

T = {8: 'B', 16: 'H', 32: 'S', 64: 'D'}
ES = {v: k for k, v in T.items()}
IW = 16                 # width of lane indices (at most 256 lanes)
NONE = (1 << IW) - 1    # index of no lane


def sve(*files, spec=None, undef=None):
    SVE_FILES.update(files)
    return sem(*files, spec=spec, undef=undef)


# -----------------------------------------------------------------------------
# Element size specializations
# -----------------------------------------------------------------------------
def field_spec(field: str, names: Dict[int, str]):
    """One instruction per value of `field` (`{value: suffix}`)."""
    def spec(e: Encoding):
        if field not in {f.name for f in e.operands}:
            return None
        return [(n, {field: v}) for v, n in names.items() if _fits(e, {field: v})] or None
    return spec


def size_spec(sizes=(0, 1, 2, 3), field='size'):
    """Element size `8 << field`: suffix B/H/S/D."""
    return field_spec(field, {sz: T[8 << sz] for sz in sizes})


def product(*specs):
    """All combinations of several specializations (suffixes joined by `_`)."""
    def spec(e: Encoding):
        out = [('', {})]
        for sp in specs:
            r = sp(e)
            if r:
                out = [(f'{a}_{b}' if a else b, {**x, **y}) for a, x in out for b, y in r]
        return [o for o in out if o[0]] or None
    return spec


SF = field_spec('sf', {0: 'W', 1: 'X'})
SZ = field_spec('sz', {0: 'W', 1: 'X'})                  # register size
SZ_ELEM = field_spec('sz', {0: 'S', 1: 'D'})            # element size 32 << sz


def tsz_spec(e: Encoding):
    """tsize = tszh:tszl: esize = 8 << HighestSetBit(tsize); tsize = 0 is UNDEFINED."""
    return [('B', {'tszh': 0, 'tszl': 1}), ('H', {'tszh': 0, 'tszl': (2, 2)}),
            ('S', {'tszh': 1}), ('D', {'tszh': (2, 2)})]


def es(e: Encoding) -> int:
    """Element size of a specialized instruction (its B/H/S/D suffix)."""
    return ES[e.name.rsplit('_', 1)[1]]


def mn_es(e: Encoding) -> int:
    """Element size given by the last letter of the mnemonic (CNTB, INCW, ...)."""
    return {'B': 8, 'H': 16, 'W': 32, 'D': 64}[e.mnemonic[-1]]


# -----------------------------------------------------------------------------
# Lane helpers
# -----------------------------------------------------------------------------
def zs(esize: int) -> Shape:
    """Shape of a vector of esize-bit elements: VL / esize lanes."""
    return Shape(128 // esize, VQ)


def iota(s: S, esize: int, w: int = IW):
    return s.b.index(w, zs(esize))


def rep(s: S, v, esize: int):
    """Scalar v in every element."""
    return s.b.replicate(v, zs(esize))


def fold1(s: S, op, init, v):
    return s.b.fold(op, [init], [v])[0]


def count(s: S, bits):
    """Number of set predicate bits, 64-bit."""
    return fold1(s, Add(64), s.c(0, 64), s.zext(bits, 64))


def elements(s: S, esize: int):
    """VL / esize, 64-bit."""
    return fold1(s, Add(64), s.c(0, 64), s.c(1, 64, zs(esize)))


def first_index(s: S, bits):
    """Index of the first set bit, NONE if there is none."""
    esize = 128 // bits.lanes
    idx = s.select(bits, iota(s, esize), s.c(NONE, IW, bits.shape))
    return fold1(s, _binop(s, 'umin', umin, IW), s.c(NONE, IW), idx)


def last_index_plus1(s: S, bits):
    """Index after the last set bit, 0 if there is none."""
    esize = 128 // bits.lanes
    idx = s.select(bits, s.add(iota(s, esize), s.c(1, IW, bits.shape)), s.c(0, IW, bits.shape))
    return fold1(s, _binop(s, 'umax', umax, IW), s.c(0, IW), idx)


def lanes_before(s: S, idx, esize: int, inclusive=False):
    """Element e < idx (or <= idx)."""
    cmp = s.ule if inclusive else s.ult
    return cmp(iota(s, esize), rep(s, idx, esize))


def ones(s: S, esize: int):
    return s.c(1, 1, zs(esize))


def _pred_test_step(s: S, a):
    found, first, none, last, m, r = a
    act = s.and_(m, r)
    return [s.orr(found, m), s.select(found, first, act), s.and_(none, s.not_(act)),
            s.select(m, r, last)]


def pred_scan(s: S, mask, x):
    """(FirstActive, NoneActive, LastActive)(mask, x)."""
    op = s.ctx.func_op('pred_test_step', [1] * 6, [1] * 4, _pred_test_step)
    c0, c1 = s.c(0, 1), s.c(1, 1)
    _, first, none, last = s.b.fold(op, [c0, c0, c1, c0], [mask, x])
    return first, none, last


def pred_test(s: S, mask, result):
    """PredTest(mask, result, esize): N = first active, Z = none active,
    C = NOT last active, V = 0."""
    first, none, last = pred_scan(s, mask, result)
    return s.concat(first, none, s.not_(last), s.c(0, 1))


def _floor_pow2(s: S, n):
    return s.lsl(s.c(1, 64), s.sub(s.c(63, 64), s.clz(n)))


def _decode_pred_count(s: S, a):
    pat, n = a
    r = s.c(0, 64)
    for p, k in [(i, i) for i in range(1, 9)] + [(9 + i, 16 << i) for i in range(5)]:
        r = s.select(s.eqc(pat, p), s.select(s.uge(n, s.c(k, 64)), s.c(k, 64), s.c(0, 64)), r)
    r = s.select(s.eqc(pat, 0), _floor_pow2(s, n), r)
    r = s.select(s.eqc(pat, 0b11101), s.sub(n, s.rem_u(n, s.c(4, 64))), r)
    r = s.select(s.eqc(pat, 0b11110), s.sub(n, s.rem_u(n, s.c(3, 64))), r)
    return [s.select(s.eqc(pat, 0b11111), n, r)]


def pred_count(s: S, pattern, esize: int):
    """DecodePredCount(pattern, esize), 64-bit."""
    op = s.ctx.func_op('decode_pred_count', [5, 64], [64], _decode_pred_count)
    return s.call(op, [pattern, elements(s, esize)])[0]


def vl_bytes(s: S):
    """VL / 8 = 16 * VQ, 64-bit."""
    return s.lsl(s.vq(), s.c(4, 64))


def _merge(s: S, pg, active, inactive):
    return s.select(pg, active, inactive)


def ffr_read(s: S):
    return s.p_read(s.c(0, 1), 8, s.ctx.rf_ffr)


def ffr_write(s: S, bits):
    s.p_write(s.c(0, 1), bits, s.ctx.rf_ffr)


def ucmp(s: S, op: str, a, b, unsigned: bool):
    """Cmp_<op> on two integers of equal width."""
    return {'EQ': lambda: s.eq(a, b), 'NE': lambda: s.ne(a, b),
            'GT': lambda: (s.ugt if unsigned else s.sgt)(a, b),
            'GE': lambda: (s.uge if unsigned else s.sge)(a, b),
            'LT': lambda: (s.ult if unsigned else s.slt)(a, b),
            'LE': lambda: (s.ule if unsigned else s.sle)(a, b)}[op]()


def wide_elements(s: S, idx, esize: int):
    """operand[(e * esize) DIV 64] as 64-bit values in esize-bit elements."""
    v = s.z_read(idx, 64)
    if esize == 64:
        return v
    k = (64 // esize).bit_length() - 1
    sel = s.lsr(iota(s, esize), s.c(k, IW, zs(esize)))
    return s.b.gather(v, sel, s.c(0, 64, zs(esize)))


# -----------------------------------------------------------------------------
# Predicate logic, breaks, PTRUE, PTEST, FFR
# -----------------------------------------------------------------------------
PLOGIC: Dict[str, Callable] = {
    'AND': lambda s, a, b: s.and_(a, b), 'BIC': lambda s, a, b: s.and_(a, s.not_(b)),
    'EOR': lambda s, a, b: s.xor(a, b), 'NAND': lambda s, a, b: s.not_(s.and_(a, b)),
    'NOR': lambda s, a, b: s.not_(s.orr(a, b)), 'ORN': lambda s, a, b: s.orr(a, s.not_(b)),
    'ORR': lambda s, a, b: s.orr(a, b),
}


@sve('and_p_p_pp', 'ands_p_p_pp', 'bic_p_p_pp', 'bics_p_p_pp', 'eor_p_p_pp', 'eors_p_p_pp',
     'nand_p_p_pp', 'nands_p_p_pp', 'nor_p_p_pp', 'nors_p_p_pp', 'orn_p_p_pp', 'orns_p_p_pp',
     'orr_p_p_pp', 'orrs_p_p_pp')
def _plogic(s: S, e: Encoding, F):
    flags = e.fixed('S')
    fn = PLOGIC[e.mnemonic[:-1] if flags else e.mnemonic]
    g = s.p_read(F('Pg'), 8)
    res = s.and_(g, fn(s, s.p_read(F('Pn'), 8), s.p_read(F('Pm'), 8)))
    if flags:
        s.flags_write(pred_test(s, g, res))
    s.p_write(F('Pd'), res)


@sve('sel_p_p_pp')
def _sel_p(s: S, e: Encoding, F):
    g = s.p_read(F('Pg'), 8)
    s.p_write(F('Pd'), s.select(g, s.p_read(F('Pn'), 8), s.p_read(F('Pm'), 8)))


@sve('brka_p_p_p', 'brkas_p_p_p', 'brkb_p_p_p', 'brkbs_p_p_p')
def _brk(s: S, e: Encoding, F):
    g = s.p_read(F('Pg'), 8)
    first = first_index(s, s.and_(g, s.p_read(F('Pn'), 8)))
    after = e.mnemonic.startswith('BRKA')
    active = lanes_before(s, first, 8, inclusive=after)
    inactive = s.c(0, 1, zs(8))
    if 'M' in e.fields and e.fixed('M') != 0:               # merging (M is an operand)
        inactive = s.and_(rep(s, F('M'), 8), s.p_read(F('Pd'), 8))
    res = s.select(g, active, inactive)
    if e.fixed('S'):
        s.flags_write(pred_test(s, g, res))
    s.p_write(F('Pd'), res)


@sve('brkn_p_p_pp', 'brkns_p_p_pp')
def _brkn(s: S, e: Encoding, F):
    _, _, last = pred_scan(s, s.p_read(F('Pg'), 8), s.p_read(F('Pn'), 8))
    res = s.and_(rep(s, last, 8), s.p_read(F('Pdm'), 8))
    if e.fixed('S'):
        s.flags_write(pred_test(s, ones(s, 8), res))
    s.p_write(F('Pdm'), res)


@sve('brkpa_p_p_pp', 'brkpas_p_p_pp', 'brkpb_p_p_pp', 'brkpbs_p_p_pp')
def _brkp(s: S, e: Encoding, F):
    g = s.p_read(F('Pg'), 8)
    _, _, last = pred_scan(s, g, s.p_read(F('Pn'), 8))
    first = first_index(s, s.and_(g, s.p_read(F('Pm'), 8)))
    before = lanes_before(s, first, 8, inclusive=e.mnemonic.startswith('BRKPA'))
    res = s.and1(g, rep(s, last, 8), before)
    if e.fixed('S'):
        s.flags_write(pred_test(s, g, res))
    s.p_write(F('Pd'), res)


@sve('ptest_p_p')
def _ptest(s: S, e: Encoding, F):
    s.flags_write(pred_test(s, s.p_read(F('Pg'), 8), s.p_read(F('Pn'), 8)))


@sve('pfirst_p_p_p')
def _pfirst(s: S, e: Encoding, F):
    g = s.p_read(F('Pg'), 8)
    first = first_index(s, g)
    res = s.orr(s.p_read(F('Pdn'), 8), s.eq(iota(s, 8), rep(s, first, 8)))
    s.flags_write(pred_test(s, g, res))
    s.p_write(F('Pdn'), res)


@sve('pnext_p_p_p', spec=size_spec())
def _pnext(s: S, e: Encoding, F):
    n = es(e)
    mask = s.p_read(F('Pv'), n)
    nxt = last_index_plus1(s, s.p_read(F('Pdn'), n))
    first = first_index(s, s.and_(mask, s.uge(iota(s, n), rep(s, nxt, n))))
    res = s.eq(iota(s, n), rep(s, first, n))
    s.flags_write(pred_test(s, mask, res))
    s.p_write(F('Pdn'), res)


@sve('ptrue_p_s', 'ptrues_p_s', spec=size_spec())
def _ptrue(s: S, e: Encoding, F):
    n = es(e)
    res = lanes_before(s, s.trunc(pred_count(s, F('pattern'), n), IW), n)
    if e.fixed('S'):
        s.flags_write(pred_test(s, res, res))
    s.p_write(F('Pd'), res)


@sve('pfalse_p')
def _pfalse(s: S, e: Encoding, F):
    s.p_write(F('Pd'), s.c(0, 1, zs(8)))


@sve('rdffr_p_f')
def _rdffr(s: S, e: Encoding, F):
    s.p_write(F('Pd'), ffr_read(s))


@sve('rdffr_p_p_f', 'rdffrs_p_p_f')
def _rdffr_p(s: S, e: Encoding, F):
    g = s.p_read(F('Pg'), 8)
    res = s.and_(ffr_read(s), g)
    if e.fixed('S'):
        s.flags_write(pred_test(s, g, res))
    s.p_write(F('Pd'), res)


@sve('setffr_f')
def _setffr(s: S, e: Encoding, F):
    ffr_write(s, ones(s, 8))


@sve('wrffr_f_p')
def _wrffr(s: S, e: Encoding, F):
    ffr_write(s, s.p_read(F('Pn'), 8))


# -----------------------------------------------------------------------------
# WHILE, CTERM
# -----------------------------------------------------------------------------
WHILE = {'WHILELT': ('LT', False), 'WHILELE': ('LE', False),
         'WHILELO': ('LT', True), 'WHILELS': ('LE', True)}


@sve('whilele_p_p_rr', 'whilelo_p_p_rr', 'whilels_p_p_rr', 'whilelt_p_p_rr',
     spec=product(SF, size_spec()))
def _while(s: S, e: Encoding, F):
    n = es(e)
    rsize = 32 << e.fixed('sf')
    op, unsigned = WHILE[e.mnemonic]
    op1 = s.x_read(F('Rn'), rsize)
    op2 = s.x_read(F('Rm'), rsize)
    # operand1 + e, wrapping in rsize bits; the predicate stops at the first false
    elem = s.add(rep(s, op1, n), s.zext(iota(s, n), rsize))
    cond = ucmp(s, op, elem, rep(s, op2, n), unsigned)
    res = lanes_before(s, first_index(s, s.not_(cond)), n)
    s.flags_write(pred_test(s, ones(s, n), res))
    s.p_write(F('Pd'), res)


@sve('ctermeq_rr', spec=SZ)
def _cterm(s: S, e: Encoding, F):
    w = 32 << e.fixed('sz')
    a, b = s.x_read(F('Rn'), w), s.x_read(F('Rm'), w)
    term = s.eq(a, b) if e.mnemonic == 'CTERMEQ' else s.ne(a, b)
    nzcv = s.flags_read()
    z, c = s.bits(nzcv, 2, 1), s.bits(nzcv, 1, 1)
    s.flags_write(s.concat(term, z, c, s.select(term, s.c(0, 1), s.not_(c))))


# -----------------------------------------------------------------------------
# Element counts: CNTP, INC/DEC by predicate count or pattern, ADDVL, RDVL
# -----------------------------------------------------------------------------
def _sat_scalar(s: S, x, delta, ssize: int, unsigned: bool, sub: bool):
    """(Un)signedSatQ(x +/- delta) on ssize bits, extended to 64 bits;
    delta is a non-negative 64-bit count."""
    w = 2 * ssize
    v = ext(s, x, w, not unsigned)
    d = s.zext(s.trunc(delta, min(64, w)), w)
    r, _ = sat(s, s.sub(v, d) if sub else s.add(v, d), ssize, unsigned)
    return ext(s, r, 64, not unsigned)


def _sat_vector(s: S, v, delta, unsigned: bool, sub: bool):
    """Lane-wise (Un)signedSatQ(v +/- delta); delta is a 64-bit scalar count."""
    n = v.width
    w = 2 * n
    x = ext(s, v, w, not unsigned)
    d = rep(s, s.zext(s.trunc(delta, min(64, w)), w), n)
    r, _ = sat(s, s.sub(x, d) if sub else s.add(x, d), n, unsigned)
    return r


@sve('cntp_r_p_p', spec=size_spec())
def _cntp(s: S, e: Encoding, F):
    n = es(e)
    s.x_write(F('Rd'), count(s, s.and_(s.p_read(F('Pg'), n), s.p_read(F('Pn'), n))))


@sve('decp_r_p_r', 'incp_r_p_r', 'sqdecp_r_p_r', 'sqincp_r_p_r', 'uqdecp_r_p_r', 'uqincp_r_p_r',
     spec=size_spec())
def _incp_r(s: S, e: Encoding, F):
    c = count(s, s.p_read(F('Pm'), es(e)))
    sub = 'DEC' in e.mnemonic
    if e.mnemonic in ('INCP', 'DECP'):
        x = s.x_read(F('Rdn'), 64)
        s.x_write(F('Rdn'), s.sub(x, c) if sub else s.add(x, c))
        return
    ssize = 32 << e.fixed('sf')
    unsigned = e.mnemonic.startswith('U')
    s.x_write(F('Rdn'), _sat_scalar(s, s.x_read(F('Rdn'), ssize), c, ssize, unsigned, sub))


@sve('decp_z_p_z', 'incp_z_p_z', 'sqdecp_z_p_z', 'sqincp_z_p_z', 'uqdecp_z_p_z', 'uqincp_z_p_z',
     spec=size_spec((1, 2, 3)))
def _incp_z(s: S, e: Encoding, F):
    n = es(e)
    c = count(s, s.p_read(F('Pm'), n))
    v = s.z_read(F('Zdn'), n)
    sub = 'DEC' in e.mnemonic
    if e.mnemonic in ('INCP', 'DECP'):
        d = rep(s, s.trunc(c, n), n)
        r = s.sub(v, d) if sub else s.add(v, d)
    else:
        r = _sat_vector(s, v, c, e.mnemonic.startswith('U'), sub)
    s.z_write(F('Zdn'), r)


@sve('cntb_r_s')
def _cnt(s: S, e: Encoding, F):
    c = pred_count(s, F('pattern'), mn_es(e))
    s.x_write(F('Rd'), s.mul(c, s.add(s.zext(F('imm4'), 64), s.c(1, 64))))


def _count_imm(s: S, e: Encoding, F):
    """DecodePredCount(pattern, esize) * imm."""
    c = pred_count(s, F('pattern'), mn_es(e))
    return s.mul(c, s.add(s.zext(F('imm4'), 64), s.c(1, 64)))


@sve('decb_r_rs', 'incb_r_rs', 'sqdecb_r_rs', 'sqdecd_r_rs', 'sqdech_r_rs', 'sqdecw_r_rs',
     'sqincb_r_rs', 'sqincd_r_rs', 'sqinch_r_rs', 'sqincw_r_rs', 'uqdecb_r_rs', 'uqdecd_r_rs',
     'uqdech_r_rs', 'uqdecw_r_rs', 'uqincb_r_rs', 'uqincd_r_rs', 'uqinch_r_rs', 'uqincw_r_rs')
def _incdec_r(s: S, e: Encoding, F):
    c = _count_imm(s, e, F)
    sub = 'DEC' in e.mnemonic
    if not e.mnemonic.startswith(('SQ', 'UQ')):
        x = s.x_read(F('Rdn'), 64)
        s.x_write(F('Rdn'), s.sub(x, c) if sub else s.add(x, c))
        return
    ssize = 32 << e.fixed('sf')
    unsigned = e.mnemonic.startswith('U')
    s.x_write(F('Rdn'), _sat_scalar(s, s.x_read(F('Rdn'), ssize), c, ssize, unsigned, sub))


@sve('decd_z_zs', 'incd_z_zs', 'sqdecd_z_zs', 'sqdech_z_zs', 'sqdecw_z_zs', 'sqincd_z_zs',
     'sqinch_z_zs', 'sqincw_z_zs', 'uqdecd_z_zs', 'uqdech_z_zs', 'uqdecw_z_zs', 'uqincd_z_zs',
     'uqinch_z_zs', 'uqincw_z_zs')
def _incdec_z(s: S, e: Encoding, F):
    n = mn_es(e)
    c = _count_imm(s, e, F)
    v = s.z_read(F('Zdn'), n)
    sub = 'DEC' in e.mnemonic
    if not e.mnemonic.startswith(('SQ', 'UQ')):
        d = rep(s, s.trunc(c, n), n)
        r = s.sub(v, d) if sub else s.add(v, d)
    else:
        r = _sat_vector(s, v, c, e.mnemonic.startswith('U'), sub)
    s.z_write(F('Zdn'), r)


@sve('addvl_r_ri', 'addpl_r_ri')
def _addvl(s: S, e: Encoding, F):
    unit = vl_bytes(s) if e.mnemonic == 'ADDVL' else s.lsl(s.vq(), s.c(1, 64))   # PL / 8 = 2 * VQ
    x = s.xsp_read(F('Rn'), 64)
    s.xsp_write(F('Rd'), s.add(x, s.mul(s.sext(F('imm6'), 64), unit)))


@sve('rdvl_r_i')
def _rdvl(s: S, e: Encoding, F):
    s.x_write(F('Rd'), s.mul(s.sext(F('imm6'), 64), vl_bytes(s)))


# -----------------------------------------------------------------------------
# Integer arithmetic and logic
# -----------------------------------------------------------------------------
def _abd(s, a, b, signed):
    gt = s.sgt(a, b) if signed else s.ugt(a, b)
    return s.select(gt, s.sub(a, b), s.sub(b, a))


def _mulh(s, a, b, signed):
    n = a.width
    return s.bits(s.mul(ext(s, a, 2 * n, signed), ext(s, b, 2 * n, signed)), n, n)


def _qaddsub(s, a, b, signed, sub):
    n = a.width
    x, y = ext(s, a, 2 * n, signed), ext(s, b, 2 * n, signed)
    return sat(s, s.sub(x, y) if sub else s.add(x, y), n, not signed)[0]


# Binary operations on elements; `R` suffixes are reversed in the callers
BINOP: Dict[str, Callable] = {
    'ADD': lambda s, a, b: s.add(a, b), 'SUB': lambda s, a, b: s.sub(a, b),
    'AND': lambda s, a, b: s.and_(a, b), 'ORR': lambda s, a, b: s.orr(a, b),
    'EOR': lambda s, a, b: s.xor(a, b), 'BIC': lambda s, a, b: s.and_(a, s.not_(b)),
    'MUL': lambda s, a, b: s.mul(a, b),
    'SMULH': lambda s, a, b: _mulh(s, a, b, True), 'UMULH': lambda s, a, b: _mulh(s, a, b, False),
    'SMAX': smax, 'SMIN': smin, 'UMAX': umax, 'UMIN': umin,
    'SABD': lambda s, a, b: _abd(s, a, b, True), 'UABD': lambda s, a, b: _abd(s, a, b, False),
    'SDIV': lambda s, a, b: s.div_s(a, b, s.cl(0, a)), 'UDIV': lambda s, a, b: s.div_u(a, b, s.cl(0, a)),
    # shifts by an element: Min(UInt(element2), esize) is what the operations do
    'ASR': lambda s, a, b: s.asr(a, b), 'LSL': lambda s, a, b: s.lsl(a, b),
    'LSR': lambda s, a, b: s.lsr(a, b),
    'SQADD': lambda s, a, b: _qaddsub(s, a, b, True, False),
    'SQSUB': lambda s, a, b: _qaddsub(s, a, b, True, True),
    'UQADD': lambda s, a, b: _qaddsub(s, a, b, False, False),
    'UQSUB': lambda s, a, b: _qaddsub(s, a, b, False, True),
}
REVERSED = {'SUBR': 'SUB', 'SDIVR': 'SDIV', 'UDIVR': 'UDIV', 'ASRR': 'ASR', 'LSLR': 'LSL', 'LSRR': 'LSR'}


def binop(s: S, mnemonic: str, a, b):
    if mnemonic in REVERSED:
        return BINOP[REVERSED[mnemonic]](s, b, a)
    return BINOP[mnemonic](s, a, b)


@sve('add_z_zz', 'sub_z_zz', 'sqadd_z_zz', 'sqsub_z_zz', 'uqadd_z_zz', 'uqsub_z_zz', spec=size_spec())
def _zz(s: S, e: Encoding, F):
    n = es(e)
    s.z_write(F('Zd'), binop(s, e.mnemonic, s.z_read(F('Zn'), n), s.z_read(F('Zm'), n)))


@sve('and_z_zz', 'orr_z_zz', 'eor_z_zz', 'bic_z_zz')
def _zz_logic(s: S, e: Encoding, F):
    s.z_write(F('Zd'), binop(s, e.mnemonic, s.z_read(F('Zn'), 64), s.z_read(F('Zm'), 64)))


def _undef_size_sh(s: S, e: Encoding, F):
    return F('sh') if es(e) == 8 else None                 # size:sh == '001'


@sve('add_z_zi', 'sub_z_zi', 'subr_z_zi', 'sqadd_z_zi', 'sqsub_z_zi', 'uqadd_z_zi', 'uqsub_z_zi',
     spec=size_spec(), undef=_undef_size_sh)
def _zi_sh(s: S, e: Encoding, F):
    n = es(e)
    imm = s.zext(F('imm8'), 16)
    imm = s.select(F('sh'), s.lsl(imm, s.c(8, 16)), imm)
    a = s.z_read(F('Zdn'), n)
    if e.mnemonic in ('SQADD', 'SQSUB', 'UQADD', 'UQSUB'):
        # SatQ(element +/- UInt(imm)): imm is unsigned, at most 16 bits
        signed = e.mnemonic[0] == 'S'
        w = 2 * n
        x = ext(s, a, w, signed)
        y = rep(s, s.zext(imm, w), n)
        r = sat(s, s.sub(x, y) if e.mnemonic.endswith('SUB') else s.add(x, y), n, not signed)[0]
    else:
        r = binop(s, e.mnemonic, a, rep(s, s.trunc(imm, n) if n < 16 else s.zext(imm, n), n))
    s.z_write(F('Zdn'), r)


@sve('mul_z_zi', 'smax_z_zi', 'smin_z_zi', 'umax_z_zi', 'umin_z_zi', spec=size_spec())
def _zi(s: S, e: Encoding, F):
    n = es(e)
    imm = (s.zext if e.mnemonic.startswith('U') else s.sext)(F('imm8'), n)
    s.z_write(F('Zdn'), binop(s, e.mnemonic, s.z_read(F('Zdn'), n), rep(s, imm, n)))


def _undef_bitmask(s: S, e: Encoding, F):
    return s.not_(s.logic_imm_valid(s.bits(F('imm13'), 12, 1), s.bits(F('imm13'), 0, 6)))


def bitmask_imm(s: S, F):
    imm13 = F('imm13')
    return s.decode_bit_masks(s.bits(imm13, 12, 1), s.bits(imm13, 0, 6), s.bits(imm13, 6, 6), 64)[0]


@sve('and_z_zi', 'orr_z_zi', 'eor_z_zi', undef=_undef_bitmask)
def _zi_logic(s: S, e: Encoding, F):
    a = s.z_read(F('Zdn'), 64)
    s.z_write(F('Zdn'), binop(s, e.mnemonic, a, rep(s, bitmask_imm(s, F), 64)))


def shift_imm(s: S, e: Encoding, F):
    """Shift amount of tszh:tszl:imm3: esize-bit, at most esize."""
    n = es(e)
    v = s.zext(s.concat(F('tszh'), F('tszl'), F('imm3')), max(n, 16))
    if e.mnemonic == 'LSL':
        r = s.sub(v, s.c(n, v.width))                      # UInt(tsize:imm3) - esize
    else:
        r = s.sub(s.c(2 * n, v.width), v)                  # 2 * esize - UInt(tsize:imm3)
    return s.trunc(r, n)


def asrd(s: S, a, shift):
    """Arithmetic shift right rounding toward zero."""
    n = a.width
    w = 2 * n
    x = s.sext(a, w)
    sh = s.zext(shift, w)
    bias = s.sub(s.lsl(s.cl(1, x), sh), s.cl(1, x))
    x = s.select(s.slt(x, s.cl(0, x)), s.add(x, bias), x)
    return s.trunc(s.asr(x, sh), n)


@sve('asr_z_zi', 'lsl_z_zi', 'lsr_z_zi', spec=tsz_spec)
def _shift_zi(s: S, e: Encoding, F):
    n = es(e)
    sh = rep(s, shift_imm(s, e, F), n)
    s.z_write(F('Zd'), binop(s, e.mnemonic, s.z_read(F('Zn'), n), sh))


@sve('asr_z_p_zi', 'asrd_z_p_zi', 'lsl_z_p_zi', 'lsr_z_p_zi', spec=tsz_spec)
def _shift_p_zi(s: S, e: Encoding, F):
    n = es(e)
    sh = rep(s, shift_imm(s, e, F), n)
    a = s.z_read(F('Zdn'), n)
    r = asrd(s, a, sh) if e.mnemonic == 'ASRD' else binop(s, e.mnemonic, a, sh)
    s.z_write(F('Zdn'), _merge(s, s.p_read(F('Pg'), n), r, a))


def wide_shift(s: S, mnemonic: str, a, wide):
    """Shift by a 64-bit element: Min(UInt(element2), esize)."""
    n = a.width
    sh = s.trunc(s.select(s.ugt(wide, s.cl(n, wide)), s.cl(n, wide), wide), n)
    return binop(s, mnemonic, a, sh)


@sve('asr_z_zw', 'lsl_z_zw', 'lsr_z_zw', spec=size_spec((0, 1, 2)))
def _shift_zw(s: S, e: Encoding, F):
    n = es(e)
    s.z_write(F('Zd'), wide_shift(s, e.mnemonic, s.z_read(F('Zn'), n), wide_elements(s, F('Zm'), n)))


@sve('asr_z_p_zw', 'lsl_z_p_zw', 'lsr_z_p_zw', spec=size_spec((0, 1, 2)))
def _shift_p_zw(s: S, e: Encoding, F):
    n = es(e)
    a = s.z_read(F('Zdn'), n)
    r = wide_shift(s, e.mnemonic, a, wide_elements(s, F('Zm'), n))
    s.z_write(F('Zdn'), _merge(s, s.p_read(F('Pg'), n), r, a))


@sve('add_z_p_zz', 'and_z_p_zz', 'asr_z_p_zz', 'asrr_z_p_zz', 'bic_z_p_zz', 'eor_z_p_zz',
     'lsl_z_p_zz', 'lslr_z_p_zz', 'lsr_z_p_zz', 'lsrr_z_p_zz', 'mul_z_p_zz', 'orr_z_p_zz',
     'sabd_z_p_zz', 'smax_z_p_zz', 'smin_z_p_zz', 'smulh_z_p_zz', 'sub_z_p_zz', 'subr_z_p_zz',
     'uabd_z_p_zz', 'umax_z_p_zz', 'umin_z_p_zz', 'umulh_z_p_zz', spec=size_spec())
def _p_zz(s: S, e: Encoding, F):
    n = es(e)
    a = s.z_read(F('Zdn'), n)
    r = binop(s, e.mnemonic, a, s.z_read(F('Zm'), n))
    s.z_write(F('Zdn'), _merge(s, s.p_read(F('Pg'), n), r, a))


@sve('sdiv_z_p_zz', 'sdivr_z_p_zz', 'udiv_z_p_zz', 'udivr_z_p_zz', spec=size_spec((2, 3)))
def _p_div(s: S, e: Encoding, F):
    _p_zz(s, e, F)


@sve('sel_z_p_zz', spec=size_spec())
def _sel_z(s: S, e: Encoding, F):
    n = es(e)
    s.z_write(F('Zd'), s.select(s.p_read(F('Pv'), n), s.z_read(F('Zn'), n), s.z_read(F('Zm'), n)))


def _reverse_units(s: S, x, unit: int):
    """Reverse the order of the unit-bit pieces of x."""
    n = x.width
    k = n // unit
    acc = None
    for i in range(k):
        piece = s.and_(s.lsr(x, s.cl(i * unit, x)) if i else x, s.cl((1 << unit) - 1, x))
        j = k - 1 - i
        piece = s.lsl(piece, s.cl(j * unit, x)) if j else piece
        acc = piece if acc is None else s.orr(acc, piece)
    return acc


UNARY: Dict[str, Callable] = {
    'ABS': lambda s, a: s.select(s.slt(a, s.cl(0, a)), s.neg(a), a),
    'NEG': lambda s, a: s.neg(a), 'NOT': lambda s, a: s.not_(a),
    'CLS': lambda s, a: s.cls(a), 'CLZ': lambda s, a: s.clz(a), 'CNT': lambda s, a: s.popcnt(a),
    'CNOT': lambda s, a: s.zext(s.eqc(a, 0), a.width), 'RBIT': lambda s, a: s.reverse(a),
    'SXTB': lambda s, a: s.sext(s.trunc(a, 8), a.width), 'UXTB': lambda s, a: s.zext(s.trunc(a, 8), a.width),
    'SXTH': lambda s, a: s.sext(s.trunc(a, 16), a.width), 'UXTH': lambda s, a: s.zext(s.trunc(a, 16), a.width),
    'SXTW': lambda s, a: s.sext(s.trunc(a, 32), a.width), 'UXTW': lambda s, a: s.zext(s.trunc(a, 32), a.width),
    'REVB': lambda s, a: _reverse_units(s, a, 8), 'REVH': lambda s, a: _reverse_units(s, a, 16),
    'REVW': lambda s, a: _reverse_units(s, a, 32),
}
# smallest element size of the extensions and reversals
UNARY_MIN = {'SXTB': 16, 'UXTB': 16, 'REVB': 16, 'SXTH': 32, 'UXTH': 32, 'REVH': 32,
             'SXTW': 64, 'UXTW': 64, 'REVW': 64}


def _unary_spec(e: Encoding):
    lo = UNARY_MIN.get(e.mnemonic, 8)
    return size_spec(tuple(sz for sz in range(4) if 8 << sz >= lo))(e)


@sve('abs_z_p_z', 'cls_z_p_z', 'clz_z_p_z', 'cnot_z_p_z', 'cnt_z_p_z', 'neg_z_p_z', 'not_z_p_z',
     'rbit_z_p_z', 'sxtb_z_p_z', 'uxtb_z_p_z', 'revb_z_z', spec=_unary_spec)
def _p_z(s: S, e: Encoding, F):
    n = es(e)
    r = UNARY[e.mnemonic](s, s.z_read(F('Zn'), n))
    s.z_write(F('Zd'), _merge(s, s.p_read(F('Pg'), n), r, s.z_read(F('Zd'), n)))


@sve('movprfx_z_p_z', spec=size_spec())
def _movprfx_p(s: S, e: Encoding, F):
    n = es(e)
    old = s.select(rep(s, F('M'), n), s.z_read(F('Zd'), n), s.c(0, n, zs(n)))
    s.z_write(F('Zd'), _merge(s, s.p_read(F('Pg'), n), s.z_read(F('Zn'), n), old))


@sve('movprfx_z_z')
def _movprfx(s: S, e: Encoding, F):
    s.z_write(F('Zd'), s.z_read(F('Zn'), 64))


@sve('mad_z_p_zzz', 'msb_z_p_zzz', 'mla_z_p_zzz', 'mls_z_p_zzz', spec=size_spec())
def _mla(s: S, e: Encoding, F):
    n = es(e)
    if e.mnemonic in ('MAD', 'MSB'):                       # Zdn = Za +/- Zdn * Zm
        d, acc = 'Zdn', s.z_read(F('Za'), n)
        prod = s.mul(s.z_read(F('Zdn'), n), s.z_read(F('Zm'), n))
    else:                                                  # Zda = Zda +/- Zn * Zm
        d, acc = 'Zda', s.z_read(F('Zda'), n)
        prod = s.mul(s.z_read(F('Zn'), n), s.z_read(F('Zm'), n))
    r = s.sub(acc, prod) if e.mnemonic in ('MSB', 'MLS') else s.add(acc, prod)
    s.z_write(F(d), _merge(s, s.p_read(F('Pg'), n), r, s.z_read(F(d), n)))


# -----------------------------------------------------------------------------
# DUP, CPY, INDEX, ADR
# -----------------------------------------------------------------------------
def shifted_imm8(s: S, e: Encoding, F, n: int):
    """SInt(imm8) << (sh ? 8 : 0) as an esize-bit value."""
    imm = s.sext(F('imm8'), max(n, 16))
    imm = s.select(F('sh'), s.lsl(imm, s.c(8, imm.width)), imm)
    return s.trunc(imm, n)


@sve('dup_z_i', spec=size_spec(), undef=_undef_size_sh)
def _dup_i(s: S, e: Encoding, F):
    n = es(e)
    s.z_write(F('Zd'), rep(s, shifted_imm8(s, e, F, n), n))


@sve('dupm_z_i', undef=_undef_bitmask)
def _dupm(s: S, e: Encoding, F):
    s.z_write(F('Zd'), rep(s, bitmask_imm(s, F), 64))


@sve('dup_z_r', spec=size_spec())
def _dup_r(s: S, e: Encoding, F):
    n = es(e)
    s.z_write(F('Zd'), rep(s, s.xsp_read(F('Rn'), n), n))


@sve('cpy_z_o_i', 'cpy_z_p_i', spec=size_spec(), undef=_undef_size_sh)
def _cpy_i(s: S, e: Encoding, F):
    n = es(e)
    old = s.z_read(F('Zd'), n) if e.fixed('M') else s.c(0, n, zs(n))
    s.z_write(F('Zd'), _merge(s, s.p_read(F('Pg'), n), rep(s, shifted_imm8(s, e, F, n), n), old))


@sve('cpy_z_p_r', spec=size_spec())
def _cpy_r(s: S, e: Encoding, F):
    n = es(e)
    v = rep(s, s.xsp_read(F('Rn'), n), n)
    s.z_write(F('Zd'), _merge(s, s.p_read(F('Pg'), n), v, s.z_read(F('Zd'), n)))


@sve('cpy_z_p_v', spec=size_spec())
def _cpy_v(s: S, e: Encoding, F):
    n = es(e)
    v = rep(s, s.v_read(F('Vn'), n), n)
    s.z_write(F('Zd'), _merge(s, s.p_read(F('Pg'), n), v, s.z_read(F('Zd'), n)))


@sve('index_z_ii', 'index_z_ir', 'index_z_ri', 'index_z_rr', spec=size_spec())
def _index(s: S, e: Encoding, F):
    n = es(e)
    imm = e.file in ('index_z_ii', 'index_z_ir')           # base / increment: imm5 or X
    base = s.sext(F('imm5'), n) if imm else s.x_read(F('Rn'), n)
    if e.file == 'index_z_ii':
        incr = s.sext(F('imm5b'), n)
    elif e.file == 'index_z_ri':
        incr = s.sext(F('imm5'), n)
    else:
        incr = s.x_read(F('Rm'), n)
    idx = s.zext(iota(s, n), n) if n > IW else s.trunc(iota(s, n), n)
    s.z_write(F('Zd'), s.add(rep(s, base, n), s.mul(idx, rep(s, incr, n))))


@sve('adr_z_az', spec=SZ_ELEM)
def _adr(s: S, e: Encoding, F):
    if e.name.startswith('adr_z_az_sd'):                    # packed: offsets of esize bits
        n = 32 << e.fixed('sz')
        off = s.z_read(F('Zm'), n)
    else:                                                  # unpacked 32-bit offsets
        n = 64
        off = ext(s, s.trunc(s.z_read(F('Zm'), 64), 32), 64, '_s32_' in e.name)
    sh = s.zext(F('msz'), n)
    s.z_write(F('Zd'), s.add(s.z_read(F('Zn'), n), s.lsl(off, rep(s, sh, n))))


# -----------------------------------------------------------------------------
# Integer compares
# -----------------------------------------------------------------------------
CMP = {'CMPEQ': ('EQ', False), 'CMPNE': ('NE', False), 'CMPGT': ('GT', False), 'CMPGE': ('GE', False),
       'CMPLT': ('LT', False), 'CMPLE': ('LE', False), 'CMPHI': ('GT', True), 'CMPHS': ('GE', True),
       'CMPLO': ('LT', True), 'CMPLS': ('LE', True)}


def _compare(s: S, e: Encoding, F, a, b):
    n = es(e)
    op, unsigned = CMP[e.mnemonic]
    g = s.p_read(F('Pg'), n)
    res = s.and_(g, ucmp(s, op, a, b, unsigned))
    s.flags_write(pred_test(s, g, res))
    s.p_write(F('Pd'), res)


@sve('cmpeq_p_p_zz', spec=size_spec())
def _cmp_zz(s: S, e: Encoding, F):
    n = es(e)
    _compare(s, e, F, s.z_read(F('Zn'), n), s.z_read(F('Zm'), n))


@sve('cmpeq_p_p_zi', spec=size_spec())
def _cmp_zi(s: S, e: Encoding, F):
    n = es(e)
    imm = s.zext(F('imm7'), n) if 'imm7' in e.fields and CMP[e.mnemonic][1] else s.sext(F('imm5'), n)
    _compare(s, e, F, s.z_read(F('Zn'), n), rep(s, imm, n))


@sve('cmpeq_p_p_zw', spec=size_spec((0, 1, 2)))
def _cmp_zw(s: S, e: Encoding, F):
    n = es(e)
    unsigned = CMP[e.mnemonic][1]
    a = ext(s, s.z_read(F('Zn'), n), 64, not unsigned)
    _compare(s, e, F, a, wide_elements(s, F('Zm'), n))


# -----------------------------------------------------------------------------
# Dot products
# -----------------------------------------------------------------------------
def dot(s: S, acc, a, b, signed: bool):
    """acc + sum of the products of the four esize/4-bit parts of a and b."""
    n = acc.width
    q = n // 4
    for i in range(4):
        x = ext(s, s.bits(a, i * q, q), n, signed)
        y = ext(s, s.bits(b, i * q, q), n, signed)
        acc = s.add(acc, s.mul(x, y))
    return acc


@sve('sdot_z_zzz', 'udot_z_zzz', spec=size_spec((2, 3)))
def _dot(s: S, e: Encoding, F):
    n = es(e)
    r = dot(s, s.z_read(F('Zda'), n), s.z_read(F('Zn'), n), s.z_read(F('Zm'), n), e.mnemonic == 'SDOT')
    s.z_write(F('Zda'), r)


@sve('sdot_z_zzzi', 'udot_z_zzzi')
def _dot_idx(s: S, e: Encoding, F):
    n = 32 if e.name.endswith('_s') else 64
    index = F('i2') if n == 32 else F('i1')
    # element `index` of each 128-bit segment of Zm
    per_seg = 128 // n
    i = iota(s, n)
    seg = s.and_(i, s.c(NONE ^ (per_seg - 1), IW, zs(n)))
    sel = s.add(seg, rep(s, s.zext(index, IW), n))
    b = s.b.gather(s.z_read(F('Zm'), n), sel, s.c(0, n, zs(n)))
    r = dot(s, s.z_read(F('Zda'), n), s.z_read(F('Zn'), n), b, e.mnemonic == 'SDOT')
    s.z_write(F('Zda'), r)

