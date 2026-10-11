"""SME instructions (FEAT_SME).

ZA is one register of VL / 8 vectors of VL bits (`S.za_read`). Read as esize-bit
elements it has dim * dim * esize / 8 lanes, dim = VL / esize, row-major: ZA
vector r is lanes [r * dim, (r + 1) * dim). The tile t of esize-bit elements
(ZAt.<T>, t < esize / 8) is the vectors t, t + esize / 8, t + 2 * esize / 8, ...:
its element (i, j) is element j of ZA vector i * esize / 8 + t. Tile accesses
are lane-wise statements on the whole of ZA, each lane computing its tile and
coordinates, and slices (horizontal or vertical, the `V` field) are gathers, so
one description serves every vector length.

PSTATE.SM and PSTATE.ZA are the `SVCR` register. The streaming vector length is
the vector length (SVL = VL) and FEAT_SME_FA64 is enabled (Linux enables it when
it is implemented), so every other instruction behaves the same in streaming
mode. The instructions that need streaming mode or ZA call `sme_access_trap`
when they are off; the CPACR/CPTR/SMCR enables are the environment's.

Only the FEAT_SME encodings of the files are described (not FEAT_SME_I16I64,
FEAT_SME_F64F64, FEAT_SME_F16F16 or FEAT_SME2), with REVD, PSEL, SCLAMP and
UCLAMP (FEAT_SME || FEAT_SVE2p1). The SVE2 instructions that streaming mode
also provides are not described (FEAT_SVE2 is not).
"""
from python.lira import float_ops as FO
from python.lira.ir import Shape

from . import insns
from .insns import sem
from .insns_simd import ext, smax, smin, umax, umin
from .insns_sve import (IW, es, fneg, iota, load_lanes, p_raw, pick_scalar, rep, rmv,
                        size_spec, store_lanes, vl_bytes, zs)
from .lib import S, VQ, VQVQ
from .xmlspec import Encoding

FEATURES = {'FEAT_SME', 'FEAT_SME || FEAT_SVE2p1'}
SME_FILES: set = set()
insns.KEEP.append(lambda e: e.file not in SME_FILES or e.feature in FEATURES)

ZW = 32                                     # width of ZA element indices
ZA_FP = ('default_nan', 'no_flags')         # the ASL *_ZA float helpers (FPMulAdd_ZA, ...)


def sme(*files, spec=None, undef=None):
    SME_FILES.update(files)
    return sem(*files, spec=spec, undef=undef)


