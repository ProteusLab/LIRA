"""Advanced SIMD integer instructions (vector and scalar forms).

Vectors use LIRA shapes: a 4S operand is read as `4 32 _v = read V n`, lane
operations are lane-wise `op` statements, and permutations use `index` and
`gather` (docs: vector semantics). Encodings with a `size`/`Q` arrangement are
split into one LIRA instruction per arrangement (e.g. `ADD_asimdsame_only_4S`),
because statement shapes are static; reserved arrangements are not generated.

64-bit arrangements read the full register and keep the low lanes
(`extract_first`); their results clear the upper half (`extend_zero`).
Saturating instructions set FPSR.QC.
"""
from typing import Callable, Dict, List, Optional

from python.lira.ir import Shape
from python.lira.ir_ops import Add, Orr

from .insns import sem
from .lib import S
from .xmlspec import Encoding

ARR = {(0, 0): '8B', (0, 1): '16B', (1, 0): '4H', (1, 1): '8H',
       (2, 0): '2S', (2, 1): '4S', (3, 0): '1D', (3, 1): '2D'}
SCALAR = {0: 'B', 1: 'H', 2: 'S', 3: 'D'}
QC_BIT = 27


# -----------------------------------------------------------------------------
# Arrangement specializations
# -----------------------------------------------------------------------------
def _fits(e: Encoding, assignments) -> bool:
    for name, v in assignments.items():
        vm = (1 << e.fields[name].width) - 1
        if isinstance(v, tuple):
            v, vm = v
        fm, fv = e.fixed_bits(name)
        if (v & fm & vm) != (fv & vm):
            return False
    return True


def arr_spec(sizes=(0, 1, 2, 3), one_d=False, scalar_sizes=None):
    """Specialize `size`/`Q` operand fields into arrangements."""
    def spec(e: Encoding):
        ops = {f.name for f in e.operands}
        out = []
        if 'size' in ops and 'Q' in ops:
            for sz in sizes:
                for q in (0, 1):
                    if sz == 3 and q == 0 and not one_d:
                        continue
                    out.append((ARR[(sz, q)], {'size': sz, 'Q': q}))
        elif 'size' in ops:
            for sz in (sizes if scalar_sizes is None else scalar_sizes):
                out.append((SCALAR[sz], {'size': sz}))
        elif 'Q' in ops:
            out = [('D', {'Q': 0}), ('Q', {'Q': 1})]
        return [(n, a) for n, a in out if _fits(e, a)] or None
    return spec


def simd(*files, spec=None, undef=None):
    return sem(*files, spec=spec or arr_spec(), undef=undef)


def is_scalar(e: Encoding) -> bool:
    return 'asisd' in e.name and 'asisdls' not in e.name


def esize_of(e: Encoding, field='size') -> int:
    return 8 << e.fixed(field)


def lanes_of(e: Encoding, esize: int) -> int:
    if is_scalar(e):
        return 1
    return (64 << e.fixed('Q')) // esize


# -----------------------------------------------------------------------------
# Lane helpers
# -----------------------------------------------------------------------------
def sh(n):
    return Shape(n, None)


def iota(s: S, n: int, w: int = 8):
    return s.b.index(w, sh(n))


