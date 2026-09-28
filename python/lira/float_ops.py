"""Standard floating-point operation bases for `fop` statements.

Executable reference semantics (see docs/float_ops.md). Values are IEEE 754
binary16/32/64 bit patterns; arithmetic is exact (`Fraction`) followed by one
rounding, transliterated from the Arm FP library (FPUnpack, FPRound,
FPProcessNaNs, ...) with FEAT_AFP disabled (FPCR.AH = FIZ = NEP = 0), no
trapped exceptions and IEEE half precision (AHP = 0).

A float operation reads the FPU *controls* and ORs exception *flags* into the
FPU state; both live in `FPUState`, which an interpreter fills from/writes back
to the architecture registers named by `FPUBinding`.
"""
import re
from dataclasses import dataclass, field
from fractions import Fraction
from math import isqrt
from typing import Callable, Dict, List, Optional, Set, Tuple

from .arch import Arch, FloatOperation

# Rounding-mode operand values (3 bits); DYN takes the mode from the FPU state.
# ODD (round to odd) is only used by conversions (e.g. AArch64 FCVTXN).
RNE, RTP, RTN, RTZ, RNA, ODD, DYN = 0, 1, 2, 3, 4, 5, 7

# Exception flags
INVALID, DIVBYZERO, OVERFLOW, UNDERFLOW, INEXACT, INPUT_DENORMAL = (
    'invalid', 'divbyzero', 'overflow', 'underflow', 'inexact', 'input_denormal')
FLAGS = (INVALID, DIVBYZERO, OVERFLOW, UNDERFLOW, INEXACT, INPUT_DENORMAL)

# Comparison result of fcmpq/fcmps
CMP_EQ, CMP_LT, CMP_GT, CMP_UN = 0, 1, 2, 3

FORMATS = {16: (5, 10), 32: (8, 23), 64: (11, 52)}  # N -> (E, F)


@dataclass
class FPUState:
    rmode: int = RNE          # RNE/RTP/RTN/RTZ
    fz: bool = False          # flush-to-zero for single/double
    fz16: bool = False        # flush-to-zero for half
    dn: bool = False          # default NaN
    flags: Set[str] = field(default_factory=set)


# -----------------------------------------------------------------------------
# Encoding helpers
# -----------------------------------------------------------------------------
ZERO, DENORMAL, NONZERO, INFINITY, QNAN, SNAN = range(6)
INF = float('inf')


def _fmt(n):
    e, f = FORMATS[n]
    return e, f, 2 - (1 << (e - 1))           # E, F, minimum exponent


def fp_zero(n, sign):
    return sign << (n - 1)


def fp_inf(n, sign):
    e, f, _ = _fmt(n)
    return (sign << (n - 1)) | (((1 << e) - 1) << f)


def fp_default_nan(n):
    e, f, _ = _fmt(n)
    return (((1 << e) - 1) << f) | (1 << (f - 1))


def fp_max_normal(n, sign):
    e, f, _ = _fmt(n)
    return (sign << (n - 1)) | (((1 << e) - 2) << f) | ((1 << f) - 1)


def unpack(bits: int, n: int, st: FPUState, flush: bool = True) -> Tuple[int, int, object]:
    """FPUnpackBase: (type, sign, value). `flush=False` for conversions of half
    precision (FPUnpackCV ignores FZ16)."""
    e, f, emin = _fmt(n)
    sign = bits >> (n - 1)
    exp = (bits >> f) & ((1 << e) - 1)
    frac = bits & ((1 << f) - 1)
    if exp == 0:
        if frac == 0:
            t, v = ZERO, Fraction(0)
        elif n == 16:
            if st.fz16 and flush:
                t, v = ZERO, Fraction(0)
            else:
                t, v = DENORMAL, Fraction(frac, 1 << f) * Fraction(2) ** emin
        elif st.fz:
            t, v = ZERO, Fraction(0)
            st.flags.add(INPUT_DENORMAL)
        else:
            t, v = DENORMAL, Fraction(frac, 1 << f) * Fraction(2) ** emin
    elif exp == (1 << e) - 1:
        if frac == 0:
            t, v = INFINITY, INF
        else:
            t, v = (QNAN if frac >> (f - 1) else SNAN), Fraction(0)
    else:
        t, v = NONZERO, (1 + Fraction(frac, 1 << f)) * Fraction(2) ** (exp - (1 << (e - 1)) + 1)
    return t, sign, (-v if sign else v)


def _is_nan(t):
    return t in (QNAN, SNAN)


def _flush_out(n, st, flush):
    return flush and (st.fz16 if n == 16 else st.fz)


def _ilog2(x: Fraction) -> int:
    e = x.numerator.bit_length() - x.denominator.bit_length()
    if Fraction(2) ** e > x:
        e -= 1
    return e