# -----------------------------------------------------------------------------
# ZA helpers
# -----------------------------------------------------------------------------
def zas(esize: int) -> Shape:
    """Shape of ZA as esize-bit elements."""
    return Shape(2048 // esize, VQVQ)


def za_rep(s: S, v, esize: int):
    return s.b.replicate(v, zas(esize))


def dim(s: S, esize: int, w: int = ZW):
    """VL / esize: elements in a ZA vector, slices of a tile."""
    return s.mul(s.vq(w), s.c(128 // esize, w))


def za_vectors(s: S, esize: int):
    """(ZA vector, element in the vector) of every ZA element."""
    lane = s.b.index(ZW, zas(esize))
    d = za_rep(s, dim(s, esize), esize)
    vec = s.div_u(lane, d, s.cl(0, lane))
    return vec, s.sub(lane, s.mul(vec, d))


def za_tiles(s: S, esize: int):
    """(tile, row, column) of every ZA element in the tiles of esize-bit elements."""
    vec, col = za_vectors(s, esize)
    k = esize // 8
    if k == 1:
        return s.cl(0, vec), vec, col
    return s.and_(vec, s.cl(k - 1, vec)), s.lsr(vec, s.cl(k.bit_length() - 1, vec)), col


def in_tile(s: S, tile, t, esize: int):
    return s.eq(tile, za_rep(s, s.zext(t, ZW), esize))


def take(s: S, v, idx):
    """v[idx] in every lane of idx (idx is in range)."""
    return s.b.gather(v, idx, s.c(0, v.width, idx.shape))


OFFSET = {8: 'off4', 16: 'off3', 32: 'off2', 64: 'o1', 128: None}
TSIZE = {'B': 8, 'H': 16, 'W': 32, 'D': 64, 'Q': 128}


def slice_number(s: S, F, esize: int, reg: str = 'Rs', off: str = None):
    """(UInt(W[12 + reg]) + offset) MOD (VL / esize)."""
    index = s.xsp_read(s.concat(s.c(0b011, 3), F(reg)), 32)    # W12..W15
    v = s.zext(index, 64)
    off = off or OFFSET[esize]
    if off:
        v = s.add(v, s.zext(F(off), 64))
    return s.trunc(s.rem_u(v, dim(s, esize, 64)), ZW)


def tile_slice(s: S, F, esize: int, tile_field: str):
    """(tile, vertical, slice) of a ZA tile slice operand."""
    tile = s.c(0, ZW) if esize == 8 else s.zext(F(tile_field), ZW)
    return tile, F('V'), slice_number(s, F, esize)


def slice_read(s: S, esize: int, tile, vertical, sl):
    """ZAslice(tile, esize, vertical, slice): the elements of row (horizontal)
    or column (vertical) `sl` of the tile."""
    e = iota(s, esize, ZW)
    sl, v = rep(s, sl, esize), rep(s, vertical, esize)
    row, col = s.select(v, e, sl), s.select(v, sl, e)
    vec = s.add(s.mul(row, s.cl(esize // 8, row)), rep(s, tile, esize))
    index = s.add(s.mul(vec, rep(s, dim(s, esize), esize)), col)
    return take(s, s.za_read(esize), index)


def slice_write(s: S, esize: int, tile, vertical, sl, value, active=None):
    """ZAslice(tile, esize, vertical, slice) = value, only the `active` elements."""
    t, row, col = za_tiles(s, esize)
    v = za_rep(s, vertical, esize)
    pos = s.select(v, row, col)                            # element of the slice
    hit = s.and_(s.eq(t, za_rep(s, tile, esize)), s.eq(s.select(v, col, row), za_rep(s, sl, esize)))
    if active is not None:
        hit = s.and_(hit, take(s, active, pos))
    za = s.za_read(esize)
    s.za_write(s.select(hit, take(s, value, pos), za))


# -----------------------------------------------------------------------------
# Outer products and accumulates
# -----------------------------------------------------------------------------
# Each ZA lane of the 32-bit tiles takes element `row` of Zn and Pn and element
# `col` of Zm and Pm; lanes outside the tile ZAda or inactive keep their value.
def _operands(s: S, F, row, col):
    """Zn[row], Zm[col] as 32-bit elements, and Pn, Pm as their 4 predicate bits."""
    a, b = take(s, s.z_read(F('Zn'), 32), row), take(s, s.z_read(F('Zm'), 32), col)
    pa, pb = take(s, p_raw(s, F('Pn'), 32), row), take(s, p_raw(s, F('Pm'), 32), col)
    return a, b, pa, pb


@sme('fmopa_za_pp_zz', 'fmops_za_pp_zz')
def _fmopa(s: S, e: Encoding, F):
    s.sme_check()
    t, row, col = za_tiles(s, 32)
    acc = s.za_read(32)
    a, b, pa, pb = _operands(s, F, row, col)
    if e.mnemonic == 'FMOPS':
        a = fneg(s, a)
    # FPMulAdd_ZA: no exceptions, default NaN; computed on every lane
    r = s.fop('fmuladd', 32, [acc, a, b, rmv(s, FO.DYN, acc)], modifiers=ZA_FP)
    hit = s.and1(in_tile(s, t, F('ZAda'), 32), s.trunc(pa, 1), s.trunc(pb, 1))
    s.za_write(s.select(hit, r, acc))


@sme('fmopa_za32_pp_zz', 'fmops_za32_pp_zz', 'bfmopa_za32_pp_zz', 'bfmops_za32_pp_zz')
def _fmopa_wide(s: S, e: Encoding, F):
    """Sums of two products of 16-bit pairs: an inactive element of a pair is
    +0, an active row element of FMOPS/BFMOPS is negated."""
    s.sme_check()
    t, row, col = za_tiles(s, 32)
    acc = s.za_read(32)
    a, b, pa, pb = _operands(s, F, row, col)
    negate = e.mnemonic.endswith('S')

    def pair(x, p, neg):
        out = []
        for h in (0, 1):                                   # predicate bit of half h is 2h
            act, v = s.bits(p, 2 * h, 1), s.bits(x, 16 * h, 16)
            out.append((act, s.select(act, fneg(s, v) if neg else v, s.cl(0, v))))
        return out

    (pr0, er0), (pr1, er1) = pair(a, pa, negate)
    (pc0, ec0), (pc1, ec1) = pair(b, pb, False)
    if e.mnemonic.startswith('BF'):                        # BFDotAdd (FEAT_EBF16 is not described)
        r = s.fop('bfdotadd', 32, [acc, er0, er1, ec0, ec1])
    else:                                                  # FPDotAdd_ZA
        r = s.fop('fdotadd', 32, [acc, er0, er1, ec0, ec1, rmv(s, FO.DYN, acc)], modifiers=ZA_FP)
    active = s.orr(s.and_(pr0, pc0), s.and_(pr1, pc1))
    s.za_write(s.select(s.and_(in_tile(s, t, F('ZAda'), 32), active), r, acc))


# (Zn signed, Zm signed) of the integer outer products
IMOPA = {'SMOP': (True, True), 'UMOP': (False, False), 'SUMOP': (True, False), 'USMOP': (False, True)}


@sme('smopa_za_pp_zz', 'smops_za_pp_zz', 'umopa_za_pp_zz', 'umops_za_pp_zz',
     'sumopa_za_pp_zz', 'sumops_za_pp_zz', 'usmopa_za_pp_zz', 'usmops_za_pp_zz')
def _imopa(s: S, e: Encoding, F):
    """Sums of four products of 8-bit elements, each counted if both are active."""
    s.sme_check()
    t, row, col = za_tiles(s, 32)
    acc = s.za_read(32)
    a, b, pa, pb = _operands(s, F, row, col)
    signed1, signed2 = IMOPA[e.mnemonic[:-1]]
    active = s.and_(pa, pb)
    r = acc
    for k in range(4):
        x = ext(s, s.bits(a, 8 * k, 8), 32, signed1)
        y = ext(s, s.bits(b, 8 * k, 8), 32, signed2)
        prod = s.select(s.bits(active, k, 1), s.mul(x, y), s.cl(0, acc))
        r = s.sub(r, prod) if e.mnemonic.endswith('S') else s.add(r, prod)
    s.za_write(s.select(in_tile(s, t, F('ZAda'), 32), r, acc))


@sme('addha_za_pp_z', 'addva_za_pp_z')
def _addha(s: S, e: Encoding, F):
    """ADDHA adds element `col` of Zn to every row, ADDVA element `row` to every column."""
    s.sme_check()
    t, row, col = za_tiles(s, 32)
    acc = s.za_read(32)
    v = take(s, s.z_read(F('Zn'), 32), col if e.mnemonic == 'ADDHA' else row)
    active = s.and_(take(s, s.p_read(F('Pn'), 32), row), take(s, s.p_read(F('Pm'), 32), col))
    s.za_write(s.select(s.and_(in_tile(s, t, F('ZAda'), 32), active), s.add(acc, v), acc))


# -----------------------------------------------------------------------------
# Moves, loads and stores of tile slices, ZA vectors, ZERO
# -----------------------------------------------------------------------------
def _mova_esize(e: Encoding) -> int:
    return TSIZE[e.name[-1].upper()]


@sme('mova_za_p_rz')
def _mova_to_za(s: S, e: Encoding, F):
    s.sme_check()
    n = _mova_esize(e)
    tile, v, sl = tile_slice(s, F, n, 'ZAd')
    slice_write(s, n, tile, v, sl, s.z_read(F('Zn'), n), s.p_read(F('Pg'), n))


@sme('mova_z_p_rza')
def _mova_to_z(s: S, e: Encoding, F):
    s.sme_check()
    n = _mova_esize(e)
    tile, v, sl = tile_slice(s, F, n, 'ZAn')
    r = slice_read(s, n, tile, v, sl)
    s.z_write(F('Zd'), s.select(s.p_read(F('Pg'), n), r, s.z_read(F('Zd'), n)))


@sme('ld1b_za_p_rrr', 'ld1h_za_p_rrr', 'ld1w_za_p_rrr', 'ld1d_za_p_rrr', 'ld1q_za_p_rrr',
     'st1b_za_p_rrr', 'st1h_za_p_rrr', 'st1w_za_p_rrr', 'st1d_za_p_rrr', 'st1q_za_p_rrr')
def _ldst_slice(s: S, e: Encoding, F):
    """Element e is at X[n]|SP + (X[m] + e) * esize / 8; a load writes the whole
    slice (inactive elements are zero), a store writes the active elements."""
    s.sme_check()
    n = TSIZE[e.mnemonic[-1]]
    tile, v, sl = tile_slice(s, F, n, 'ZAt')
    pg = s.p_read(F('Pg'), n)
    index = s.add(rep(s, s.x_read(F('Rm'), 64), n), s.zext(iota(s, n), 64))
    addrs = s.add(rep(s, s.xsp_read(F('Rn'), 64), n), s.mul(index, s.c(n // 8, 64, zs(n))))
    if e.mnemonic.startswith('LD'):
        slice_write(s, n, tile, v, sl, load_lanes(s, pg, addrs, n))
    else:
        store_lanes(s, pg, addrs, slice_read(s, n, tile, v, sl))


@sme('ldr_za_ri', 'str_za_ri')
def _ldr_str_za(s: S, e: Encoding, F):
    """ZA vector (W[12 + Rv] + off4) MOD (VL / 8), the horizontal slice of
    ZA0.B, at X[n]|SP + off4 * VL / 8 (SCTLR.A is clear: no alignment check)."""
    s.sme_check(streaming=False)
    vec = slice_number(s, F, 8, 'Rv', 'off4')
    addr0 = s.add(s.xsp_read(F('Rn'), 64), s.mul(s.zext(F('off4'), 64), vl_bytes(s)))
    addrs = s.add(rep(s, addr0, 8), s.zext(iota(s, 8), 64))
    tile, horizontal = s.c(0, ZW), s.c(0, 1)
    if e.mnemonic == 'LDR':
        slice_write(s, 8, tile, horizontal, vec, s.env(s.ctx.envs['mem_read_8'], [addrs])[0])
    else:
        s.env(s.ctx.envs['mem_write_8'], [addrs, slice_read(s, 8, tile, horizontal, vec)])


@sme('zero_za_i')
def _zero(s: S, e: Encoding, F):
    """Zero the 64-bit tiles ZA<i>.D with imm8<i> set."""
    s.sme_check(streaming=False)
    vec, _ = za_vectors(s, 64)
    tile = s.and_(vec, s.cl(7, vec))
    hit = s.trunc(s.lsr(za_rep(s, s.zext(F('imm8'), ZW), 64), tile), 1)
    za = s.za_read(64)
    s.za_write(s.select(hit, s.cl(0, za), za))


# -----------------------------------------------------------------------------
# Streaming vector length, PSTATE.SM/ZA
# -----------------------------------------------------------------------------
@sme('rdsvl_r_i')
def _rdsvl(s: S, e: Encoding, F):
    s.x_write(F('Rd'), s.mul(s.sext(F('imm6'), 64), vl_bytes(s)))


@sme('addsvl_r_ri', 'addspl_r_ri')
def _addsvl(s: S, e: Encoding, F):
    unit = vl_bytes(s) if e.mnemonic == 'ADDSVL' else s.lsl(s.vq(), s.c(1, 64))   # SVL / 64
    x = s.xsp_read(F('Rn'), 64)
    s.xsp_write(F('Rd'), s.add(x, s.mul(s.sext(F('imm6'), 64), unit)))


# MSR SVCRSM/SVCRZA/SVCRSMZA, #imm (alias SMSTART/SMSTOP): CRm<2:1> selects the
# fields, CRm<0> is the value; CRm<2:1> = 00 is UNDEFINED
SVCR_FIELDS = [('SM', {'CRm': (0b0010, 0b0110)}), ('ZA', {'CRm': (0b0100, 0b0110)}),
               ('SMZA', {'CRm': (0b0110, 0b0110)})]


@sme('smstart_msr_imm', 'smstop_msr_imm', spec=lambda e: SVCR_FIELDS)
def _smstart(s: S, e: Encoding, F):
    fields = e.name.rsplit('_', 1)[1]
    value = s.bits(F('CRm'), 0, 1)
    s.svcr_write(value if 'SM' in fields else None, value if 'ZA' in fields else None)


# -----------------------------------------------------------------------------
# SVE instructions introduced with SME
# -----------------------------------------------------------------------------
@sme('revd_z_p_z')
def _revd(s: S, e: Encoding, F):
    """Swap the doublewords of the active quadwords."""
    x = s.z_read(F('Zn'), 128)
    r = s.concat(s.trunc(x, 64), s.bits(x, 64, 64))
    s.z_write(F('Zd'), s.select(s.p_read(F('Pg'), 128), r, s.z_read(F('Zd'), 128)))


# tszh:tszl: B xxx1, H xx10, S x100, D 1000; 0000 is UNDEFINED
PSEL_SIZES = [('B', {'tszl': (1, 1)}), ('H', {'tszl': (2, 3)}), ('S', {'tszl': (4, 7)}),
              ('D', {'tszh': 1, 'tszl': 0})]


@sme('psel_p_ppi', spec=lambda e: PSEL_SIZES)
def _psel(s: S, e: Encoding, F):
    """Pd = Pn if element (W[12 + Rv] + imm) MOD (VL / esize) of Pm is active, else 0."""
    n = es(e)
    imm5 = s.concat(F('i1'), F('tszh'), F('tszl'))
    imm = s.lsr(imm5, s.c({8: 1, 16: 2, 32: 3, 64: 4}[n], 5))      # imm5<4:k>
    index = s.zext(s.xsp_read(s.concat(s.c(0b011, 3), F('Rv')), 32), 64)
    elem = s.rem_u(s.add(index, s.zext(imm, 64)), s.mul(s.vq(), s.c(128 // n, 64)))
    active = pick_scalar(s, s.p_read(F('Pm'), n), s.trunc(elem, IW))
    shape = Shape(2, VQ)
    src = s.b.read(s.ctx.rf_p, F('Pn'), shape)
    s.b.write(s.ctx.rf_p, F('Pd'), s.select(s.b.replicate(active, shape), src, s.cl(0, src)))


@sme('sclamp_z_zz', 'uclamp_z_zz', spec=size_spec())
def _clamp(s: S, e: Encoding, F):
    """Min(Max(Zn, Zd), Zm)"""
    n = es(e)
    mx, mn = (smax, smin) if e.mnemonic == 'SCLAMP' else (umax, umin)
    r = mn(s, mx(s, s.z_read(F('Zn'), n), s.z_read(F('Zd'), n)), s.z_read(F('Zm'), n))
    s.z_write(F('Zd'), r)
