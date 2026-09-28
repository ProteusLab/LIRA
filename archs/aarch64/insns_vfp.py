"""Advanced SIMD floating point (vector and scalar forms), FEAT_FHM, FEAT_FCMA,
FEAT_BF16, FEAT_FRINTTS and FEAT_JSCVT.

Lane-wise FP operations are `fop` statements with a vector shape. With
FPCR.NEP = 0 (FEAT_AFP not modeled here) scalar results clear the upper bits.
"""
from python.lira import float_ops as F

from .insns import sem
from .insns_fp import cmp_to_nzcv, fsize, vfp_expand_imm
from .insns_simd import (_fits, _immhb, concat, iota, pick, rd, rd_part, sh, wr, wr_part)
from .lib import S
from .xmlspec import Encoding


# -----------------------------------------------------------------------------
# Arrangements: `fp16` encodings are half precision, others use sz (S/D)
# -----------------------------------------------------------------------------
def _ops(e):
    return {f.name for f in e.operands}


def fp_spec(e: Encoding):
    ops = _ops(e)
    if 'Q' in ops and 'sz' in ops:
        out = [('2S', {'Q': 0, 'sz': 0}), ('4S', {'Q': 1, 'sz': 0}), ('2D', {'Q': 1, 'sz': 1})]
    elif 'sz' in ops:
        out = [('S', {'sz': 0}), ('D', {'sz': 1})]
    elif 'Q' in ops:
        out = [('D', {'Q': 0}), ('Q', {'Q': 1})]
    else:
        return None
    return [(n, a) for n, a in out if _fits(e, a)] or None


def fp_esize(e: Encoding) -> int:
    if 'fp16' in e.name or e.name.endswith(('_H', 'RH_H')) or '_H_' in e.name:
        return 16
    if 'sz' in e.fields and e.fixed('sz') is not None:
        return 32 << e.fixed('sz')
    return 32


def fp_lanes(e: Encoding, es: int) -> int:
    if 'asisd' in e.name:
        return 1
    return (64 << e.fixed('Q')) // es


def fsem(*files, spec=fp_spec, undef=None):
    return sem(*files, spec=spec, undef=undef)


def rmode(s: S, mode, like):
    return s.c(mode, 3, like.shape)


def fop(s: S, base, n, args, m=None):
    return s.fop(base, n, args, m)


def fneg(s: S, x):
    return s.xor(x, s.cl(1 << (x.width - 1), x))


def fabs(s: S, x):
    return s.and_(x, s.cl((1 << (x.width - 1)) - 1, x))


def ones(s: S, cond, w):
    return s.replicate1(cond, w)


def _dims(e):
    es = fp_esize(e)
    return es, fp_lanes(e, es)


# -----------------------------------------------------------------------------
# Three same / two register
# -----------------------------------------------------------------------------
def _cmp(s: S, a, b, signal, accept):
    rel = fop(s, 'fcmps' if signal else 'fcmpq', a.width, [a, b])
    hit = None
    for code in accept:
        h = s.eqc(rel, code)
        hit = h if hit is None else s.orr(hit, h)
    return ones(s, hit, a.width)