def rd(s: S, idx, lanes: int, esize: int):
    """V{lanes * esize}(idx) as `lanes` elements."""
    if lanes == 1:
        return s.v_read(idx, esize)
    full = s.b.read(s.ctx.rf_v, idx, sh(128 // esize))
    return full if lanes * esize == 128 else s.b.extract_first(full, sh(lanes))


def wr(s: S, idx, v):
    """V{datasize}(idx) = v; bits above datasize are cleared."""
    if v.lanes == 1:
        return s.v_write(idx, v)
    full = 128 // v.width
    if v.lanes != full:
        v = s.b.extend_zero_lanes(v, sh(full))
    s.b.write(s.ctx.rf_v, idx, v)


def rd_part(s: S, idx, part: int, lanes: int, esize: int):
    """Vpart{64}(idx, part) as `lanes` elements."""
    if part == 0:
        return rd(s, idx, lanes, esize)
    full = s.b.read(s.ctx.rf_v, idx, sh(2 * lanes))
    return s.b.gather(full, s.add(iota(s, lanes), s.c(lanes, 8, sh(lanes))), s.c(0, esize, sh(lanes)))


def wr_part(s: S, idx, part: int, v):
    """Vpart{64}(idx, part) = v: part 0 clears the upper half, part 1 keeps the lower."""
    if part == 0:
        return wr(s, idx, v)
    n = v.lanes
    old = s.b.read(s.ctx.rf_v, idx, sh(2 * n))
    s.b.write(s.ctx.rf_v, idx, s.b.gather(v, s.sub(iota(s, 2 * n), s.c(n, 8, sh(2 * n))), old))


def concat(s: S, lo, hi):
    """Lanes of `lo` followed by the lanes of `hi`."""
    n = lo.lanes
    base = s.b.gather(lo, iota(s, 2 * n), s.c(0, lo.width, sh(2 * n)))
    return s.b.gather(hi, s.sub(iota(s, 2 * n), s.c(n, 8, sh(2 * n))), base)


def pick(s: S, v, index):
    """v[index[i]] (indices are in range)."""
    return s.b.gather(v, index, s.cl(0, index, v.width))


def ones(s: S, cond, w):
    """Ones{w} where cond else Zeros{w}."""
    return s.replicate1(cond, w)


def fold(s: S, op, init, v):
    """Reduce the lanes of v with a binary operation."""
    return s.b.fold(op, [init], [v])[0]


def set_qc(s: S, sat):
    if sat.lanes > 1:
        sat = fold(s, Orr(1), s.c(0, 1), sat)
    fpsr = s.sysreg_read(s.ctx.rf_fpsr)
    s.sysreg_write(s.ctx.rf_fpsr, s.orr(fpsr, s.lsl(s.zext(sat, 32), s.c(QC_BIT, 32))))


def ext(s: S, v, w, signed):
    return (s.sext if signed else s.zext)(v, w)


def sat(s: S, x, esize, unsigned, x_unsigned=False):
    """SatQ of a wide value x to esize bits: (result, saturated). x is signed
    unless `x_unsigned` (then it can use the full wide width)."""
    if unsigned:
        hi, lo = (1 << esize) - 1, 0
    else:
        hi, lo = (1 << (esize - 1)) - 1, -(1 << (esize - 1))
    if x_unsigned:
        over, under = s.ugt(x, s.cl(hi, x)), s.c(0, 1, x.shape)
    else:
        over, under = s.sgt(x, s.cl(hi, x)), s.slt(x, s.cl(lo, x))
    r = s.select(over, s.cl(hi, x), s.select(under, s.cl(lo, x), x))
    return s.trunc(r, esize), s.orr(over, under)


def smax(s, a, b): return s.select(s.sgt(a, b), a, b)
def smin(s, a, b): return s.select(s.slt(a, b), a, b)
def umax(s, a, b): return s.select(s.ugt(a, b), a, b)
def umin(s, a, b): return s.select(s.ult(a, b), a, b)


def _binop(s: S, name: str, fn, n: int):
    """Operation defined by a snippet (used by `fold`)."""
    return s.ctx.func_op(f'{name}_{n}', [n, n], [n], lambda s2, a: [fn(s2, a[0], a[1])])


# -----------------------------------------------------------------------------
# Three registers of the same type
# -----------------------------------------------------------------------------
def _abd(s, a, b, signed):
    gt = s.sgt(a, b) if signed else s.ugt(a, b)
    return s.select(gt, s.sub(a, b), s.sub(b, a))


def _halving(s, a, b, signed, op):
    w = 2 * a.width
    x, y = ext(s, a, w, signed), ext(s, b, w, signed)
    r = {'add': lambda: s.add(x, y), 'radd': lambda: s.add(s.add(x, y), s.cl(1, x)),
         'sub': lambda: s.sub(x, y)}[op]()
    return s.trunc(s.asr(r, s.cl(1, r)), a.width)


def _shl_reg(s, a, b, signed, rounding):
    """SSHL/USHL/SRSHL/URSHL: shift by the signed low byte of b."""
    e = a.width
    w = 2 * e if e < 64 else 128
    x = ext(s, a, w, signed)
    shift = s.sext(s.trunc(b, 8), w)
    lim = s.cl(e + 1, x)
    shift = s.select(s.sgt(shift, lim), lim, s.select(s.slt(shift, s.neg(lim)), s.neg(lim), shift))
    neg = s.slt(shift, s.cl(0, x))
    left = s.lsl(x, s.select(neg, s.cl(0, x), shift))
    rs = s.select(neg, s.neg(shift), s.cl(1, x))
    if rounding:
        x = s.add(x, s.lsl(s.cl(1, x), s.sub(rs, s.cl(1, x))))
    right = (s.asr if signed else s.lsr)(x, rs)
    return s.trunc(s.select(neg, right, left), e)


def _polynomial_mult(s: S, a):
    """PolynomialMult(op1, op2): carry-less product on 2 * esize bits."""
    x, y = a
    w = 2 * x.width
    y = s.zext(y, w)
    acc = None
    for i in range(x.width):
        t = s.and_(ones(s, s.bits(x, i, 1), w), s.lsl(y, s.c(i, w)) if i else y)
        acc = t if acc is None else s.xor(acc, t)
    return [acc]


def pmull(s: S, a, b):
    """PolynomialMult of two esize-bit lanes (a shared operation)."""
    es = a.width
    op = s.ctx.func_op(f'polynomial_mult_{es}', [es, es], [2 * es], _polynomial_mult)
    return s.call(op, [a, b])[0]


def _qdmulh(s: S, a, b, rounding, acc=None, sub=False):
    """SQDMULH/SQRDMULH and, with `acc`, SQRDMLAH/SQRDMLSH:
    SignedSatQ(((acc << esize) +/- 2 * a * b + round) >> esize)."""
    e = a.width
    w = 4 * e if e < 32 else 128
    p = s.lsl(s.mul(s.sext(a, w), s.sext(b, w)), s.c(1, w, a.shape))
    if sub:
        p = s.neg(p)
    if acc is not None:
        p = s.add(s.lsl(s.sext(acc, w), s.c(e, w, a.shape)), p)
    if rounding:
        p = s.add(p, s.c(1 << (e - 1), w, a.shape))
    return sat(s, s.asr(p, s.c(e, w, a.shape)), e, False)


def _qaddsub(s, a, b, signed, sub):
    e = a.width
    w = 2 * e
    x, y = ext(s, a, w, signed), ext(s, b, w, signed)
    return sat(s, s.sub(x, y) if sub else s.add(x, y), e, not signed)


SAME: Dict[str, Callable] = {
    'add_advsimd': lambda s, a, b: s.add(a, b),
    'sub_advsimd': lambda s, a, b: s.sub(a, b),
    'mul_advsimd_vec': lambda s, a, b: s.mul(a, b),
    'cmeq_advsimd_reg': lambda s, a, b: ones(s, s.eq(a, b), a.width),
    'cmge_advsimd_reg': lambda s, a, b: ones(s, s.sge(a, b), a.width),
    'cmgt_advsimd_reg': lambda s, a, b: ones(s, s.sgt(a, b), a.width),
    'cmhi_advsimd': lambda s, a, b: ones(s, s.ugt(a, b), a.width),
    'cmhs_advsimd': lambda s, a, b: ones(s, s.uge(a, b), a.width),
    'cmtst_advsimd': lambda s, a, b: ones(s, s.not_(s.eqc(s.and_(a, b), 0)), a.width),
    'smax_advsimd': smax, 'smin_advsimd': smin, 'umax_advsimd': umax, 'umin_advsimd': umin,
    'sabd_advsimd': lambda s, a, b: _abd(s, a, b, True),
    'uabd_advsimd': lambda s, a, b: _abd(s, a, b, False),
    'shadd_advsimd': lambda s, a, b: _halving(s, a, b, True, 'add'),
    'uhadd_advsimd': lambda s, a, b: _halving(s, a, b, False, 'add'),
    'srhadd_advsimd': lambda s, a, b: _halving(s, a, b, True, 'radd'),
    'urhadd_advsimd': lambda s, a, b: _halving(s, a, b, False, 'radd'),
    'shsub_advsimd': lambda s, a, b: _halving(s, a, b, True, 'sub'),
    'uhsub_advsimd': lambda s, a, b: _halving(s, a, b, False, 'sub'),
    'sshl_advsimd': lambda s, a, b: _shl_reg(s, a, b, True, False),
    'ushl_advsimd': lambda s, a, b: _shl_reg(s, a, b, False, False),
    'srshl_advsimd': lambda s, a, b: _shl_reg(s, a, b, True, True),
    'urshl_advsimd': lambda s, a, b: _shl_reg(s, a, b, False, True),
    'pmul_advsimd': lambda s, a, b: s.trunc(pmull(s, a, b), a.width),
}
SAME_SAT = {
    'sqadd_advsimd': lambda s, a, b: _qaddsub(s, a, b, True, False),
    'uqadd_advsimd': lambda s, a, b: _qaddsub(s, a, b, False, False),
    'sqsub_advsimd': lambda s, a, b: _qaddsub(s, a, b, True, True),
    'uqsub_advsimd': lambda s, a, b: _qaddsub(s, a, b, False, True),
    'sqdmulh_advsimd_vec': lambda s, a, b: _qdmulh(s, a, b, False),
    'sqrdmulh_advsimd_vec': lambda s, a, b: _qdmulh(s, a, b, True),
}
SAME_SIZES = {'mul_advsimd_vec': (0, 1, 2), 'smax_advsimd': (0, 1, 2), 'smin_advsimd': (0, 1, 2),
              'umax_advsimd': (0, 1, 2), 'umin_advsimd': (0, 1, 2), 'sabd_advsimd': (0, 1, 2),
              'uabd_advsimd': (0, 1, 2), 'shadd_advsimd': (0, 1, 2), 'uhadd_advsimd': (0, 1, 2),
              'srhadd_advsimd': (0, 1, 2), 'urhadd_advsimd': (0, 1, 2), 'shsub_advsimd': (0, 1, 2),
              'uhsub_advsimd': (0, 1, 2), 'pmul_advsimd': (0,), 'sqdmulh_advsimd_vec': (1, 2),
              'sqrdmulh_advsimd_vec': (1, 2)}


def _same(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    a, b = rd(s, F('Rn'), n, es), rd(s, F('Rm'), n, es)
    if e.file in SAME_SAT:
        r, saturated = SAME_SAT[e.file](s, a, b)
        wr(s, F('Rd'), r)
        set_qc(s, saturated)
    else:
        wr(s, F('Rd'), SAME[e.file](s, a, b))


for _f in list(SAME) + list(SAME_SAT):
    _sizes = SAME_SIZES.get(_f, (0, 1, 2, 3))
    simd(_f, spec=arr_spec(_sizes, scalar_sizes=_sizes))(_same)


@simd('mla_advsimd_vec', 'mls_advsimd_vec', 'saba_advsimd', 'uaba_advsimd', spec=arr_spec((0, 1, 2)))
def _accumulate(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    a, b, acc = rd(s, F('Rn'), n, es), rd(s, F('Rm'), n, es), rd(s, F('Rd'), n, es)
    if e.file.startswith('ml'):
        p = s.mul(a, b)
        r = s.sub(acc, p) if e.file.startswith('mls') else s.add(acc, p)
    else:
        r = s.add(acc, _abd(s, a, b, e.file == 'saba_advsimd'))
    wr(s, F('Rd'), r)


LOGIC = {'and_advsimd': lambda s, n, m, d: s.and_(n, m),
         'bic_advsimd_reg': lambda s, n, m, d: s.and_(n, s.not_(m)),
         'orr_advsimd_reg': lambda s, n, m, d: s.orr(n, m),
         'orn_advsimd': lambda s, n, m, d: s.orr(n, s.not_(m)),
         'eor_advsimd': lambda s, n, m, d: s.xor(n, m),
         'bsl_advsimd': lambda s, n, m, d: s.xor(m, s.and_(s.xor(m, n), d)),
         'bit_advsimd': lambda s, n, m, d: s.xor(d, s.and_(s.xor(d, n), m)),
         'bif_advsimd': lambda s, n, m, d: s.xor(d, s.and_(s.xor(d, n), s.not_(m)))}


@simd(*LOGIC)
def _logic(s: S, e: Encoding, F):
    n = 8 << e.fixed('Q')
    r = LOGIC[e.file](s, rd(s, F('Rn'), n, 8), rd(s, F('Rm'), n, 8), rd(s, F('Rd'), n, 8))
    wr(s, F('Rd'), r)


PAIRWISE = {'addp_advsimd_vec': lambda s, a, b: s.add(a, b),
            'smaxp_advsimd': smax, 'sminp_advsimd': smin,
            'umaxp_advsimd': umax, 'uminp_advsimd': umin}


@simd('addp_advsimd_vec', spec=arr_spec((0, 1, 2, 3)))
@simd('smaxp_advsimd', 'sminp_advsimd', 'umaxp_advsimd', 'uminp_advsimd', spec=arr_spec((0, 1, 2)))
def _pairwise(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    c = concat(s, rd(s, F('Rn'), n, es), rd(s, F('Rm'), n, es))
    even = s.lsl(iota(s, n), s.c(1, 8, sh(n)))
    odd = s.orr(even, s.c(1, 8, sh(n)))
    wr(s, F('Rd'), PAIRWISE[e.file](s, pick(s, c, even), pick(s, c, odd)))


# -----------------------------------------------------------------------------
# Two-register miscellaneous
# -----------------------------------------------------------------------------
def _qabsneg(s, a, neg):
    e = a.width
    x = s.sext(a, 2 * e)
    r = s.neg(x) if neg else s.select(s.slt(x, s.cl(0, x)), s.neg(x), x)
    return sat(s, r, e, False)


MISC = {
    'abs_advsimd': lambda s, a: s.select(s.slt(a, s.cl(0, a)), s.neg(a), a),
    'neg_advsimd': lambda s, a: s.neg(a),
    'cls_advsimd': lambda s, a: s.cls(a),
    'clz_advsimd': lambda s, a: s.clz(a),
    'cnt_advsimd': lambda s, a: s.popcnt(a),
    'not_advsimd': lambda s, a: s.not_(a),
    'rbit_advsimd': lambda s, a: s.reverse(a),
    'cmeq_advsimd_zero': lambda s, a: ones(s, s.eqc(a, 0), a.width),
    'cmge_advsimd_zero': lambda s, a: ones(s, s.sge(a, s.cl(0, a)), a.width),
    'cmgt_advsimd_zero': lambda s, a: ones(s, s.sgt(a, s.cl(0, a)), a.width),
    'cmle_advsimd': lambda s, a: ones(s, s.sle(a, s.cl(0, a)), a.width),
    'cmlt_advsimd': lambda s, a: ones(s, s.slt(a, s.cl(0, a)), a.width),
}
MISC_SAT = {'sqabs_advsimd': lambda s, a: _qabsneg(s, a, False),
            'sqneg_advsimd': lambda s, a: _qabsneg(s, a, True)}
MISC_SIZES = {'cls_advsimd': (0, 1, 2), 'clz_advsimd': (0, 1, 2), 'cnt_advsimd': (0,),
              'not_advsimd': (0,), 'rbit_advsimd': (1,)}


def _misc(s: S, e: Encoding, F):
    es = 8 if e.file in ('not_advsimd', 'rbit_advsimd') else esize_of(e)
    n = lanes_of(e, es)
    a = rd(s, F('Rn'), n, es)
    if e.file in MISC_SAT:
        r, saturated = MISC_SAT[e.file](s, a)
        wr(s, F('Rd'), r)
        set_qc(s, saturated)
    else:
        wr(s, F('Rd'), MISC[e.file](s, a))


for _f in list(MISC) + list(MISC_SAT):
    _sizes = MISC_SIZES.get(_f, (0, 1, 2, 3))
    simd(_f, spec=arr_spec(_sizes, scalar_sizes=(3,) if _f in MISC else _sizes))(_misc)


@simd('rev16_advsimd', spec=arr_spec((0,)))
@simd('rev32_advsimd', spec=arr_spec((0, 1)))
@simd('rev64_advsimd', spec=arr_spec((0, 1, 2)))
def _rev(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    per = {'rev16_advsimd': 16, 'rev32_advsimd': 32, 'rev64_advsimd': 64}[e.file] // es
    idx = s.xor(iota(s, n), s.c(per - 1, 8, sh(n)))
    wr(s, F('Rd'), pick(s, rd(s, F('Rn'), n, es), idx))


def _narrow_spec(e):
    return [(n, a) for n, a in arr_spec((0, 1, 2), scalar_sizes=(0, 1, 2))(e) or []]


NARROW = {'xtn_advsimd': None, 'sqxtn_advsimd': (True, False), 'uqxtn_advsimd': (False, True),
          'sqxtun_advsimd': (True, True)}


@simd(*NARROW, spec=_narrow_spec)
def _narrow(s: S, e: Encoding, F):
    es = esize_of(e)
    if is_scalar(e):
        a = s.v_read(F('Rn'), 2 * es)
        part, n = 0, 1
    else:
        part, n = e.fixed('Q'), 64 // es
        a = rd(s, F('Rn'), n, 2 * es)
    mode = NARROW[e.file]
    if mode is None:
        r = s.trunc(a, es)
    else:
        src_signed, dst_unsigned = mode
        r, saturated = sat(s, ext(s, a, 4 * es if es < 32 else 128, src_signed), es, dst_unsigned)
        set_qc(s, saturated)
    if n == 1:
        s.v_write(F('Rd'), r)
    else:
        wr_part(s, F('Rd'), part, r)


@simd('saddlp_advsimd', 'uaddlp_advsimd', 'sadalp_advsimd', 'uadalp_advsimd', spec=arr_spec((0, 1, 2)))
def _addlp(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    signed = e.file[0] == 's'
    a = rd(s, F('Rn'), n, es)
    even = s.lsl(iota(s, n // 2), s.c(1, 8, sh(n // 2)))
    odd = s.orr(even, s.c(1, 8, sh(n // 2)))
    r = s.add(ext(s, pick(s, a, even), 2 * es, signed), ext(s, pick(s, a, odd), 2 * es, signed))
    if e.file in ('sadalp_advsimd', 'uadalp_advsimd'):
        r = s.add(r, rd(s, F('Rd'), n // 2, 2 * es))
    wr(s, F('Rd'), r)


@simd('shll_advsimd', spec=arr_spec((0, 1, 2)))
def _shll(s: S, e: Encoding, F):
    es = esize_of(e)
    n = 64 // es
    a = rd_part(s, F('Rn'), e.fixed('Q'), n, es)
    wr(s, F('Rd'), s.lsl(s.zext(a, 2 * es), s.c(es, 2 * es, sh(n))))


# -----------------------------------------------------------------------------
# Across lanes
# -----------------------------------------------------------------------------
REDUCE = {'addv_advsimd': ('add', lambda s, a, b: s.add(a, b), False),
          'smaxv_advsimd': ('smax', smax, False), 'sminv_advsimd': ('smin', smin, False),
          'umaxv_advsimd': ('umax', umax, False), 'uminv_advsimd': ('umin', umin, False),
          'saddlv_advsimd': ('add', lambda s, a, b: s.add(a, b), True),
          'uaddlv_advsimd': ('add', lambda s, a, b: s.add(a, b), True)}


def _reduce_spec(e):
    # size::Q == '100' (4S with 64-bit datasize) and size == '11' are reserved
    return [(n, a) for n, a in arr_spec((0, 1, 2))(e) if (a['size'], a['Q']) != (2, 0)]


@simd(*REDUCE, spec=_reduce_spec)
def _reduce(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    name, fn, widen = REDUCE[e.file]
    v = rd(s, F('Rn'), n, es)
    if widen:
        v = ext(s, v, 2 * es, e.file[0] == 's')
    if name == 'add':                                    # sum from 0
        s.v_write(F('Rd'), fold(s, Add(v.width), s.c(0, v.width), v))
        return
    # min/max: start from lane 0, fold the others
    op = _binop(s, f'reduce_{name}', fn, v.width)
    s.v_write(F('Rd'), fold(s, op, pick(s, v, s.c(0, 8)), s.b.gather(
        v, s.add(iota(s, n - 1), s.c(1, 8, sh(n - 1))), s.c(0, v.width, sh(n - 1)))))


@sem('addp_advsimd_pair')
def _addp_scalar(s: S, e: Encoding, F):
    v = rd(s, F('Rn'), 2, 64)
    s.v_write(F('Rd'), s.add(pick(s, v, s.c(0, 8)), pick(s, v, s.c(1, 8))))


# -----------------------------------------------------------------------------
# Permutations and table lookup
# -----------------------------------------------------------------------------
@simd('zip1_advsimd', 'zip2_advsimd', 'uzp1_advsimd', 'uzp2_advsimd', 'trn1_advsimd',
      'trn2_advsimd')
def _perm(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    part = e.fixed('op')
    c = concat(s, rd(s, F('Rn'), n, es), rd(s, F('Rm'), n, es))
    i = iota(s, n)
    k = lambda v: s.c(v, 8, sh(n))
    odd = s.and_(i, k(1))
    if e.file.startswith('zip'):                   # (i & 1) * n + part * n/2 + i/2
        idx = s.add(s.add(s.mul(odd, k(n)), k(part * n // 2)), s.lsr(i, k(1)))
    elif e.file.startswith('uzp'):                 # 2i + part
        idx = s.add(s.lsl(i, k(1)), k(part))
    else:                                          # (i & 1) * n + (i & ~1) + part
        idx = s.add(s.add(s.mul(odd, k(n)), s.and_(i, k(0xFE))), k(part))
    wr(s, F('Rd'), pick(s, c, idx))


@simd('ext_advsimd', spec=lambda e: [('D', {'Q': 0}), ('Q', {'Q': 1})],
      undef=lambda s, e, F: s.bits(F('imm4'), 3, 1) if e.fixed('Q') == 0 else None)
def _ext(s: S, e: Encoding, F):
    n = 8 << e.fixed('Q')
    c = concat(s, rd(s, F('Rn'), n, 8), rd(s, F('Rm'), n, 8))
    wr(s, F('Rd'), pick(s, c, s.add(iota(s, n), s.b.replicate(s.zext(F('imm4'), 8), sh(n)))))


@simd('tbl_advsimd', 'tbx_advsimd', spec=lambda e: [('8B', {'Q': 0}), ('16B', {'Q': 1})])
def _tbl(s: S, e: Encoding, F):
    n = 8 << e.fixed('Q')
    regs = e.fixed('len') + 1
    # table = V[n+regs-1]:...:V[n+1]:V[n] as 16 * regs byte lanes; lanes of
    # register r are gathered at iota - 16r (other lanes are out of range)
    table = s.b.read(s.ctx.rf_v, F('Rn'), sh(16))
    if regs > 1:
        lanes = sh(16 * regs)
        i = iota(s, 16 * regs)
        table = s.b.gather(table, i, s.c(0, 8, lanes))
        for r in range(1, regs):
            v = s.b.read(s.ctx.rf_v, _vreg(s, F, 'Rn', r), sh(16))
            table = s.b.gather(v, s.sub(i, s.c(16 * r, 8, lanes)), table)
    default = rd(s, F('Rd'), n, 8) if e.file == 'tbx_advsimd' else s.c(0, 8, sh(n))
    wr(s, F('Rd'), s.b.gather(table, rd(s, F('Rm'), n, 8), default))


# -----------------------------------------------------------------------------
# Copy: DUP, INS, UMOV, SMOV
# -----------------------------------------------------------------------------
def _imm5_spec(sizes=(0, 1, 2, 3), qs=(0, 1)):
    """Element size from the lowest set bit of imm5."""
    def spec(e):
        out = []
        for sz in sizes:
            pattern = ((1 << sz), (1 << (sz + 1)) - 1)
            for q in (qs if 'Q' in {f.name for f in e.operands} else (None,)):
                a = {'imm5': pattern}
                if q is not None:
                    if sz == 3 and q == 0:
                        continue
                    a['Q'] = q
                name = ARR[(sz, q)] if q is not None else SCALAR[sz]
                if _fits(e, a):
                    out.append((name, a))
        return out
    return spec


def _imm5_size(e: Encoding) -> int:
    m, v = e.fixed_bits('imm5')
    return (v & -v).bit_length() - 1


def _element(s: S, v, index):
    """v[index] for a dynamic index (shape 1)."""
    return s.b.gather(v, index, s.c(0, v.width))


@simd('dup_advsimd_elt', spec=_imm5_spec())
def _dup_elt(s: S, e: Encoding, F):
    sz = _imm5_size(e)
    es = 8 << sz
    src = s.b.read(s.ctx.rf_v, F('Rn'), sh(128 // es))
    elem = _element(s, src, s.zext(s.bits(F('imm5'), sz + 1, 4 - sz), 8))
    n = 1 if is_scalar(e) else lanes_of(e, es)
    wr(s, F('Rd'), elem if n == 1 else s.b.replicate(elem, sh(n)))


@simd('dup_advsimd_gen', spec=_imm5_spec())
def _dup_gen(s: S, e: Encoding, F):
    es = 8 << _imm5_size(e)
    n = lanes_of(e, es)
    wr(s, F('Rd'), s.b.replicate(s.x_read(F('Rn'), es), sh(n)))


def _insert(s: S, idx, lane, value, es):
    """V[idx][lane] = value."""
    n = 128 // es
    old = s.b.read(s.ctx.rf_v, idx, sh(n))
    hit = s.eq(iota(s, n), s.b.replicate(s.zext(lane, 8), sh(n)))
    s.b.write(s.ctx.rf_v, idx, s.select(hit, s.b.replicate(value, sh(n)), old))


@simd('ins_advsimd_gen', spec=_imm5_spec())
def _ins_gen(s: S, e: Encoding, F):
    sz = _imm5_size(e)
    _insert(s, F('Rd'), s.zext(s.bits(F('imm5'), sz + 1, 4 - sz), 8), s.x_read(F('Rn'), 8 << sz), 8 << sz)


@simd('ins_advsimd_elt', spec=_imm5_spec())
def _ins_elt(s: S, e: Encoding, F):
    sz = _imm5_size(e)
    es = 8 << sz
    src = s.b.read(s.ctx.rf_v, F('Rn'), sh(128 // es))
    elem = _element(s, src, s.zext(s.bits(F('imm4'), sz, 4 - sz), 8))
    _insert(s, F('Rd'), s.zext(s.bits(F('imm5'), sz + 1, 4 - sz), 8), elem, es)


def _mov_spec(signed):
    def spec(e):
        q = e.fixed('Q')
        out = []
        for sz in range(4):
            es = 8 << sz
            if signed and not es < (32 << q):
                continue
            if not signed and not ((q == 1 and es == 64) or (q == 0 and es < 64)):
                continue
            a = {'imm5': ((1 << sz), (1 << (sz + 1)) - 1)}
            if _fits(e, a):
                out.append((SCALAR[sz], a))
        return out
    return spec


@sem('umov_advsimd', spec=_mov_spec(False))
@sem('smov_advsimd', spec=_mov_spec(True))
def _mov_to_gen(s: S, e: Encoding, F):
    sz = _imm5_size(e)
    es = 8 << sz
    src = s.b.read(s.ctx.rf_v, F('Rn'), sh(128 // es))
    elem = _element(s, src, s.zext(s.bits(F('imm5'), sz + 1, 4 - sz), 8))
    datasize = 32 << e.fixed('Q')
    s.x_write(F('Rd'), ext(s, elem, datasize, e.file == 'smov_advsimd'))


# -----------------------------------------------------------------------------
# Modified immediate: MOVI, MVNI, ORR, BIC
# -----------------------------------------------------------------------------
def _imm8(s: S, F):
    return s.concat(*[F(c) for c in 'abcdefgh'])


def _replicate(s: S, v, w: int = 64):
    """Replicate{w}(v): copies of v multiplied into place."""
    pattern = sum(1 << i for i in range(0, w, v.width))
    return s.mul(s.zext(v, w), s.c(pattern, w))


def _expand_imm(s: S, a):
    """AdvSIMDExpandImm(op, cmode, imm8) -> 64 bits."""
    op, cmode, imm8 = a
    z = lambda w: s.c(0, w)
    o = lambda w: s.c((1 << w) - 1, w)
    bit = lambda i: s.bits(imm8, i, 1)
    cmode0 = s.bits(cmode, 0, 1)
    by_cmode_3_1 = [
        _replicate(s, s.concat(z(24), imm8)),            # 000
        _replicate(s, s.concat(z(16), imm8, z(8))),      # 001
        _replicate(s, s.concat(z(8), imm8, z(16))),      # 010
        _replicate(s, s.concat(imm8, z(24))),            # 011
        _replicate(s, s.concat(z(8), imm8)),             # 100
        _replicate(s, s.concat(imm8, z(8))),             # 101
        s.select(cmode0,                                 # 110
                 _replicate(s, s.concat(z(8), imm8, o(16))),
                 _replicate(s, s.concat(z(16), imm8, o(8)))),
    ]
    # 111: bytes (op 0) or byte masks (op 1); cmode<0> = 1 is FMOV (vector, immediate)
    masks = s.concat(*[s.replicate1(bit(i), 8) for i in range(7, -1, -1)])
    b6 = bit(6)
    fp32 = s.concat(bit(7), s.not_(b6), s.replicate1(b6, 5), s.bits(imm8, 0, 6), z(19))
    fp64 = s.concat(bit(7), s.not_(b6), s.replicate1(b6, 8), s.bits(imm8, 0, 6), z(48))
    r = s.select(cmode0, s.select(op, fp64, _replicate(s, fp32)),
                 s.select(op, masks, _replicate(s, imm8)))
    sel = s.bits(cmode, 1, 3)
    for k in range(6, -1, -1):
        r = s.select(s.eqc(sel, k), by_cmode_3_1[k], r)
    return [r]


@simd('movi_advsimd', 'mvni_advsimd', 'orr_advsimd_imm', 'bic_advsimd_imm')
def _modimm(s: S, e: Encoding, F):
    expand = s.ctx.func_op('adv_simd_expand_imm', [1, 4, 8], [64], _expand_imm)
    imm = s.call(expand, [F('op'), F('cmode'), _imm8(s, F)])[0]
    if e.file in ('mvni_advsimd', 'bic_advsimd_imm'):
        imm = s.not_(imm)
    datasize = 64 << e.fixed('Q')
    val = imm if datasize == 64 else s.concat(imm, imm)
    if e.file in ('orr_advsimd_imm', 'bic_advsimd_imm'):
        old = s.v_read(F('Rd'), datasize)
        val = s.orr(old, val) if e.file == 'orr_advsimd_imm' else s.and_(old, val)
    s.v_write(F('Rd'), val)


# -----------------------------------------------------------------------------
# Shifts by immediate
# -----------------------------------------------------------------------------
IMMH = {0: (0b0001, 0b1111), 1: (0b0010, 0b1110), 2: (0b0100, 0b1100), 3: (0b1000, 0b1000)}


def _immh_spec(sizes=(0, 1, 2, 3), narrow=False):
    def spec(e):
        out = []
        ops = {f.name for f in e.operands}
        for sz in sizes:
            for q in ((0, 1) if 'Q' in ops else (None,)):
                a = {'immh': IMMH[sz]}
                if q is not None:
                    if sz == 3 and q == 0 and not narrow:
                        continue
                    a['Q'] = q
                if _fits(e, a):
                    out.append(((ARR[(sz, q)] if q is not None else SCALAR[sz]), a))
        return out
    return spec


def _shift_esize(e: Encoding) -> int:
    m, v = e.fixed_bits('immh')
    return 8 << (v.bit_length() - 1)


def _immhb(s: S, F):
    return s.concat(F('immh'), F('immb'))


RIGHT = {'sshr_advsimd': (True, False, False), 'ushr_advsimd': (False, False, False),
         'srshr_advsimd': (True, True, False), 'urshr_advsimd': (False, True, False),
         'ssra_advsimd': (True, False, True), 'usra_advsimd': (False, False, True),
         'srsra_advsimd': (True, True, True), 'ursra_advsimd': (False, True, True)}


def _rshr(s: S, a, shift, signed, rounding, w):
    """RShr(Int(a), shift, rounding) computed on w bits; shift >= 1."""
    x = ext(s, a, w, signed)
    sh_ = s.zext(shift, w)
    if rounding:
        x = s.add(x, s.lsl(s.cl(1, x), s.sub(sh_, s.cl(1, x))))
    return (s.asr if signed else s.lsr)(x, sh_)


@simd(*RIGHT, spec=_immh_spec())
def _shr_imm(s: S, e: Encoding, F):
    es = _shift_esize(e)
    n = lanes_of(e, es)
    signed, rounding, acc = RIGHT[e.file]
    a = rd(s, F('Rn'), n, es)
    shift = s.sub(s.c(2 * es, 8), s.zext(_immhb(s, F), 8))
    if n > 1:
        shift = s.b.replicate(shift, sh(n))
    r = s.trunc(_rshr(s, a, shift, signed, rounding, 2 * es if es < 64 else 128), es)
    if acc:
        r = s.add(rd(s, F('Rd'), n, es), r)
    wr(s, F('Rd'), r)


@simd('shl_advsimd', 'sli_advsimd', 'sri_advsimd', spec=_immh_spec())
def _shl_imm(s: S, e: Encoding, F):
    es = _shift_esize(e)
    n = lanes_of(e, es)
    a = rd(s, F('Rn'), n, es)
    w = 2 * es if es < 64 else 128
    ones_ = s.cl((1 << es) - 1, a, w)
    if e.file == 'sri_advsimd':
        shift = s.sub(s.c(2 * es, 8), s.zext(_immhb(s, F), 8))
    else:
        shift = s.sub(s.zext(_immhb(s, F), 8), s.c(es, 8))
    shift = s.zext(shift, w)
    if n > 1:
        shift = s.b.replicate(shift, sh(n))
    x = s.zext(a, w)
    if e.file == 'sri_advsimd':
        shifted, mask = s.lsr(x, shift), s.lsr(ones_, shift)
    else:
        shifted, mask = s.lsl(x, shift), s.lsl(ones_, shift)
    shifted, mask = s.trunc(shifted, es), s.trunc(mask, es)
    if e.file == 'shl_advsimd':
        r = shifted
    else:
        d = rd(s, F('Rd'), n, es)
        r = s.orr(s.and_(d, s.not_(mask)), shifted)
    wr(s, F('Rd'), r)


@simd('shrn_advsimd', 'rshrn_advsimd', spec=_immh_spec((0, 1, 2), narrow=True))
def _shrn(s: S, e: Encoding, F):
    es = _shift_esize(e)
    n = 64 // es
    a = rd(s, F('Rn'), n, 2 * es)
    shift = s.b.replicate(s.sub(s.c(2 * es, 8), s.zext(_immhb(s, F), 8)), sh(n))
    r = _rshr(s, a, shift, False, e.file == 'rshrn_advsimd', 4 * es if es < 32 else 128)
    wr_part(s, F('Rd'), e.fixed('Q'), s.trunc(r, es))


@simd('sshll_advsimd', 'ushll_advsimd', spec=_immh_spec((0, 1, 2), narrow=True))
def _shll_imm(s: S, e: Encoding, F):
    es = _shift_esize(e)
    n = 64 // es
    a = rd_part(s, F('Rn'), e.fixed('Q'), n, es)
    shift = s.b.replicate(s.zext(s.sub(s.zext(_immhb(s, F), 8), s.c(es, 8)), 2 * es), sh(n))
    wr(s, F('Rd'), s.lsl(ext(s, a, 2 * es, e.file == 'sshll_advsimd'), shift))


# -----------------------------------------------------------------------------
# Three registers of different types (long, wide, narrow)
# -----------------------------------------------------------------------------
LONG = {'saddl_advsimd': ('add', True), 'uaddl_advsimd': ('add', False),
        'ssubl_advsimd': ('sub', True), 'usubl_advsimd': ('sub', False),
        'smull_advsimd_vec': ('mul', True), 'umull_advsimd_vec': ('mul', False),
        'smlal_advsimd_vec': ('mla', True), 'umlal_advsimd_vec': ('mla', False),
        'smlsl_advsimd_vec': ('mls', True), 'umlsl_advsimd_vec': ('mls', False),
        'sabdl_advsimd': ('abd', True), 'uabdl_advsimd': ('abd', False),
        'sabal_advsimd': ('aba', True), 'uabal_advsimd': ('aba', False)}


def _long_op(s, kind, x, y, signed, acc_fn):
    if kind == 'add': return s.add(x, y)
    if kind == 'sub': return s.sub(x, y)
    if kind == 'mul': return s.mul(x, y)
    if kind == 'mla': return s.add(acc_fn(), s.mul(x, y))
    if kind == 'mls': return s.sub(acc_fn(), s.mul(x, y))
    d = _abd(s, x, y, signed)
    return d if kind == 'abd' else s.add(acc_fn(), d)


@simd(*LONG, spec=arr_spec((0, 1, 2)))
def _long(s: S, e: Encoding, F):
    es = esize_of(e)
    n, part = 64 // es, e.fixed('Q')
    kind, signed = LONG[e.file]
    x = ext(s, rd_part(s, F('Rn'), part, n, es), 2 * es, signed)
    y = ext(s, rd_part(s, F('Rm'), part, n, es), 2 * es, signed)
    wr(s, F('Rd'), _long_op(s, kind, x, y, signed, lambda: rd(s, F('Rd'), n, 2 * es)))


@simd('saddw_advsimd', 'uaddw_advsimd', 'ssubw_advsimd', 'usubw_advsimd', spec=arr_spec((0, 1, 2)))
def _wide(s: S, e: Encoding, F):
    es = esize_of(e)
    n, part = 64 // es, e.fixed('Q')
    signed = e.file[0] == 's'
    x = rd(s, F('Rn'), n, 2 * es)
    y = ext(s, rd_part(s, F('Rm'), part, n, es), 2 * es, signed)
    wr(s, F('Rd'), s.sub(x, y) if 'sub' in e.file else s.add(x, y))


@simd('addhn_advsimd', 'raddhn_advsimd', 'subhn_advsimd', 'rsubhn_advsimd', spec=arr_spec((0, 1, 2)))
def _hn(s: S, e: Encoding, F):
    es = esize_of(e)
    n = 64 // es
    x, y = rd(s, F('Rn'), n, 2 * es), rd(s, F('Rm'), n, 2 * es)
    r = s.sub(x, y) if 'sub' in e.file else s.add(x, y)
    if e.file[0] == 'r':
        r = s.add(r, s.cl(1 << (es - 1), r))
    wr_part(s, F('Rd'), e.fixed('Q'), s.bits(r, es, es))


@simd('pmull_advsimd', spec=lambda e: [(n, a) for n, a in arr_spec((0, 3), one_d=True)(e)])
def _pmull(s: S, e: Encoding, F):
    es = esize_of(e)
    n, part = 64 // es, e.fixed('Q')
    wr(s, F('Rd'), pmull(s, rd_part(s, F('Rn'), part, n, es), rd_part(s, F('Rm'), part, n, es)))


# -----------------------------------------------------------------------------
# By element
# -----------------------------------------------------------------------------
def _elem_index(s: S, e: Encoding, F, es):
    """(index, Rm) of a by-element operand."""
    if es == 16:
        return s.concat(F('H'), F('L'), F('M')), s.zext(F('Rm'), 5)
    return s.concat(F('H'), F('L')), s.concat(F('M'), F('Rm'))


def _elem_operand(s: S, e: Encoding, F, es, n):
    idx, rm = _elem_index(s, e, F, es)
    src = s.b.read(s.ctx.rf_v, rm, sh(128 // es))
    elem = _element(s, src, s.zext(idx, 8))
    return elem if n == 1 else s.b.replicate(elem, sh(n))


ELEM = {'mul_advsimd_elt': 'mul', 'mla_advsimd_elt': 'mla', 'mls_advsimd_elt': 'mls'}


@simd(*ELEM, spec=arr_spec((1, 2)))
def _mul_elt(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    a, b = rd(s, F('Rn'), n, es), _elem_operand(s, e, F, es, n)
    p = s.mul(a, b)
    kind = ELEM[e.file]
    if kind != 'mul':
        acc = rd(s, F('Rd'), n, es)
        p = s.add(acc, p) if kind == 'mla' else s.sub(acc, p)
    wr(s, F('Rd'), p)


LONG_ELEM = {'smull_advsimd_elt': ('mul', True), 'umull_advsimd_elt': ('mul', False),
             'smlal_advsimd_elt': ('mla', True), 'umlal_advsimd_elt': ('mla', False),
             'smlsl_advsimd_elt': ('mls', True), 'umlsl_advsimd_elt': ('mls', False)}


@simd(*LONG_ELEM, spec=arr_spec((1, 2)))
def _long_elt(s: S, e: Encoding, F):
    es = esize_of(e)
    n, part = 64 // es, e.fixed('Q')
    kind, signed = LONG_ELEM[e.file]
    x = ext(s, rd_part(s, F('Rn'), part, n, es), 2 * es, signed)
    y = ext(s, _elem_operand(s, e, F, es, n), 2 * es, signed)
    wr(s, F('Rd'), _long_op(s, kind, x, y, signed, lambda: rd(s, F('Rd'), n, 2 * es)))


# -----------------------------------------------------------------------------
# Loads and stores of multiple structures, load and replicate
# -----------------------------------------------------------------------------
# opcode -> (registers, structure elements)
LDST_MULT = {0b0000: (1, 4), 0b0010: (4, 1), 0b0100: (1, 3), 0b0110: (3, 1),
             0b0111: (1, 1), 0b1000: (1, 2), 0b1010: (2, 1)}


def _ldst_mult_spec(e):
    specs = arr_spec(one_d=True)(e) or []
    rpt, selem = LDST_MULT[e.fixed('opcode')]
    return [(n, a) for n, a in specs if not (a['size'] == 3 and a['Q'] == 0 and selem != 1)]


def _base_and_writeback(s: S, e: Encoding, F, total_bytes):
    base = s.xsp_read(F('Rn'), 64)
    if 'asisdlsep' in e.name or 'asisdlsop' in e.name:     # post-index
        if e.fixed('Rm') == 31:
            new = s.add(base, s.c(total_bytes, 64))
        else:
            new = s.add(base, s.x_read(F('Rm'), 64))
        return base, lambda: s.xsp_write(F('Rn'), new)
    return base, lambda: None


def _vreg(s: S, F, field, k):
    return F(field) if k == 0 else s.and_(s.add(F(field), s.c(k, 5)), s.c(31, 5))


@simd('ld1_advsimd_mult', 'st1_advsimd_mult', 'ld2_advsimd_mult', 'st2_advsimd_mult',
      'ld3_advsimd_mult', 'st3_advsimd_mult', 'ld4_advsimd_mult', 'st4_advsimd_mult',
      spec=_ldst_mult_spec)
def _ldst_mult(s: S, e: Encoding, F):
    es = esize_of(e)
    n = (64 << e.fixed('Q')) // es
    rpt, selem = LDST_MULT[e.fixed('opcode')]
    ebytes = es // 8
    base, writeback = _base_and_writeback(s, e, F, rpt * selem * n * ebytes)
    load = e.fixed('L')
    for r in range(rpt):
        for k in range(selem):
            # element i of register t + r + k is at ((r * n + i) * selem + k) * ebytes
            off = s.mul(s.zext(iota(s, n), 64), s.c(selem * ebytes, 64, sh(n)))
            off = s.add(off, s.c((r * n * selem + k) * ebytes, 64, sh(n)))
            addr = s.add(s.b.replicate(base, sh(n)), off) if n > 1 else s.add(base, off)
            t = _vreg(s, F, 'Rt', r + k)
            if load:
                wr(s, t, s.mem_read(addr, es))
            else:
                s.mem_write(addr, rd(s, t, n, es))
    writeback()


@simd('ld1r_advsimd', spec=arr_spec(one_d=True))
def _ld1r(s: S, e: Encoding, F):
    es = esize_of(e)
    n = (64 << e.fixed('Q')) // es
    base, writeback = _base_and_writeback(s, e, F, es // 8)
    elem = s.mem_read(base, es)
    wr(s, F('Rt'), elem if n == 1 else s.b.replicate(elem, sh(n)))
    writeback()
