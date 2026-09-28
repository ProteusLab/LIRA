"""Advanced SIMD integer, second part: saturating shifts and narrows,
saturating doubling multiplies (incl. FEAT_RDM), SUQADD/USQADD, unsigned
estimates, single-structure loads/stores, dot products (FEAT_DotProd,
FEAT_I8MM) and the AES/SHA1/SHA256 crypto instructions."""
from python.lira.ir import Shape

from .insns import sem
from .insns_simd import (_element, _fits, _immh_spec, _immhb, _shift_esize, _vreg, arr_spec,
                         concat, esize_of, ext, iota, is_scalar, lanes_of, pick, rd, rd_part, sat,
                         set_qc, sh, simd, wr, wr_part, SCALAR)
from .lib import S
from .xmlspec import Encoding


def _wide(e):
    return 2 * e if e < 64 else 128


# -----------------------------------------------------------------------------
# Saturating shifts
# -----------------------------------------------------------------------------
def _qshl_reg(s: S, a, b, signed, rounding):
    """SQSHL/UQSHL/SQRSHL/UQRSHL (register): shift by the signed low byte of b,
    saturate. Left shifts beyond esize saturate exactly like a shift by esize."""
    e = a.width
    w = _wide(e)
    x = ext(s, a, w, signed)
    shift = s.sext(s.trunc(b, 8), w)
    hi, lo = s.cl(e, x), s.cl(-(e + 1), x)
    shift = s.select(s.sgt(shift, hi), hi, s.select(s.slt(shift, lo), lo, shift))
    neg = s.slt(shift, s.cl(0, x))
    left = s.lsl(x, s.select(neg, s.cl(0, x), shift))
    rs = s.select(neg, s.neg(shift), s.cl(1, x))
    if rounding:
        x = s.add(x, s.lsl(s.cl(1, x), s.sub(rs, s.cl(1, x))))
    right = (s.asr if signed else s.lsr)(x, rs)
    # unsigned: x << e can use all 2e bits, compare unsigned
    return sat(s, s.select(neg, right, left), e, not signed, x_unsigned=not signed)


QSHL_REG = {'sqshl_advsimd_reg': (True, False), 'uqshl_advsimd_reg': (False, False),
            'sqrshl_advsimd': (True, True), 'uqrshl_advsimd': (False, True)}