def fp_round(value: Fraction, n: int, st: FPUState, rounding: int, flush: bool = True,
             bf16: bool = False) -> int:
    """FPRoundBase (FPCR.AH = 0): round a non-zero exact value. With `bf16`,
    round to BFloat16 (n == 32) and return it in the upper half."""
    assert value != 0
    if bf16:
        r = _round_fmt(value, 8, 7, -126, 16, st, rounding, flush and st.fz)
        return r << 16
    e, f, emin = _fmt(n)
    return _round_fmt(value, e, f, emin, n, st, rounding, _flush_out(n, st, flush))


def _round_fmt(value, e, f, emin, n, st, rounding, flush_out):
    sign = int(value < 0)
    mant = -value if sign else value
    exponent = _ilog2(mant)
    mant = mant / Fraction(2) ** exponent
    if flush_out and exponent < emin:
        st.flags.add(UNDERFLOW)
        return fp_zero(n, sign)
    biased = max(exponent - emin + 1, 0)
    if biased == 0:
        mant = mant / Fraction(2) ** (emin - exponent)
    scaled = mant * (1 << f)
    int_mant = scaled.numerator // scaled.denominator
    error = scaled - int_mant
    if biased == 0 and error != 0:
        st.flags.add(UNDERFLOW)
    if rounding == RNE:
        up = error > Fraction(1, 2) or (error == Fraction(1, 2) and int_mant & 1)
        to_inf = True
    elif rounding == RTP:
        up, to_inf = error != 0 and not sign, not sign
    elif rounding == RTN:
        up, to_inf = error != 0 and bool(sign), bool(sign)
    elif rounding == RTZ:
        up, to_inf = False, False
    elif rounding == ODD:
        up, to_inf = False, False
    else:  # RNA
        up, to_inf = error >= Fraction(1, 2), True
    if up:
        int_mant += 1
        if int_mant == 1 << f:
            biased = 1
        if int_mant == 1 << (f + 1):
            biased += 1
            int_mant >>= 1
    if error != 0 and rounding == ODD and not int_mant & 1:
        int_mant += 1
    if biased >= (1 << e) - 1:
        inf = (sign << (n - 1)) | (((1 << e) - 1) << f)
        result = inf if to_inf else inf - 1
        st.flags.add(OVERFLOW)
        error = 1
    else:
        result = (sign << (n - 1)) | (biased << f) | (int_mant & ((1 << f) - 1))
    if error != 0:
        st.flags.add(INEXACT)
    return result


def _process_nan(t, op, n, st):
    e, f, _ = _fmt(n)
    if t == SNAN:
        op |= 1 << (f - 1)
        st.flags.add(INVALID)
    return fp_default_nan(n) if st.dn else op


def _process_nans(types, ops, n, st):
    for kind in (SNAN, QNAN):
        for t, op in zip(types, ops):
            if t == kind:
                return True, _process_nan(t, op, n, st)
    return False, 0


def _mode(rm, st):
    return st.rmode if rm == DYN else rm


def _exact_zero_sign(rounding):
    return 1 if rounding == RTN else 0


# -----------------------------------------------------------------------------
# Operation bases
# -----------------------------------------------------------------------------
def fadd(n, st, a, b, rm, negate_b=False):
    rounding = _mode(rm, st)
    t1, s1, v1 = unpack(a, n, st)
    t2, s2, v2 = unpack(b, n, st)
    done, result = _process_nans((t1, t2), (a, b), n, st)
    if done:
        return result
    if negate_b:                                   # FPSub
        s2, v2 = 1 - s2, -v2
    inf1, inf2 = t1 == INFINITY, t2 == INFINITY
    if inf1 and inf2 and s1 != s2:
        st.flags.add(INVALID)
        return fp_default_nan(n)
    if (inf1 and s1 == 0) or (inf2 and s2 == 0):
        return fp_inf(n, 0)
    if inf1 or inf2:
        return fp_inf(n, 1)
    if t1 == ZERO and t2 == ZERO and s1 == s2:
        return fp_zero(n, s1)
    r = v1 + v2
    if r == 0:
        return fp_zero(n, _exact_zero_sign(rounding))
    return fp_round(r, n, st, rounding)


def fsub(n, st, a, b, rm):
    return fadd(n, st, a, b, rm, negate_b=True)


def fmul(n, st, a, b, rm):
    rounding = _mode(rm, st)
    t1, s1, v1 = unpack(a, n, st)
    t2, s2, v2 = unpack(b, n, st)
    done, result = _process_nans((t1, t2), (a, b), n, st)
    if done:
        return result
    inf1, inf2, z1, z2 = t1 == INFINITY, t2 == INFINITY, t1 == ZERO, t2 == ZERO
    if (inf1 and z2) or (z1 and inf2):
        st.flags.add(INVALID)
        return fp_default_nan(n)
    if inf1 or inf2:
        return fp_inf(n, s1 ^ s2)
    if z1 or z2:
        return fp_zero(n, s1 ^ s2)
    return fp_round(v1 * v2, n, st, rounding)