BINARY = {
    'fadd_advsimd': lambda s, a, b: fop(s, 'fadd', a.width, [a, b, rmode(s, F.DYN, a)]),
    'fsub_advsimd': lambda s, a, b: fop(s, 'fsub', a.width, [a, b, rmode(s, F.DYN, a)]),
    'fmul_advsimd_vec': lambda s, a, b: fop(s, 'fmul', a.width, [a, b, rmode(s, F.DYN, a)]),
    'fdiv_advsimd': lambda s, a, b: fop(s, 'fdiv', a.width, [a, b, rmode(s, F.DYN, a)]),
    'fmulx_advsimd_vec': lambda s, a, b: fop(s, 'fmulx', a.width, [a, b, rmode(s, F.DYN, a)]),
    'frecps_advsimd': lambda s, a, b: fop(s, 'frecps', a.width, [a, b, rmode(s, F.DYN, a)]),
    'frsqrts_advsimd': lambda s, a, b: fop(s, 'frsqrts', a.width, [a, b, rmode(s, F.DYN, a)]),
    'fmax_advsimd': lambda s, a, b: fop(s, 'fmax', a.width, [a, b]),
    'fmin_advsimd': lambda s, a, b: fop(s, 'fmin', a.width, [a, b]),
    'fmaxnm_advsimd': lambda s, a, b: fop(s, 'fmaxnm', a.width, [a, b]),
    'fminnm_advsimd': lambda s, a, b: fop(s, 'fminnm', a.width, [a, b]),
    'fabd_advsimd': lambda s, a, b: fabs(s, fop(s, 'fsub', a.width, [a, b, rmode(s, F.DYN, a)])),
    'facge_advsimd': lambda s, a, b: _cmp(s, fabs(s, a), fabs(s, b), True, (F.CMP_EQ, F.CMP_GT)),
    'facgt_advsimd': lambda s, a, b: _cmp(s, fabs(s, a), fabs(s, b), True, (F.CMP_GT,)),
    'fcmeq_advsimd_reg': lambda s, a, b: _cmp(s, a, b, False, (F.CMP_EQ,)),
    'fcmge_advsimd_reg': lambda s, a, b: _cmp(s, a, b, True, (F.CMP_EQ, F.CMP_GT)),
    'fcmgt_advsimd_reg': lambda s, a, b: _cmp(s, a, b, True, (F.CMP_GT,)),
}


@fsem(*BINARY)
def _binary(s: S, e: Encoding, F_):
    es, n = _dims(e)
    wr(s, F_('Rd'), BINARY[e.file](s, rd(s, F_('Rn'), n, es), rd(s, F_('Rm'), n, es)))


FRINT = {'frintn_advsimd': ('frint', F.RNE), 'frintp_advsimd': ('frint', F.RTP),
         'frintm_advsimd': ('frint', F.RTN), 'frintz_advsimd': ('frint', F.RTZ),
         'frinta_advsimd': ('frint', F.RNA), 'frinti_advsimd': ('frint', F.DYN),
         'frintx_advsimd': ('frintx', F.DYN),
         'frint32x_advsimd': ('frint32', F.DYN), 'frint32z_advsimd': ('frint32', F.RTZ),
         'frint64x_advsimd': ('frint64', F.DYN), 'frint64z_advsimd': ('frint64', F.RTZ)}
UNARY = {
    'fabs_advsimd': fabs, 'fneg_advsimd': fneg,
    'fsqrt_advsimd': lambda s, a: fop(s, 'fsqrt', a.width, [a, rmode(s, F.DYN, a)]),
    'frecpe_advsimd': lambda s, a: fop(s, 'frecpe', a.width, [a]),
    'frsqrte_advsimd': lambda s, a: fop(s, 'frsqrte', a.width, [a]),
    'frecpx_advsimd': lambda s, a: fop(s, 'frecpx', a.width, [a]),
    'fcmeq_advsimd_zero': lambda s, a: _cmp(s, a, s.cl(0, a), False, (F.CMP_EQ,)),
    'fcmge_advsimd_zero': lambda s, a: _cmp(s, a, s.cl(0, a), True, (F.CMP_EQ, F.CMP_GT)),
    'fcmgt_advsimd_zero': lambda s, a: _cmp(s, a, s.cl(0, a), True, (F.CMP_GT,)),
    'fcmle_advsimd': lambda s, a: _cmp(s, s.cl(0, a), a, True, (F.CMP_EQ, F.CMP_GT)),
    'fcmlt_advsimd': lambda s, a: _cmp(s, s.cl(0, a), a, True, (F.CMP_GT,)),
}
for _f, (_b, _m) in FRINT.items():
    UNARY[_f] = (lambda b, m: lambda s, a: fop(s, b, a.width, [a, rmode(s, m, a)]))(_b, _m)


@fsem(*UNARY)
def _unary(s: S, e: Encoding, F_):
    es, n = _dims(e)
    wr(s, F_('Rd'), UNARY[e.file](s, rd(s, F_('Rn'), n, es)))


@sem('frint32x_float', 'frint32z_float', 'frint64x_float', 'frint64z_float')
def _frint_n_scalar(s: S, e: Encoding, F_):
    n = 32 << e.fixed('ftype')
    base, mode = FRINT[e.file.replace('_float', '_advsimd')]
    s.v_write(F_('Rd'), fop(s, base, n, [s.v_read(F_('Rn'), n), s.rm(mode)]))