@simd(*QSHL_REG, spec=arr_spec())
def _qshl(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    signed, rounding = QSHL_REG[e.file]
    r, saturated = _qshl_reg(s, rd(s, F('Rn'), n, es), rd(s, F('Rm'), n, es), signed, rounding)
    wr(s, F('Rd'), r)
    set_qc(s, saturated)


# file -> (source signed, destination unsigned)
QSHL_IMM = {'sqshl_advsimd_imm': (True, False), 'uqshl_advsimd_imm': (False, True),
            'sqshlu_advsimd': (True, True)}


@simd(*QSHL_IMM, spec=_immh_spec())
def _qshl_imm(s: S, e: Encoding, F):
    es = _shift_esize(e)
    n = lanes_of(e, es)
    src_signed, dst_unsigned = QSHL_IMM[e.file]
    w = _wide(es)
    x = ext(s, rd(s, F('Rn'), n, es), w, src_signed)
    shift = s.zext(s.sub(s.zext(_immhb(s, F), 8), s.c(es, 8)), w)
    if n > 1:
        shift = s.b.replicate(shift, sh(n))
    r, saturated = sat(s, s.lsl(x, shift), es, dst_unsigned)
    wr(s, F('Rd'), r)
    set_qc(s, saturated)


# file -> (source signed, destination unsigned, rounding)
QSHRN = {'sqshrn_advsimd': (True, False, False), 'sqrshrn_advsimd': (True, False, True),
         'uqshrn_advsimd': (False, True, False), 'uqrshrn_advsimd': (False, True, True),
         'sqshrun_advsimd': (True, True, False), 'sqrshrun_advsimd': (True, True, True)}


@simd(*QSHRN, spec=_immh_spec((0, 1, 2), narrow=True))
def _qshrn(s: S, e: Encoding, F):
    es = _shift_esize(e)
    src_signed, dst_unsigned, rounding = QSHRN[e.file]
    scalar = is_scalar(e)
    n = 1 if scalar else 64 // es
    a = s.v_read(F('Rn'), 2 * es) if scalar else rd(s, F('Rn'), n, 2 * es)
    w = 4 * es if es < 32 else 128
    x = ext(s, a, w, src_signed)
    shift = s.zext(s.sub(s.c(2 * es, 8), s.zext(_immhb(s, F), 8)), w)
    if n > 1:
        shift = s.b.replicate(shift, sh(n))
    if rounding:
        x = s.add(x, s.lsl(s.cl(1, x), s.sub(shift, s.cl(1, x))))
    r, saturated = sat(s, (s.asr if src_signed else s.lsr)(x, shift), es, dst_unsigned)
    if scalar:
        s.v_write(F('Rd'), r)
    else:
        wr_part(s, F('Rd'), e.fixed('Q'), r)
    set_qc(s, saturated)


# -----------------------------------------------------------------------------
# Saturating doubling multiplies
# -----------------------------------------------------------------------------
def _elem_operand(s: S, e: Encoding, F, es, n):
    if es == 16:
        idx, rm = s.concat(F('H'), F('L'), F('M')), s.zext(F('Rm'), 5)
    else:
        idx, rm = s.concat(F('H'), F('L')), s.concat(F('M'), F('Rm'))
    elem = _element(s, s.b.read(s.ctx.rf_v, rm, sh(128 // es)), s.zext(idx, 8))
    return elem if n == 1 else s.b.replicate(elem, sh(n))


def _second(s: S, e: Encoding, F, es, n, part=0):
    """Second operand: Vm (vector/scalar) or a by-element operand."""
    if 'elem' in e.name:
        return _elem_operand(s, e, F, es, n)
    return rd_part(s, F('Rm'), part, n, es) if part else rd(s, F('Rm'), n, es)


def _dmull(s: S, a, b):
    """SignedSatQ{2e}(2 * a * b) (saturates only for a == b == INT_MIN)."""
    e = a.width
    p = s.mul(s.sext(a, 2 * e), s.sext(b, 2 * e))
    both_min = s.and_(s.eqc(a, 1 << (e - 1)), s.eqc(b, 1 << (e - 1)))
    p2 = s.lsl(p, s.cl(1, p))
    return s.select(both_min, s.cl((1 << (2 * e - 1)) - 1, p2), p2), both_min


DMULL = {'sqdmull_advsimd_vec': 0, 'sqdmull_advsimd_elt': 0, 'sqdmlal_advsimd_vec': 1,
         'sqdmlal_advsimd_elt': 1, 'sqdmlsl_advsimd_vec': -1, 'sqdmlsl_advsimd_elt': -1}


@simd(*DMULL, spec=arr_spec((1, 2), scalar_sizes=(1, 2)))
def _sqdmull(s: S, e: Encoding, F):
    es = esize_of(e)
    scalar = is_scalar(e)
    part = 0 if scalar else e.fixed('Q')
    n = 1 if scalar else 64 // es
    a = s.v_read(F('Rn'), es) if scalar else rd_part(s, F('Rn'), part, n, es)
    b = _second(s, e, F, es, n, part) if not scalar or 'elem' in e.name else s.v_read(F('Rm'), es)
    prod, sat1 = _dmull(s, a, b)
    acc = DMULL[e.file]
    if acc:
        d = s.v_read(F('Rd'), 2 * es) if scalar else rd(s, F('Rd'), n, 2 * es)
        w = 4 * es if es < 32 else 128
        x, y = s.sext(d, w), s.sext(prod, w)
        prod, sat2 = sat(s, s.add(x, y) if acc > 0 else s.sub(x, y), 2 * es, False)
        sat1 = s.orr(sat1, sat2)
    wr(s, F('Rd'), prod)
    set_qc(s, sat1)


def _qdmulh(s: S, a, b, rounding, acc=None, sub=False):
    """SQDMULH/SQRDMULH and SQRDMLAH/SQRDMLSH (acc given)."""
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


QDMULH = {'sqdmulh_advsimd_elt': (False, None), 'sqrdmulh_advsimd_elt': (True, None),
          'sqrdmlah_advsimd_vec': (True, 'add'), 'sqrdmlah_advsimd_elt': (True, 'add'),
          'sqrdmlsh_advsimd_vec': (True, 'sub'), 'sqrdmlsh_advsimd_elt': (True, 'sub')}


@simd(*QDMULH, spec=arr_spec((1, 2), scalar_sizes=(1, 2)))
def _qdmulh_all(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    rounding, acc = QDMULH[e.file]
    a = rd(s, F('Rn'), n, es)
    b = _second(s, e, F, es, n)
    d = rd(s, F('Rd'), n, es) if acc else None
    r, saturated = _qdmulh(s, a, b, rounding, d, acc == 'sub')
    wr(s, F('Rd'), r)
    set_qc(s, saturated)


@simd('suqadd_advsimd', 'usqadd_advsimd', spec=arr_spec())
def _sqadd_mixed(s: S, e: Encoding, F):
    es = esize_of(e)
    n = lanes_of(e, es)
    w = _wide(es)
    a, d = rd(s, F('Rn'), n, es), rd(s, F('Rd'), n, es)
    if e.file == 'suqadd_advsimd':           # UInt(Vn) + SInt(Vd), signed result
        x, unsigned = s.add(s.zext(a, w), s.sext(d, w)), False
    else:                                    # SInt(Vn) + UInt(Vd), unsigned result
        x, unsigned = s.add(s.sext(a, w), s.zext(d, w)), True
    r, saturated = sat(s, x, es, unsigned)
    wr(s, F('Rd'), r)
    set_qc(s, saturated)


# -----------------------------------------------------------------------------
# Unsigned reciprocal (square root) estimates: 9-bit lookup tables
# -----------------------------------------------------------------------------
def recip_estimate(a):
    """RecipEstimate(a, FALSE) for a in 256..511."""
    a = a * 2 + 1
    b = (1 << 19) // a
    return (b + 1) // 2


def rsqrt_estimate(a):
    """RecipSqrtEstimate(a, FALSE) for a in 128..511."""
    if a < 256:
        a = a * 2 + 1
    else:
        a = (a >> 1) << 1
        a = (a + 1) * 2
    b = 512
    while a * (b + 1) * (b + 1) < 1 << 28:
        b += 1
    return (b + 1) // 2


RECIP_TABLE = [recip_estimate(a) & 0x1FF if a >= 256 else 0 for a in range(512)]
RSQRT_TABLE = [rsqrt_estimate(a) & 0x1FF if a >= 128 else 0 for a in range(512)]


@simd('urecpe_advsimd', 'ursqrte_advsimd', spec=lambda e: [('2S', {'Q': 0, 'sz': 0}),
                                                            ('4S', {'Q': 1, 'sz': 0})])
def _uestimate(s: S, e: Encoding, F):
    n = 2 << e.fixed('Q')
    a = rd(s, F('Rn'), n, 32)
    recip = e.file == 'urecpe_advsimd'
    table = s.ctx.table_op('recip_estimate_9' if recip else 'rsqrt_estimate_9', 9, 9,
                           RECIP_TABLE if recip else RSQRT_TABLE)
    est = s.call(table, [s.bits(a, 23, 9)])[0]
    small = s.not_(s.bits(a, 31, 1)) if recip else s.eqc(s.bits(a, 30, 2), 0)
    r = s.select(small, s.cl(0xFFFFFFFF, a), s.lsl(s.zext(est, 32), s.cl(23, a)))
    wr(s, F('Rd'), r)


# -----------------------------------------------------------------------------
# Single-structure loads/stores and load-and-replicate
# -----------------------------------------------------------------------------
def _sngl_esize(e: Encoding) -> int:
    kind = e.name.split('_')[2][0]                       # B1 / H2 / S3 / D4 / BX1 ...
    return {'B': 8, 'H': 16, 'S': 32, 'D': 64}[kind]


def _sngl_index(s: S, e: Encoding, F, es):
    q = F('Q')
    if es == 8:
        return s.concat(q, F('S'), F('size'))
    if es == 16:
        return s.concat(q, F('S'), s.bits(F('size'), 1, 1))
    if es == 32:
        return s.concat(q, F('S'))
    return s.zext(q, 1)


def _post(s: S, e: Encoding, F, base, total):
    if 'asisdlsop' not in e.name:
        return lambda: None
    if e.fixed('Rm') == 31:
        new = s.add(base, s.c(total, 64))
    else:
        new = s.add(base, s.x_read(F('Rm'), 64))
    return lambda: s.xsp_write(F('Rn'), new)


def _insert_lane(s: S, t, lane, value, es):
    n = 128 // es
    old = s.b.read(s.ctx.rf_v, t, sh(n))
    hit = s.eq(iota(s, n), s.b.replicate(s.zext(lane, 8), sh(n)))
    s.b.write(s.ctx.rf_v, t, s.select(hit, s.b.replicate(value, sh(n)), old))


SNGL = {f'{op}{k}_advsimd_sngl': (op == 'ld', k) for op in ('ld', 'st') for k in range(1, 5)}


@sem(*SNGL)
def _ldst_sngl(s: S, e: Encoding, F):
    load, selem = SNGL[e.file]
    es = _sngl_esize(e)
    ebytes = es // 8
    base = s.xsp_read(F('Rn'), 64)
    writeback = _post(s, e, F, base, selem * ebytes)
    lane = _sngl_index(s, e, F, es)
    for k in range(selem):
        t = _vreg(s, F, 'Rt', k)
        addr = s.add(base, s.c(k * ebytes, 64))
        if load:
            _insert_lane(s, t, lane, s.mem_read(addr, es), es)
        else:
            src = s.b.read(s.ctx.rf_v, t, sh(128 // es))
            s.mem_write(addr, _element(s, src, s.zext(lane, 8)))
    writeback()


@simd('ld2r_advsimd', 'ld3r_advsimd', 'ld4r_advsimd', spec=arr_spec(one_d=True))
def _ldnr(s: S, e: Encoding, F):
    es = esize_of(e)
    n = (64 << e.fixed('Q')) // es
    selem = int(e.file[2])
    base = s.xsp_read(F('Rn'), 64)
    writeback = _post(s, e, F, base, selem * es // 8)
    for k in range(selem):
        elem = s.mem_read(s.add(base, s.c(k * es // 8, 64)), es)
        wr(s, _vreg(s, F, 'Rt', k), elem if n == 1 else s.b.replicate(elem, sh(n)))
    writeback()


# -----------------------------------------------------------------------------
# Dot products and 8-bit integer matrix multiply
# -----------------------------------------------------------------------------
DOT = {'sdot_advsimd_vec': (True, True), 'udot_advsimd_vec': (False, False),
       'usdot_advsimd_vec': (False, True), 'sdot_advsimd_elt': (True, True),
       'udot_advsimd_elt': (False, False), 'usdot_advsimd_elt': (False, True),
       'sudot_advsimd_elt': (True, False)}


def _dot_spec(e):
    return [(n, a) for n, a in [('2S', {'Q': 0, 'size': 2}), ('4S', {'Q': 1, 'size': 2})]
            if _fits(e, {k: v for k, v in a.items() if k in e.fields})]


@simd(*DOT, spec=lambda e: [(n, {k: v for k, v in a.items() if k in {f.name for f in e.operands}})
                           for n, a in _dot_spec(e)])
def _dot(s: S, e: Encoding, F):
    n = 2 << e.fixed('Q')
    s1, s2 = DOT[e.file]
    a = rd(s, F('Rn'), 4 * n, 8)
    if 'elt' in e.file:
        full = s.b.read(s.ctx.rf_v, s.concat(F('M'), F('Rm')), sh(16))
        base = s.lsl(s.b.replicate(s.zext(s.concat(F('H'), F('L')), 8), sh(n)), s.c(2, 8, sh(n)))
    else:
        full = rd(s, F('Rm'), 4 * n, 8)
        base = s.lsl(iota(s, n), s.c(2, 8, sh(n)))
    acc = rd(s, F('Rd'), n, 32)
    group = s.lsl(iota(s, n), s.c(2, 8, sh(n)))
    for i in range(4):
        x = ext(s, pick(s, a, s.add(group, s.c(i, 8, sh(n)))), 32, s1)
        y = ext(s, pick(s, full, s.add(base, s.c(i, 8, sh(n)))), 32, s2)
        acc = s.add(acc, s.mul(x, y))
    wr(s, F('Rd'), acc)


MMLA = {'smmla_advsimd_vec': (True, True), 'ummla_advsimd_vec': (False, False),
        'usmmla_advsimd_vec': (False, True)}


@sem(*MMLA)
def _mmla(s: S, e: Encoding, F):
    s1, s2 = MMLA[e.file]
    a, b = rd(s, F('Rn'), 16, 8), rd(s, F('Rm'), 16, 8)
    lane = iota(s, 4)
    i8 = s.lsl(s.lsr(lane, s.c(1, 8, sh(4))), s.c(3, 8, sh(4)))      # 8 * (lane >> 1)
    j8 = s.lsl(s.and_(lane, s.c(1, 8, sh(4))), s.c(3, 8, sh(4)))     # 8 * (lane & 1)
    acc = rd(s, F('Rd'), 4, 32)
    for k in range(8):
        x = ext(s, pick(s, a, s.add(i8, s.c(k, 8, sh(4)))), 32, s1)
        y = ext(s, pick(s, b, s.add(j8, s.c(k, 8, sh(4)))), 32, s2)
        acc = s.add(acc, s.mul(x, y))
    wr(s, F('Rd'), acc)


# -----------------------------------------------------------------------------
# AES
# -----------------------------------------------------------------------------
def _gf_mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        a = ((a << 1) ^ (0x1B if a & 0x80 else 0)) & 0xFF
        b >>= 1
    return r


def _aes_sbox():
    inv = [0] * 256
    for x in range(1, 256):
        for y in range(1, 256):
            if _gf_mul(x, y) == 1:
                inv[x] = y
                break
    sbox = []
    for x in range(256):
        b = inv[x]
        r = b
        for k in range(1, 5):
            r ^= ((b << k) | (b >> (8 - k))) & 0xFF
        sbox.append(r ^ 0x63)
    return sbox


AES_SBOX = _aes_sbox()
AES_INV_SBOX = [AES_SBOX.index(i) for i in range(256)]


def _xtime(s: S, b):
    hi = s.bits(b, 7, 1)
    return s.xor(s.lsl(b, s.cl(1, b)), s.and_(s.replicate1(hi, 8), s.cl(0x1B, b)))


def _gmul(s: S, b, k):
    """b * k in GF(2^8) for a constant k."""
    acc, p = None, b
    while k:
        if k & 1:
            acc = p if acc is None else s.xor(acc, p)
        k >>= 1
        if k:
            p = _xtime(s, p)
    return acc


def _in_column(s: S, i, k):
    """Byte index of row (r + k) mod 4 in the column of byte i (4c + r)."""
    return s.orr(s.and_(i, s.c(0xFC, 8, sh(16))), s.and_(s.add(i, s.c(k, 8, sh(16))), s.c(3, 8, sh(16))))


@sem('aese_advsimd', 'aesd_advsimd')
def _aes_round(s: S, e: Encoding, F):
    x = s.xor(rd(s, F('Rd'), 16, 8), rd(s, F('Rn'), 16, 8))
    i = iota(s, 16)
    r = s.and_(i, s.c(3, 8, sh(16)))
    c = s.lsr(i, s.c(2, 8, sh(16)))
    enc = e.file == 'aese_advsimd'
    col = s.add(c, r) if enc else s.sub(c, r)            # (Inv)ShiftRows
    x = pick(s, x, s.orr(s.lsl(s.and_(col, s.c(3, 8, sh(16))), s.c(2, 8, sh(16))), r))
    table = s.ctx.table_op('aes_sbox' if enc else 'aes_inv_sbox', 8, 8,
                           AES_SBOX if enc else AES_INV_SBOX)
    wr(s, F('Rd'), s.call(table, [x])[0])


@sem('aesmc_advsimd', 'aesimc_advsimd')
def _aes_mix(s: S, e: Encoding, F):
    x = rd(s, F('Rn'), 16, 8)
    i = iota(s, 16)
    rows = [x] + [pick(s, x, _in_column(s, i, k)) for k in (1, 2, 3)]
    coeffs = (2, 3, 1, 1) if e.file == 'aesmc_advsimd' else (0x0E, 0x0B, 0x0D, 0x09)
    acc = None
    for v, k in zip(rows, coeffs):
        t = v if k == 1 else _gmul(s, v, k)
        acc = t if acc is None else s.xor(acc, t)
    wr(s, F('Rd'), acc)


# -----------------------------------------------------------------------------
# SHA1 / SHA256 (32-bit words, unrolled)
# -----------------------------------------------------------------------------
def _words(s: S, idx, count=4):
    v = s.b.read(s.ctx.rf_v, idx)
    return [s.bits(v, 32 * k, 32) for k in range(count)]


def _write_words(s: S, idx, words):
    s.v_write(idx, s.concat(*reversed(words)))


def _rol(s: S, x, k):
    return s.ror(x, s.c(32 - k, 32))


def _ror(s: S, x, k):
    return s.ror(x, s.c(k, 32))


def _choose(s, x, y, z):
    return s.xor(s.and_(s.xor(y, z), x), z)


def _parity(s, x, y, z):
    return s.xor(s.xor(x, y), z)


def _majority(s, x, y, z):
    return s.orr(s.and_(x, y), s.and_(s.orr(x, y), z))


SHA1 = {'sha1c_advsimd': _choose, 'sha1p_advsimd': _parity, 'sha1m_advsimd': _majority}


@sem(*SHA1)
def _sha1(s: S, e: Encoding, F):
    x = _words(s, F('Rd'))
    y = s.v_read(F('Rn'), 32)
    w = _words(s, F('Rm'))
    for k in range(4):
        t = SHA1[e.file](s, x[1], x[2], x[3])
        y = s.add(s.add(s.add(y, _rol(s, x[0], 5)), t), w[k])
        x[1] = _rol(s, x[1], 30)
        y, x = x[3], [y, x[0], x[1], x[2]]
    _write_words(s, F('Rd'), x)


@sem('sha1h_advsimd')
def _sha1h(s: S, e: Encoding, F):
    s.v_write(F('Rd'), _rol(s, s.v_read(F('Rn'), 32), 30))


@sem('sha1su0_advsimd')
def _sha1su0(s: S, e: Encoding, F):
    d, n, m = (s.b.read(s.ctx.rf_v, F(r)) for r in ('Rd', 'Rn', 'Rm'))
    r = s.concat(s.trunc(n, 64), s.bits(d, 64, 64))
    s.v_write(F('Rd'), s.xor(s.xor(r, d), m))


@sem('sha1su1_advsimd')
def _sha1su1(s: S, e: Encoding, F):
    d, n = s.b.read(s.ctx.rf_v, F('Rd')), s.b.read(s.ctx.rf_v, F('Rn'))
    t = s.xor(d, s.lsr(n, s.c(32, 128)))
    tw = [s.bits(t, 32 * k, 32) for k in range(4)]
    out = [_rol(s, tw[k], 1) for k in range(4)]
    out[3] = s.xor(out[3], _rol(s, tw[0], 2))
    _write_words(s, F('Rd'), out)


def _sigma(s, x, a, b, c):
    return s.xor(s.xor(_ror(s, x, a), _ror(s, x, b)), _ror(s, x, c))


@sem('sha256h_advsimd', 'sha256h2_advsimd')
def _sha256h(s: S, e: Encoding, F):
    x, y, w = _words(s, F('Rd')), _words(s, F('Rn')), _words(s, F('Rm'))
    if e.file == 'sha256h2_advsimd':                     # SHA256hash(V[n], V[d], V[m], FALSE)
        x, y = y, x
    for k in range(4):
        chs = _choose(s, y[0], y[1], y[2])
        maj = _majority(s, x[0], x[1], x[2])
        t = s.add(s.add(s.add(y[3], _sigma(s, y[0], 6, 11, 25)), chs), w[k])
        x[3] = s.add(t, x[3])
        y[3] = s.add(s.add(t, _sigma(s, x[0], 2, 13, 22)), maj)
        # (y, x) = ROL(y::x, 32)
        y, x = [x[3], y[0], y[1], y[2]], [y[3], x[0], x[1], x[2]]
    _write_words(s, F('Rd'), y if e.file == 'sha256h2_advsimd' else x)


@sem('sha256su0_advsimd')
def _sha256su0(s: S, e: Encoding, F):
    d, n = _words(s, F('Rd')), _words(s, F('Rn'))
    t = d[1:] + [n[0]]
    out = [s.add(s.xor(s.xor(_ror(s, t[k], 7), _ror(s, t[k], 18)), s.lsr(t[k], s.c(3, 32))), d[k])
           for k in range(4)]
    _write_words(s, F('Rd'), out)


@sem('sha256su1_advsimd')
def _sha256su1(s: S, e: Encoding, F):
    d, n, m = _words(s, F('Rd')), _words(s, F('Rn')), _words(s, F('Rm'))
    t0 = n[1:] + [m[0]]

    def f(x):
        return s.xor(s.xor(_ror(s, x, 17), _ror(s, x, 19)), s.lsr(x, s.c(10, 32)))
    out = [None] * 4
    t1 = [m[2], m[3]]
    for k in range(2):
        out[k] = s.add(s.add(f(t1[k]), d[k]), t0[k])
    for k in range(2, 4):
        out[k] = s.add(s.add(f(out[k - 2]), d[k]), t0[k])
    _write_words(s, F('Rd'), out)