def fdiv(n, st, a, b, rm):
    rounding = _mode(rm, st)
    t1, s1, v1 = unpack(a, n, st)
    t2, s2, v2 = unpack(b, n, st)
    done, result = _process_nans((t1, t2), (a, b), n, st)
    if done:
        return result
    inf1, inf2, z1, z2 = t1 == INFINITY, t2 == INFINITY, t1 == ZERO, t2 == ZERO
    if (inf1 and inf2) or (z1 and z2):
        st.flags.add(INVALID)
        return fp_default_nan(n)
    if inf1 or z2:
        if not inf1:
            st.flags.add(DIVBYZERO)
        return fp_inf(n, s1 ^ s2)
    if z1 or inf2:
        return fp_zero(n, s1 ^ s2)
    return fp_round(v1 / v2, n, st, rounding)


def fmuladd(n, st, addend, a, b, rm):
    """addend + a * b with a single rounding (FPMulAdd)."""
    rounding = _mode(rm, st)
    ta, sa, va = unpack(addend, n, st)
    t1, s1, v1 = unpack(a, n, st)
    t2, s2, v2 = unpack(b, n, st)
    inf1, inf2, z1, z2 = t1 == INFINITY, t2 == INFINITY, t1 == ZERO, t2 == ZERO
    done, result = _process_nans((ta, t1, t2), (addend, a, b), n, st)
    if ta == QNAN and ((inf1 and z2) or (z1 and inf2)):
        st.flags.add(INVALID)
        result = fp_default_nan(n)
    if done:
        return result
    infa, zeroa = ta == INFINITY, ta == ZERO
    sp, infp, zerop = s1 ^ s2, inf1 or inf2, z1 or z2
    if (inf1 and z2) or (z1 and inf2) or (infa and infp and sa != sp):
        st.flags.add(INVALID)
        return fp_default_nan(n)
    if (infa and sa == 0) or (infp and sp == 0):
        return fp_inf(n, 0)
    if infa or infp:
        return fp_inf(n, 1)
    if zeroa and zerop and sa == sp:
        return fp_zero(n, sa)
    r = va + v1 * v2
    if r == 0:
        return fp_zero(n, _exact_zero_sign(rounding))
    return fp_round(r, n, st, rounding)