# -----------------------------------------------------------------------------
# Pairwise and across lanes (FPReduce: recursive halves)
# -----------------------------------------------------------------------------
PAIR_OPS = {'faddp': 'fadd', 'fmaxp': 'fmax', 'fminp': 'fmin', 'fmaxnmp': 'fmaxnm',
            'fminnmp': 'fminnm', 'fmaxv': 'fmax', 'fminv': 'fmin', 'fmaxnmv': 'fmaxnm',
            'fminnmv': 'fminnm'}


def _pair_op(s: S, base, a, b):
    args = [a, b, rmode(s, F.DYN, a)] if base == 'fadd' else [a, b]
    return fop(s, base, a.width, args)


@fsem(*[f'{p}_advsimd_vec' for p in ('faddp', 'fmaxp', 'fminp', 'fmaxnmp', 'fminnmp')])
def _pairwise(s: S, e: Encoding, F_):
    es, n = _dims(e)
    c = concat(s, rd(s, F_('Rn'), n, es), rd(s, F_('Rm'), n, es))
    even = s.lsl(iota(s, n), s.c(1, 8, sh(n)))
    odd = s.orr(even, s.c(1, 8, sh(n)))
    wr(s, F_('Rd'), _pair_op(s, PAIR_OPS[e.file.split('_')[0]], pick(s, c, even), pick(s, c, odd)))


@fsem(*[f'{p}_advsimd_pair' for p in ('faddp', 'fmaxp', 'fminp', 'fmaxnmp', 'fminnmp')])
def _pair_scalar(s: S, e: Encoding, F_):
    es = fp_esize(e)
    v = rd(s, F_('Rn'), 2, es) if es != 16 else s.b.extract_first(s.b.read(s.ctx.rf_v, F_('Rn'), sh(8)), sh(2))
    a, b = pick(s, v, s.c(0, 8)), pick(s, v, s.c(1, 8))
    s.v_write(F_('Rd'), _pair_op(s, PAIR_OPS[e.file.split('_')[0]], a, b))


def _across_spec(e):
    ops = _ops(e)
    if 'Q' in ops:
        return [('4H', {'Q': 0}), ('8H', {'Q': 1})]
    return None                                   # 4S only


@fsem('fmaxv_advsimd', 'fminv_advsimd', 'fmaxnmv_advsimd', 'fminnmv_advsimd', spec=_across_spec)
def _across(s: S, e: Encoding, F_):
    es = 16 if 'H' in e.name.split('_')[-1] or e.name.endswith(('4H', '8H')) else 32
    n = (64 << e.fixed('Q')) // es if 'Q' in e.fields and e.fixed('Q') is not None else 128 // es
    v = rd(s, F_('Rn'), n, es)
    base = PAIR_OPS[e.file.split('_')[0]]
    while v.lanes > 1:
        h = v.lanes // 2
        lo = s.b.extract_first(v, sh(h))
        hi = s.b.gather(v, s.add(iota(s, h), s.c(h, 8, sh(h))), s.c(0, es, sh(h)))
        v = _pair_op(s, base, lo, hi)
    s.v_write(F_('Rd'), pick(s, v, s.c(0, 8)) if v.lanes != 1 or v.shape.lanes_base != 1 else v)


# -----------------------------------------------------------------------------
# Conversions
# -----------------------------------------------------------------------------
CVT = {}
for _r, _m in (('n', F.RNE), ('a', F.RNA), ('p', F.RTP), ('m', F.RTN)):
    CVT[f'fcvt{_r}s_advsimd'] = ('ftosi', _m)
    CVT[f'fcvt{_r}u_advsimd'] = ('ftoui', _m)
CVT['fcvtzs_advsimd_int'] = ('ftosi', F.RTZ)
CVT['fcvtzu_advsimd_int'] = ('ftoui', F.RTZ)
CVT['scvtf_advsimd_int'] = ('sitof', F.DYN)
CVT['ucvtf_advsimd_int'] = ('uitof', F.DYN)


@fsem(*CVT)
def _cvt_int(s: S, e: Encoding, F_):
    es, n = _dims(e)
    base, mode = CVT[e.file]
    a = rd(s, F_('Rn'), n, es)
    wr(s, F_('Rd'), fop(s, base, es, [a, s.cl(0, a, 8), rmode(s, mode, a)], es))


FIX_IMMH = {16: (0b0010, 0b1110), 32: (0b0100, 0b1100), 64: (0b1000, 0b1000)}


def _fix_spec(e):
    out = []
    ops = _ops(e)
    for es, pattern in FIX_IMMH.items():
        for q in ((0, 1) if 'Q' in ops else (None,)):
            a = {'immh': pattern}
            if q is not None:
                if es == 64 and q == 0:
                    continue
                a['Q'] = q
            name = {16: 'H', 32: 'S', 64: 'D'}[es] + ('' if q is None else ('_Q' if q else '_D'))
            if _fits(e, a):
                out.append((name, a))
    return out


FIX = {'fcvtzs_advsimd_fix': 'ftosi', 'fcvtzu_advsimd_fix': 'ftoui',
       'scvtf_advsimd_fix': 'sitof', 'ucvtf_advsimd_fix': 'uitof'}


@fsem(*FIX, spec=_fix_spec)
def _cvt_fix(s: S, e: Encoding, F_):
    m, v = e.fixed_bits('immh')
    es = {0b1000: 64, 0b0100: 32, 0b0010: 16}[m & ~(m >> 1) & 0xE if False else (v & -v) << 0] \
        if False else (64 if v & 8 else 32 if v & 4 else 16)
    n = 1 if 'asisd' in e.name else (64 << e.fixed('Q')) // es
    a = rd(s, F_('Rn'), n, es)
    fbits = s.sub(s.c(2 * es, 8), s.zext(_immhb(s, F_), 8))
    if n > 1:
        fbits = s.b.replicate(fbits, sh(n))
    base = FIX[e.file]
    mode = F.RTZ if base.startswith('fto') else F.DYN
    wr(s, F_('Rd'), fop(s, base, es, [a, fbits, rmode(s, mode, a)], es))


@fsem('fcvtl_advsimd', spec=lambda e: [('4S', {'Q': 0, 'sz': 0}), ('4S2', {'Q': 1, 'sz': 0}),
                                        ('2D', {'Q': 0, 'sz': 1}), ('2D2', {'Q': 1, 'sz': 1})])
def _fcvtl(s: S, e: Encoding, F_):
    es = 16 << e.fixed('sz')
    n = 64 // es
    a = rd_part(s, F_('Rn'), e.fixed('Q'), n, es)
    wr(s, F_('Rd'), fop(s, 'fcvtf', es, [a, rmode(s, F.DYN, a)], 2 * es))


@fsem('fcvtn_advsimd', spec=lambda e: [('4H', {'Q': 0, 'sz': 0}), ('8H', {'Q': 1, 'sz': 0}),
                                        ('2S', {'Q': 0, 'sz': 1}), ('4S', {'Q': 1, 'sz': 1})])
@fsem('fcvtxn_advsimd', spec=lambda e: [('2S', {'Q': 0}), ('4S', {'Q': 1})] if 'Q' in _ops(e) else None)
def _fcvtn(s: S, e: Encoding, F_):
    xn = e.file == 'fcvtxn_advsimd'
    es = 32 if xn else 16 << e.fixed('sz')
    mode = F.ODD if xn else F.DYN
    if 'asisd' in e.name:                         # FCVTXN Sd, Dn
        a = s.v_read(F_('Rn'), 64)
        s.v_write(F_('Rd'), fop(s, 'fcvtf', 64, [a, s.rm(mode)], 32))
        return
    n = 64 // es
    a = rd(s, F_('Rn'), n, 2 * es)
    wr_part(s, F_('Rd'), e.fixed('Q'), fop(s, 'fcvtf', 2 * es, [a, rmode(s, mode, a)], es))


@sem('fjcvtzs')
def _fjcvtzs(s: S, e: Encoding, F_):
    value, z = s.b.fop(__import__('python.lira.float_ops', fromlist=['make']).make('fjcvtzs', 64),
                       [s.v_read(F_('Rn'), 64)])
    s.x_write(F_('Rd'), value)
    s.flags_write(s.concat(s.c(0, 1), z, s.c(0, 2)))