def _sqrt_rounded(value: Fraction, prec: int) -> Fraction:
    """Square root with `prec` significant bits, truncated, with a sticky last
    bit when inexact (enough for a correct final rounding to fewer bits)."""
    q = _ilog2(value) // 2                          # sqrt(value) in [2^q, 2^(q+2))
    s = prec + 1 - q
    scaled = value * Fraction(4) ** s               # sqrt(scaled) = sqrt(value) * 2^s
    t = isqrt(scaled.numerator // scaled.denominator)
    if Fraction(t * t) != scaled:
        t |= 1
    return Fraction(t) / Fraction(2) ** s


def fsqrt(n, st, a, rm):
    rounding = _mode(rm, st)
    t, s, v = unpack(a, n, st)
    if _is_nan(t):
        return _process_nan(t, a, n, st)
    if t == ZERO:
        return fp_zero(n, s)
    if t == INFINITY and s == 0:
        return fp_inf(n, 0)
    if s:
        st.flags.add(INVALID)
        return fp_default_nan(n)
    return fp_round(_sqrt_rounded(v, FORMATS[n][1] + 3), n, st, rounding)


def _fmaxmin(n, st, a, b, is_max):
    t1, s1, v1 = unpack(a, n, st)
    t2, s2, v2 = unpack(b, n, st)
    done, result = _process_nans((t1, t2), (a, b), n, st)
    if done:
        return result
    first = (v1 > v2) if is_max else (v1 < v2)
    t, s, v = (t1, s1, v1) if first else (t2, s2, v2)
    if t == INFINITY:
        return fp_inf(n, s)
    if t == ZERO:
        return fp_zero(n, (s1 & s2) if is_max else (s1 | s2))
    return fp_round(v, n, st, st.rmode)


def _fnum(n, st, a, b, is_max):
    t1, _, _ = unpack(a, n, st)
    t2, _, _ = unpack(b, n, st)
    replacement = fp_inf(n, 1 if is_max else 0)     # a single QNaN loses
    if t1 == QNAN and t2 != QNAN:
        a = replacement
    elif t1 != QNAN and t2 == QNAN:
        b = replacement
    return _fmaxmin(n, st, a, b, is_max)


def fmax(n, st, a, b):
    return _fmaxmin(n, st, a, b, True)


def fmin(n, st, a, b):
    return _fmaxmin(n, st, a, b, False)


def fmaxnm(n, st, a, b):
    return _fnum(n, st, a, b, True)


def fminnm(n, st, a, b):
    return _fnum(n, st, a, b, False)


def _fcmp(n, st, a, b, signal):
    t1, _, v1 = unpack(a, n, st)
    t2, _, v2 = unpack(b, n, st)
    if _is_nan(t1) or _is_nan(t2):
        if signal or t1 == SNAN or t2 == SNAN:
            st.flags.add(INVALID)
        return CMP_UN
    return CMP_EQ if v1 == v2 else CMP_LT if v1 < v2 else CMP_GT


def fcmpq(n, st, a, b):
    """Quiet comparison: invalid only for signalling NaNs."""
    return _fcmp(n, st, a, b, False)


def fcmps(n, st, a, b):
    """Signalling comparison: invalid for any NaN."""
    return _fcmp(n, st, a, b, True)


def fcvtf(n, m, st, a, rm):
    """FPConvert from N-bit to M-bit float (half precision ignores FZ16)."""
    rounding = _mode(rm, st)
    t, s, v = unpack(a, n, st, flush=False)
    if _is_nan(t):
        if t == SNAN:
            st.flags.add(INVALID)
        if st.dn:
            return fp_default_nan(m)
        _, fn, _ = _fmt(n)
        _, fm, _ = _fmt(m)
        payload = a & ((1 << (fn - 1)) - 1)           # fraction without the quiet bit
        payload = payload << (fm - fn) if fm > fn else payload >> (fn - fm)
        return fp_inf(m, s) | (1 << (fm - 1)) | payload
    if t == INFINITY:
        return fp_inf(m, s)
    if t == ZERO:
        return fp_zero(m, s)
    return fp_round(v, m, st, rounding, flush=(m != 16))


def _round_int(value: Fraction, rounding: int) -> Tuple[int, Fraction]:
    i = value.numerator // value.denominator
    error = value - i
    if rounding == RNE:
        up = error > Fraction(1, 2) or (error == Fraction(1, 2) and i & 1)
    elif rounding == RTP:
        up = error != 0
    elif rounding == RTN:
        up = False
    elif rounding == RTZ:
        up = error != 0 and i < 0
    else:  # RNA
        up = error > Fraction(1, 2) or (error == Fraction(1, 2) and i >= 0)
    return i + int(up), error


def ftoi(n, m, st, a, fbits, rm, unsigned):
    """FPToFixed: N-bit float to M-bit (un)signed fixed point, saturating."""
    rounding = _mode(rm, st)
    t, s, v = unpack(a, n, st)
    if _is_nan(t):
        st.flags.add(INVALID)
    if t == INFINITY:
        i, error = (-(1 << 2000) if s else 1 << 2000), 0
    else:
        i, error = _round_int(v * (1 << fbits), rounding)
    lo, hi = (0, (1 << m) - 1) if unsigned else (-(1 << (m - 1)), (1 << (m - 1)) - 1)
    if i < lo or i > hi:
        st.flags.add(INVALID)
        i = min(max(i, lo), hi)
    elif error != 0:
        st.flags.add(INEXACT)
    return i & ((1 << m) - 1)


def ftosi(n, m, st, a, fbits, rm):
    return ftoi(n, m, st, a, fbits, rm, False)


def ftoui(n, m, st, a, fbits, rm):
    return ftoi(n, m, st, a, fbits, rm, True)


def itof(n, m, st, a, fbits, rm, unsigned):
    """FixedToFP: N-bit (un)signed fixed point to M-bit float."""
    rounding = _mode(rm, st)
    i = a if unsigned or not a >> (n - 1) else a - (1 << n)
    value = Fraction(i, 1 << fbits)
    if value == 0:
        return fp_zero(m, 0)
    return fp_round(value, m, st, rounding)


def sitof(n, m, st, a, fbits, rm):
    return itof(n, m, st, a, fbits, rm, False)


def uitof(n, m, st, a, fbits, rm):
    return itof(n, m, st, a, fbits, rm, True)


def _frint(n, st, a, rm, exact):
    rounding = _mode(rm, st)
    t, s, v = unpack(a, n, st)
    if _is_nan(t):
        return _process_nan(t, a, n, st)
    if t == INFINITY:
        return fp_inf(n, s)
    if t == ZERO:
        return fp_zero(n, s)
    i, error = _round_int(v, rounding)
    result = fp_zero(n, s) if i == 0 else fp_round(Fraction(i), n, st, RTZ)
    if error != 0 and exact:
        st.flags.add(INEXACT)
    return result


def frint(n, st, a, rm):
    """Round to integral value, no inexact exception."""
    return _frint(n, st, a, rm, False)


def frintx(n, st, a, rm):
    """Round to integral value, signalling inexact."""
    return _frint(n, st, a, rm, True)


# -----------------------------------------------------------------------------
# Arm-specific operations: FMULX, reciprocal estimates and steps, FRECPX,
# FRINT32/64, FJCVTZS, FMLAL (half to single), BFloat16
# -----------------------------------------------------------------------------
def _fp_const(n, value):
    """Encoding of a small positive constant (2.0, 1.5, 3.0)."""
    return fp_round(Fraction(value), n, FPUState(), RNE)


def fmulx(n, st, a, b, rm):
    """FPMulX: like fmul, but infinity * zero = +/-2.0."""
    t1, s1, _ = unpack(a, n, st)
    t2, s2, _ = unpack(b, n, st)
    if not (_is_nan(t1) or _is_nan(t2)) and \
            ((t1 == INFINITY and t2 == ZERO) or (t1 == ZERO and t2 == INFINITY)):
        return _fp_const(n, 2) | ((s1 ^ s2) << (n - 1))
    return fmul(n, st, a, b, rm)


def _step_fused(n, st, a, b, rm, const, halve):
    """FPRecipStepFused / FPRSqrtStepFused: (const - a*b) [/ 2], fused."""
    rounding = _mode(rm, st)
    a ^= 1 << (n - 1)                                 # FPNeg(op1)
    t1, s1, v1 = unpack(a, n, st)
    t2, s2, v2 = unpack(b, n, st)
    done, result = _process_nans((t1, t2), (a, b), n, st)
    if done:
        return result
    inf1, inf2, z1, z2 = t1 == INFINITY, t2 == INFINITY, t1 == ZERO, t2 == ZERO
    if (inf1 and z2) or (z1 and inf2):
        return _fp_const(n, Fraction(3, 2) if halve else 2)
    if inf1 or inf2:
        return fp_inf(n, s1 ^ s2)
    r = (const + v1 * v2) / (2 if halve else 1)
    if r == 0:
        return fp_zero(n, _exact_zero_sign(rounding))
    return fp_round(r, n, st, rounding)


def frecps(n, st, a, b, rm):
    return _step_fused(n, st, a, b, rm, 2, False)


def frsqrts(n, st, a, b, rm):
    return _step_fused(n, st, a, b, rm, 3, True)


def _recip_estimate(a):
    a = a * 2 + 1
    return ((1 << 19) // a + 1) // 2


def _rsqrt_estimate(a):
    if a < 256:
        a = a * 2 + 1
    else:
        a = ((a >> 1) << 1) + 1
        a = a * 2
    b = 512
    while a * (b + 1) * (b + 1) < 1 << 28:
        b += 1
    return (b + 1) // 2


def _fraction52(a, n):
    e, f, _ = _fmt(n)
    return (a & ((1 << f) - 1)) << (52 - f), (a >> f) & ((1 << e) - 1)


def frecpe(n, st, a):
    """FPRecipEstimate (8-bit estimate, FEAT_RPRES not used)."""
    t, sign, v = unpack(a, n, st)
    if _is_nan(t):
        return _process_nan(t, a, n, st)
    if t == INFINITY:
        return fp_zero(n, sign)
    if t == ZERO:
        st.flags.add(DIVBYZERO)
        return fp_inf(n, sign)
    lim = {16: -16, 32: -128, 64: -1024}[n]
    if abs(v) < Fraction(2) ** lim:
        rm = st.rmode
        to_inf = rm == RNE or (rm == RTP and not sign) or (rm == RTN and sign)
        st.flags.update((OVERFLOW, INEXACT))
        return fp_inf(n, sign) if to_inf else fp_max_normal(n, sign)
    big = {16: 14, 32: 126, 64: 1022}[n]
    if (st.fz16 if n == 16 else st.fz) and abs(v) >= Fraction(2) ** big:
        st.flags.add(UNDERFLOW)
        return fp_zero(n, sign)
    fraction, exp = _fraction52(a, n)
    if exp == 0:
        if not fraction >> 51 & 1:
            exp = -1
            fraction = (fraction << 2) & ((1 << 52) - 1)
        else:
            fraction = (fraction << 1) & ((1 << 52) - 1)
    scaled = (1 << 8) | (fraction >> 44)
    result_exp = {16: 29, 32: 253, 64: 2045}[n] - exp
    fraction = (_recip_estimate(scaled) & 0xFF) << 44
    if result_exp == 0:
        fraction = (1 << 51) | (fraction >> 1)
    elif result_exp == -1:
        fraction = (1 << 50) | (fraction >> 2)
        result_exp = 0
    e, f, _ = _fmt(n)
    return (sign << (n - 1)) | ((result_exp & ((1 << e) - 1)) << f) | (fraction >> (52 - f))


def frsqrte(n, st, a):
    """FPRSqrtEstimate (8-bit estimate)."""
    t, sign, v = unpack(a, n, st)
    if _is_nan(t):
        return _process_nan(t, a, n, st)
    if t == ZERO:
        st.flags.add(DIVBYZERO)
        return fp_inf(n, sign)
    if sign:
        st.flags.add(INVALID)
        return fp_default_nan(n)
    if t == INFINITY:
        return fp_zero(n, 0)
    fraction, exp = _fraction52(a, n)
    if exp == 0:
        while not fraction >> 51 & 1:
            fraction = (fraction << 1) & ((1 << 52) - 1)
            exp -= 1
        fraction = (fraction << 1) & ((1 << 52) - 1)
    if exp & 1 == 0:
        scaled = (1 << 8) | (fraction >> 44)
    else:
        scaled = (1 << 7) | (fraction >> 45)
    result_exp = ({16: 44, 32: 380, 64: 3068}[n] - exp) // 2
    est = _rsqrt_estimate(scaled) & 0xFF
    e, f, _ = _fmt(n)
    return ((result_exp & ((1 << e) - 1)) << f) | (est << (f - 8))


def frecpx(n, st, a):
    """FPRecpX: exponent reciprocal estimate."""
    e, f, _ = _fmt(n)
    t, sign, _ = unpack(a, n, st)
    if _is_nan(t):
        return _process_nan(t, a, n, st)
    exp = (a >> f) & ((1 << e) - 1)
    new = ((1 << e) - 2) if exp == 0 else (~exp & ((1 << e) - 1))
    return (sign << (n - 1)) | (new << f)


def _frint_n(n, st, a, rm, intsize):
    """FPRoundIntN (FRINT32*/FRINT64*)."""
    rounding = _mode(rm, st)
    e, f, _ = _fmt(n)
    special = (1 << (n - 1)) | ((((1 << (e - 1)) - 2 + intsize) & ((1 << e) - 1)) << f)
    t, sign, v = unpack(a, n, st)
    if _is_nan(t) or t == INFINITY:
        st.flags.add(INVALID)
        return special
    if t == ZERO:
        return fp_zero(n, sign)
    i, error = _round_int(v, rounding)
    if i > (1 << (intsize - 1)) - 1 or i < -(1 << (intsize - 1)):
        st.flags.add(INVALID)
        return special
    result = fp_zero(n, sign) if i == 0 else fp_round(Fraction(i), n, st, RTZ)
    if error != 0:
        st.flags.add(INEXACT)
    return result


def frint32(n, st, a, rm):
    return _frint_n(n, st, a, rm, 32)


def frint64(n, st, a, rm):
    return _frint_n(n, st, a, rm, 64)


def fjcvtzs(n, st, a):
    """FPToFixedJS: double to int32 (JavaScript semantics), returns (value, Z)."""
    t, sign, v = unpack(a, 64, st)
    z = 1
    if _is_nan(t):
        st.flags.add(INVALID)
        z = 0
    if t == INFINITY or _is_nan(t):
        i, error = 0, Fraction(0)
        big = t == INFINITY
    else:
        i = v.numerator // v.denominator
        error = v - i
        if error != 0 and i < 0:
            i += 1
        big = False
    if big or i < -(1 << 31) or i > (1 << 31) - 1:
        st.flags.add(INVALID)
        z = 0
    elif error != 0:
        st.flags.add(INEXACT)
        z = 0
    elif sign and v == 0:
        z = 0
    elif not sign and v == 0 and a & ((1 << 52) - 1):
        z = 0
    return [i & 0xFFFFFFFF, z]


def fmuladdh(n, st, addend, a, b, rm):
    """FPMulAddH: single addend + half * half with one rounding (FEAT_FHM)."""
    rounding = _mode(rm, st)
    ta, sa, va = unpack(addend, 32, st)
    t1, s1, v1 = unpack(a, 16, st)
    t2, s2, v2 = unpack(b, 16, st)
    inf1, inf2, z1, z2 = t1 == INFINITY, t2 == INFINITY, t1 == ZERO, t2 == ZERO
    done, result = False, 0
    for kind in (SNAN, QNAN):
        for t, op, w in ((ta, addend, 32), (t1, a, 16), (t2, b, 16)):
            if not done and t == kind:
                r = _process_nan(t, op, w, st)
                result = r if w == 32 else fcvtf(16, 32, FPUState(dn=st.dn), r, RNE)
                done = True
    if ta == QNAN and ((inf1 and z2) or (z1 and inf2)):
        st.flags.add(INVALID)
        result = fp_default_nan(32)
    if done:
        return result
    infa, zeroa = ta == INFINITY, ta == ZERO
    sp, infp, zerop = s1 ^ s2, inf1 or inf2, z1 or z2
    if (inf1 and z2) or (z1 and inf2) or (infa and infp and sa != sp):
        st.flags.add(INVALID)
        return fp_default_nan(32)
    if (infa and sa == 0) or (infp and sp == 0):
        return fp_inf(32, 0)
    if infa or infp:
        return fp_inf(32, 1)
    if zeroa and zerop and sa == sp:
        return fp_zero(32, sa)
    r = va + v1 * v2
    if r == 0:
        return fp_zero(32, _exact_zero_sign(rounding))
    return fp_round(r, 32, st, rounding)


def fcvtbf(n, m, st, a, rm):
    """FPConvertBF: single to BFloat16."""
    rounding = _mode(rm, st)
    t, s, v = unpack(a, 32, st)
    if _is_nan(t):
        if t == SNAN:
            st.flags.add(INVALID)
        r = fp_default_nan(32) if st.dn else a | (1 << 22)
    elif t == INFINITY:
        r = fp_inf(32, s)
    elif t == ZERO:
        r = fp_zero(32, s)
    else:
        r = fp_round(v, 32, st, rounding, bf16=True)
    return r >> 16


def _bf_unpack(bits, n):
    """BFUnpack: denormals flush to zero, every NaN is quiet."""
    sign = bits >> (n - 1)
    exp = (bits >> (n - 9)) & 0xFF
    frac = (bits & ((1 << (n - 9)) - 1)) << (32 - n)
    if exp == 0:
        return ZERO, sign, Fraction(0)
    if exp == 0xFF:
        return (INFINITY, sign, INF) if frac == 0 else (QNAN, sign, Fraction(0))
    v = (1 + Fraction(frac, 1 << 23)) * Fraction(2) ** (exp - 127)
    return NONZERO, sign, -v if sign else v


def _bf_round(value):
    """BFRound: round to odd into single precision, flush tiny values."""
    sign = int(value < 0)
    mant = -value if sign else value
    exponent = _ilog2(mant)
    if exponent < -126:
        return fp_zero(32, sign)
    mant = mant / Fraction(2) ** exponent
    scaled = mant * (1 << 23)
    int_mant = scaled.numerator // scaled.denominator
    if scaled != int_mant and not int_mant & 1:
        int_mant += 1
    biased = exponent + 127
    if biased >= 255:
        return fp_inf(32, sign)
    return (sign << 31) | (biased << 23) | (int_mant & ((1 << 23) - 1))


def _bf_mulh(a, b):
    t1, s1, v1 = _bf_unpack(a, 16)
    t2, s2, v2 = _bf_unpack(b, 16)
    if QNAN in (t1, t2):
        return fp_default_nan(32)
    if (t1 == INFINITY and t2 == ZERO) or (t1 == ZERO and t2 == INFINITY):
        return fp_default_nan(32)
    if INFINITY in (t1, t2):
        return fp_inf(32, s1 ^ s2)
    if ZERO in (t1, t2):
        return fp_zero(32, s1 ^ s2)
    return _bf_round(v1 * v2)


def _bf_add(a, b):
    t1, s1, v1 = _bf_unpack(a, 32)
    t2, s2, v2 = _bf_unpack(b, 32)
    if QNAN in (t1, t2):
        return fp_default_nan(32)
    if t1 == INFINITY and t2 == INFINITY and s1 != s2:
        return fp_default_nan(32)
    if (t1 == INFINITY and s1 == 0) or (t2 == INFINITY and s2 == 0):
        return fp_inf(32, 0)
    if INFINITY in (t1, t2):
        return fp_inf(32, 1)
    if t1 == ZERO and t2 == ZERO and s1 == s2:
        return fp_zero(32, s1)
    r = v1 + v2
    return fp_zero(32, 0) if r == 0 else _bf_round(r)


def bfdotadd(n, st, addend, a1, b1, a2, b2):
    """BFDotAdd (FEAT_EBF16 not implemented): no exceptions, default NaNs,
    round to odd, flush to zero; FPCR is not used."""
    return _bf_add(addend, _bf_add(_bf_mulh(a1, a2), _bf_mulh(b1, b2)))


# -----------------------------------------------------------------------------
# Registry: base -> (signature(N[, M]) -> (inputs, outputs), evaluate)
# -----------------------------------------------------------------------------
@dataclass
class FloatBase:
    arity: str                    # 'N' (same format) or 'NM' (conversion N -> M)
    signature: Callable
    fn: Callable


def _same(ins):
    return lambda n: ([n if w == 'N' else w for w in ins], [n])


BASES: Dict[str, FloatBase] = {
    'fadd': FloatBase('N', _same(['N', 'N', 3]), fadd),
    'fsub': FloatBase('N', _same(['N', 'N', 3]), fsub),
    'fmul': FloatBase('N', _same(['N', 'N', 3]), fmul),
    'fdiv': FloatBase('N', _same(['N', 'N', 3]), fdiv),
    'fmuladd': FloatBase('N', _same(['N', 'N', 'N', 3]), fmuladd),
    'fsqrt': FloatBase('N', _same(['N', 3]), fsqrt),
    'fmax': FloatBase('N', _same(['N', 'N']), fmax),
    'fmin': FloatBase('N', _same(['N', 'N']), fmin),
    'fmaxnm': FloatBase('N', _same(['N', 'N']), fmaxnm),
    'fminnm': FloatBase('N', _same(['N', 'N']), fminnm),
    'fcmpq': FloatBase('N', lambda n: ([n, n], [2]), fcmpq),
    'fcmps': FloatBase('N', lambda n: ([n, n], [2]), fcmps),
    'frint': FloatBase('N', _same(['N', 3]), frint),
    'frintx': FloatBase('N', _same(['N', 3]), frintx),
    'fcvtf': FloatBase('NM', lambda n, m: ([n, 3], [m]), fcvtf),
    'ftosi': FloatBase('NM', lambda n, m: ([n, 8, 3], [m]), ftosi),
    'ftoui': FloatBase('NM', lambda n, m: ([n, 8, 3], [m]), ftoui),
    'sitof': FloatBase('NM', lambda n, m: ([n, 8, 3], [m]), sitof),
    'uitof': FloatBase('NM', lambda n, m: ([n, 8, 3], [m]), uitof),
    'fmulx': FloatBase('N', _same(['N', 'N', 3]), fmulx),
    'frecps': FloatBase('N', _same(['N', 'N', 3]), frecps),
    'frsqrts': FloatBase('N', _same(['N', 'N', 3]), frsqrts),
    'frecpe': FloatBase('N', _same(['N']), frecpe),
    'frsqrte': FloatBase('N', _same(['N']), frsqrte),
    'frecpx': FloatBase('N', _same(['N']), frecpx),
    'frint32': FloatBase('N', _same(['N', 3]), frint32),
    'frint64': FloatBase('N', _same(['N', 3]), frint64),
    'fjcvtzs': FloatBase('N', lambda n: ([n], [32, 1]), fjcvtzs),
    'fmuladdh': FloatBase('N', lambda n: ([32, 16, 16, 3], [32]), fmuladdh),
    'fcvtbf': FloatBase('NM', lambda n, m: ([n, 3], [m]), fcvtbf),
    'bfdotadd': FloatBase('N', lambda n: ([32, 16, 16, 16, 16], [32]), bfdotadd),
}

FLOAT_WIDTHS = (16, 32, 64)
INT_WIDTHS = (16, 32, 64)


def make(base: str, n: int, m: Optional[int] = None) -> FloatOperation:
    """Standard float operation `<base>_<N>` or `<base>_<N>_to_<M>`."""
    b = BASES[base]
    if b.arity == 'N':
        assert m is None and n in FLOAT_WIDTHS
        ins, outs = b.signature(n)
        name = f'{base}_{n}'
    else:
        assert m is not None
        ins, outs = b.signature(n, m)
        name = f'{base}_{n}_to_{m}'
    return FloatOperation(name, [], ins, outs, base)


def parse(fop: FloatOperation) -> Tuple[FloatBase, int, Optional[int]]:
    """Validate a float operation against its base; returns (base, N, M)."""
    b = BASES[fop.semantic_base]
    m = re.fullmatch(rf'{fop.semantic_base}_(\d+)(?:_to_(\d+))?', fop.name)
    assert m, f'unexpected float operation name {fop.name}'
    n, mm = int(m.group(1)), (int(m.group(2)) if m.group(2) else None)
    ins, outs = b.signature(n) if b.arity == 'N' else b.signature(n, mm)
    assert (fop.inputs, fop.outputs) == (ins, outs), f'bad signature of {fop.name}'
    return b, n, mm


def evaluate(fop: FloatOperation, args: List[int], st: FPUState) -> List[int]:
    b, n, m = parse(fop)
    r = b.fn(n, st, *args) if b.arity == 'N' else b.fn(n, m, st, *args)
    return r if isinstance(r, list) else [r]


# -----------------------------------------------------------------------------
# Binding of the FPU state to architecture registers
# -----------------------------------------------------------------------------
_FIELD = re.compile(r'fpu\.(rmode|fz|fz16|dn|flag\.(\w+))@(\d+)(?:\+(\d+))?')


@dataclass
class FPUBinding:
    """FPU state stored in registers marked with attributes:

    * control register: `fpu.control`, fields `fpu.rmode@<lsb>+2`,
      `fpu.fz@<bit>`, `fpu.fz16@<bit>`, `fpu.dn@<bit>`
    * status register: `fpu.status`, flags `fpu.flag.<name>@<bit>` for the
      names in `FLAGS`
    """
    control: Tuple[str, int]                       # (register file, index)
    status: Tuple[str, int]
    fields: Dict[str, Tuple[int, int]]             # name -> (lsb, width)
    flag_bits: Dict[str, int]

    @classmethod
    def from_arch(cls, arch: Arch) -> Optional['FPUBinding']:
        control = status = None
        fields, flag_bits = {}, {}
        for rf in arch.register_files:
            for i, reg in enumerate(rf.regs):
                if 'fpu.control' in reg.attributes:
                    control = (rf.name, i)
                if 'fpu.status' in reg.attributes:
                    status = (rf.name, i)
                for attr in reg.attributes:
                    m = _FIELD.fullmatch(attr)
                    if not m:
                        continue
                    lsb, width = int(m.group(3)), int(m.group(4) or 1)
                    if m.group(2):
                        assert m.group(2) in FLAGS, attr
                        flag_bits[m.group(2)] = lsb
                    else:
                        fields[m.group(1)] = (lsb, width)
        if control is None:
            return None
        return cls(control, status, fields, flag_bits)

    def state(self, control_value: int) -> FPUState:
        def get(name, default=0):
            if name not in self.fields:
                return default
            lsb, width = self.fields[name]
            return (control_value >> lsb) & ((1 << width) - 1)
        return FPUState(rmode=get('rmode'), fz=bool(get('fz')), fz16=bool(get('fz16')),
                        dn=bool(get('dn')))

    def status_bits(self, flags: Set[str]) -> int:
        return sum(1 << self.flag_bits[f] for f in flags if f in self.flag_bits)