# -----------------------------------------------------------------------------
# Fused multiply-add, by element
# -----------------------------------------------------------------------------
def _elem(s: S, e: Encoding, F_, es, n):
    """By-element operand: index/register per element size."""
    if es == 16:
        idx, rm = s.concat(F_('H'), F_('L'), F_('M')), s.zext(F_('Rm'), 5)
    elif es == 32:
        idx, rm = s.concat(F_('H'), F_('L')), s.concat(F_('M'), F_('Rm'))
    else:
        idx, rm = s.zext(F_('H'), 2), s.concat(F_('M'), F_('Rm'))
    src = s.b.read(s.ctx.rf_v, rm, sh(128 // es))
    elem = s.b.gather(src, s.zext(idx, 8), s.c(0, es))
    return elem if n == 1 else s.b.replicate(elem, sh(n))


def _undef_elt(s: S, e: Encoding, F_):
    if 'sz' in _ops(e) or (e.fixed('sz') if 'sz' in e.fields else None) == 1:
        if fp_esize(e) == 64:
            return s.bits(F_('L'), 0, 1)                   # sz:L == '11'
    return None


FMA = {'fmla_advsimd_vec': 1, 'fmls_advsimd_vec': -1, 'fmla_advsimd_elt': 1,
       'fmls_advsimd_elt': -1, 'fmul_advsimd_elt': 0, 'fmulx_advsimd_elt': 2}


@fsem(*FMA, undef=_undef_elt)
def _fma(s: S, e: Encoding, F_):
    es, n = _dims(e)
    a = rd(s, F_('Rn'), n, es)
    b = _elem(s, e, F_, es, n) if 'elt' in e.file else rd(s, F_('Rm'), n, es)
    kind = FMA[e.file]
    if kind == 0:
        r = fop(s, 'fmul', es, [a, b, rmode(s, F.DYN, a)])
    elif kind == 2:
        r = fop(s, 'fmulx', es, [a, b, rmode(s, F.DYN, a)])
    else:
        if kind < 0:
            a = fneg(s, a)
        r = fop(s, 'fmuladd', es, [rd(s, F_('Rd'), n, es), a, b, rmode(s, F.DYN, a)])
    wr(s, F_('Rd'), r)


def _fhm_spec(e):
    return [('2S', {'Q': 0}), ('4S', {'Q': 1})]


@fsem('fmlal_advsimd_vec', 'fmlsl_advsimd_vec', 'fmlal_advsimd_elt', 'fmlsl_advsimd_elt',
      spec=_fhm_spec)
def _fhm(s: S, e: Encoding, F_):
    n = 2 << e.fixed('Q')
    part = 1 if e.name.split('_')[0].endswith('2') else 0
    full_n = s.b.read(s.ctx.rf_v, F_('Rn'), sh(8))
    a = s.b.gather(full_n, s.add(iota(s, n), s.c(part * n, 8, sh(n))), s.c(0, 16, sh(n)))
    if 'elt' in e.file:
        src = s.b.read(s.ctx.rf_v, s.zext(F_('Rm'), 5), sh(8))
        b = s.b.replicate(s.b.gather(src, s.zext(s.concat(F_('H'), F_('L'), F_('M')), 8),
                                     s.c(0, 16)), sh(n))
    else:
        full_m = s.b.read(s.ctx.rf_v, F_('Rm'), sh(8))
        b = s.b.gather(full_m, s.add(iota(s, n), s.c(part * n, 8, sh(n))), s.c(0, 16, sh(n)))
    if e.file.startswith('fmlsl'):
        a = fneg(s, a)
    acc = rd(s, F_('Rd'), n, 32)
    wr(s, F_('Rd'), fop(s, 'fmuladdh', 32, [acc, a, b, rmode(s, F.DYN, acc)]))


# -----------------------------------------------------------------------------
# Complex numbers (FEAT_FCMA)
# -----------------------------------------------------------------------------
def _cplx_spec(e):
    out = []
    for size, es in ((1, 16), (2, 32), (3, 64)):
        for q in (0, 1):
            if es == 64 and q == 0:
                continue
            if 'elt' in e.file and es == 64:
                continue
            a = {'size': size, 'Q': q}
            if _fits(e, a):
                out.append(({16: 'H', 32: 'S', 64: 'D'}[es] + str(q), a))
    return out


def _neg_lanes(s: S, x, which):
    """FPNeg on even (0), odd (1) or all (2) lanes."""
    n = x.lanes
    if which == 2:
        return fneg(s, x)
    parity = s.eqc(s.and_(iota(s, n), s.c(1, 8, sh(n))), which)
    return s.xor(x, s.select(parity, s.cl(1 << (x.width - 1), x), s.cl(0, x)))


@sem('fcadd_advsimd_vec', spec=_cplx_spec)
def _fcadd(s: S, e: Encoding, F_):
    es = 8 << e.fixed('size')
    n = (64 << e.fixed('Q')) // es
    a, b = rd(s, F_('Rn'), n, es), rd(s, F_('Rm'), n, es)
    swapped = pick(s, b, s.xor(iota(s, n), s.c(1, 8, sh(n))))
    # rot 0 (90): even lanes -b[odd]; rot 1 (270): odd lanes -b[even]
    rot = F_('rot')
    neg_even, neg_odd = _neg_lanes(s, swapped, 0), _neg_lanes(s, swapped, 1)
    other = s.select(s.b.replicate(rot, sh(n)), neg_odd, neg_even)
    wr(s, F_('Rd'), fop(s, 'fadd', es, [a, other, rmode(s, F.DYN, a)]))


@sem('fcmla_advsimd_vec', 'fcmla_advsimd_elt', spec=_cplx_spec)
def _fcmla(s: S, e: Encoding, F_):
    es = 8 << e.fixed('size')
    n = (64 << e.fixed('Q')) // es
    a, acc = rd(s, F_('Rn'), n, es), rd(s, F_('Rd'), n, es)
    i = iota(s, n)
    odd_bit = s.and_(i, s.c(1, 8, sh(n)))
    rot = s.b.replicate(s.zext(F_('rot'), 8), sh(n))
    rot_odd = s.and_(rot, s.c(1, 8, sh(n)))                   # rot 01 / 11
    # element2: operand1[even] for rot 00/10, operand1[odd] for 01/11
    a_idx = s.orr(s.and_(i, s.c(0xFE, 8, sh(n))), rot_odd)
    # element1/3: operand2 lane (rot 00/10) or its pair partner (01/11)
    b_lane = s.xor(odd_bit, rot_odd)
    if 'elt' in e.file:
        idx = s.concat(F_('H'), F_('L')) if es == 16 else s.zext(F_('H'), 2)
        b_src = rd(s, s.concat(F_('M'), F_('Rm')), n, es)
        b_idx = s.add(s.lsl(s.b.replicate(s.zext(idx, 8), sh(n)), s.c(1, 8, sh(n))), b_lane)
    else:
        b_src = rd(s, F_('Rm'), n, es)
        b_idx = s.orr(s.and_(i, s.c(0xFE, 8, sh(n))), b_lane)
    b = pick(s, b_src, b_idx)
    # negation: rot 01 -> even lanes, 10 -> all, 11 -> odd lanes
    sign = s.cl(1 << (es - 1), b)
    zero = s.cl(0, b)
    even = s.eqc(odd_bit, 0)
    neg = s.select(s.eqc(rot, 1), s.select(even, sign, zero),
          s.select(s.eqc(rot, 2), sign,
          s.select(s.eqc(rot, 3), s.select(even, zero, sign), zero)))
    b = s.xor(b, neg)
    r = fop(s, 'fmuladd', es, [acc, pick(s, a, a_idx), b, rmode(s, F.DYN, acc)])
    wr(s, F_('Rd'), r)


# -----------------------------------------------------------------------------
# FMOV (vector, immediate)
# -----------------------------------------------------------------------------
@sem('fmov_advsimd', spec=lambda e: [('D', {'Q': 0}), ('Q', {'Q': 1})] if 'Q' in _ops(e) else None)
def _fmov_vec(s: S, e: Encoding, F_):
    es = {'H': 16, 'S': 32, 'D2': 64}[e.name.split('_')[2]]
    imm8 = s.concat(*[F_(c) for c in 'abcdefgh'])
    elem = vfp_expand_imm(s, imm8, es)
    n = 2 if es == 64 else (64 << e.fixed('Q')) // es
    wr(s, F_('Rd'), s.b.replicate(elem, sh(n)))


# -----------------------------------------------------------------------------
# BFloat16 (FEAT_BF16; FEAT_EBF16 not implemented)
# -----------------------------------------------------------------------------
@sem('bfcvt_float')
def _bfcvt(s: S, e: Encoding, F_):
    s.v_write(F_('Rd'), fop(s, 'fcvtbf', 32, [s.v_read(F_('Rn'), 32), s.rm(F.DYN)], 16))


@sem('bfcvtn_advsimd', spec=lambda e: [('4H', {'Q': 0}), ('8H', {'Q': 1})])
def _bfcvtn(s: S, e: Encoding, F_):
    a = rd(s, F_('Rn'), 4, 32)
    wr_part(s, F_('Rd'), e.fixed('Q'), fop(s, 'fcvtbf', 32, [a, rmode(s, F.DYN, a)], 16))


def _halves(s: S, v, n, first):
    """Lanes 2e + first of a vector of 16-bit elements."""
    return pick(s, v, s.add(s.lsl(iota(s, n), s.c(1, 8, sh(n))), s.c(first, 8, sh(n))))


@sem('bfdot_advsimd_vec', 'bfdot_advsimd_elt', spec=lambda e: [('2S', {'Q': 0}), ('4S', {'Q': 1})])
def _bfdot(s: S, e: Encoding, F_):
    n = 2 << e.fixed('Q')
    a = rd(s, F_('Rn'), 2 * n, 16)
    if 'elt' in e.file:
        src = s.b.read(s.ctx.rf_v, s.concat(F_('M'), F_('Rm')), sh(8))
        idx = s.lsl(s.b.replicate(s.zext(s.concat(F_('H'), F_('L')), 8), sh(n)), s.c(1, 8, sh(n)))
        b0, b1 = pick(s, src, idx), pick(s, src, s.add(idx, s.c(1, 8, sh(n))))
    else:
        b = rd(s, F_('Rm'), 2 * n, 16)
        b0, b1 = _halves(s, b, n, 0), _halves(s, b, n, 1)
    acc = rd(s, F_('Rd'), n, 32)
    r = fop(s, 'bfdotadd', 32, [acc, _halves(s, a, n, 0), _halves(s, a, n, 1), b0, b1])
    wr(s, F_('Rd'), r)


@sem('bfmlal_advsimd_vec', 'bfmlal_advsimd_elt',
     spec=lambda e: [('B', {'Q': 0}), ('T', {'Q': 1})])
def _bfmlal(s: S, e: Encoding, F_):
    sel = e.fixed('Q')                              # BFMLALB / BFMLALT
    a = _halves(s, rd(s, F_('Rn'), 8, 16), 4, sel)
    if 'elt' in e.file:
        src = s.b.read(s.ctx.rf_v, s.zext(F_('Rm'), 5), sh(8))
        b = s.b.replicate(s.b.gather(src, s.zext(s.concat(F_('H'), F_('L'), F_('M')), 8),
                                     s.c(0, 16)), sh(4))
    else:
        b = _halves(s, rd(s, F_('Rm'), 8, 16), 4, sel)
    widen = lambda x: s.lsl(s.zext(x, 32), s.c(16, 32, sh(4)))
    acc = rd(s, F_('Rd'), 4, 32)
    wr(s, F_('Rd'), fop(s, 'fmuladd', 32, [acc, widen(a), widen(b), rmode(s, F.DYN, acc)]))


@sem('bfmmla_advsimd')
def _bfmmla(s: S, e: Encoding, F_):
    a, b = rd(s, F_('Rn'), 8, 16), rd(s, F_('Rm'), 8, 16)
    lane = iota(s, 4)
    i4 = s.lsl(s.lsr(lane, s.c(1, 8, sh(4))), s.c(2, 8, sh(4)))      # 4 * i
    j4 = s.lsl(s.and_(lane, s.c(1, 8, sh(4))), s.c(2, 8, sh(4)))     # 4 * j
    acc = rd(s, F_('Rd'), 4, 32)
    for k in range(2):
        el = lambda base, off: s.add(base, s.c(2 * k + off, 8, sh(4)))
        acc = fop(s, 'bfdotadd', 32, [acc, pick(s, a, el(i4, 0)), pick(s, a, el(i4, 1)),
                                       pick(s, b, el(j4, 0)), pick(s, b, el(j4, 1))])
    wr(s, F_('Rd'), acc)
