"""Hand-written LIRA semantics of A64 base (integer) instructions.

Each handler translates the ASL `decode` + `execute` pseudocode of one XML
file (all encodings of that file share it, parametrized by fixed fields such as
`sf`). Operands are raw encoding fields; `F(name)` returns the operand value or
a constant if the encoding fixes that field.

`undef` handlers return a 1-bit value that is set when the ASL decode ends in
`EndOfDecode(Decode_UNDEF)`; they become the encoding constraints.
"""
from typing import Callable, Dict, List, Optional, Tuple

from .lib import S
from .xmlspec import Encoding

Handler = Callable[[S, Encoding, Callable], None]
SEM: Dict[str, Tuple[Handler, Optional[Handler]]] = {}
# file -> [(suffix, {field: value})]: split an XML encoding into several
# LIRA instructions with these fields fixed (see xmlspec.specialize)
SPECS: Dict[str, List[Tuple[str, Dict[str, int]]]] = {}
# Encodings of covered files that belong to features outside the modeled set
EXCLUDE: set = set()
# Load/store files whose accesses are ordered (alignment-checked)
LDST_ORDERED: set = set()


def sem(*files, undef=None, spec=None):
    def deco(fn):
        for f in files:
            assert f not in SEM, f
            SEM[f] = (fn, undef)
            if spec:
                SPECS[f] = spec
        return fn
    return deco


def ds(e: Encoding) -> int:
    return 32 << e.fixed('sf')


def awc(s: S, x, y, sub: int):
    """AddWithCarry(x, y, '0') or AddWithCarry(x, NOT(y), '1')."""
    if sub:
        return s.add_with_carry(x, s.not_(y), s.c(1, 1))
    return s.add_with_carry(x, y, s.c(0, 1))


def logic_flags(s: S, r):
    """result[N-1]::IsZeroBit(result)::'00'"""
    return s.concat(s.bits(r, r.width - 1, 1), s.eqc(r, 0), s.c(0, 2))


# -----------------------------------------------------------------------------
# Add/subtract
# -----------------------------------------------------------------------------
@sem('add_addsub_imm', 'adds_addsub_imm', 'sub_addsub_imm', 'subs_addsub_imm')
def _addsub_imm(s: S, e: Encoding, F):
    n = ds(e)
    op1 = s.xsp_read(F('Rn'), n)
    imm = s.zext(F('imm12'), n)
    imm = s.select(F('sh'), s.lsl(imm, s.c(12, n)), imm)
    res, nzcv = awc(s, op1, imm, e.fixed('op'))
    if e.fixed('S'):
        s.x_write(F('Rd'), res)
        s.flags_write(nzcv)
    else:
        s.xsp_write(F('Rd'), res)


def _undef_shift_amount(s: S, e: Encoding, F):
    if ds(e) == 32:
        return s.bits(F('imm6'), 5, 1)       # sf == '0' && imm6[5] == '1'
    return None


def _undef_addsub_shift(s: S, e: Encoding, F):
    u = s.eqc(F('shift'), 0b11)
    amount = _undef_shift_amount(s, e, F)
    return u if amount is None else s.orr(u, amount)


@sem('add_addsub_shift', 'adds_addsub_shift', 'sub_addsub_shift', 'subs_addsub_shift',
     undef=_undef_addsub_shift)
def _addsub_shift(s: S, e: Encoding, F):
    n = ds(e)
    op1 = s.x_read(F('Rn'), n)
    op2 = s.shift_reg(s.x_read(F('Rm'), n), F('shift'), s.zext(F('imm6'), n))
    res, nzcv = awc(s, op1, op2, e.fixed('op'))
    s.x_write(F('Rd'), res)
    if e.fixed('S'):
        s.flags_write(nzcv)


def _undef_addsub_ext(s: S, e: Encoding, F):
    return s.ugt(F('imm3'), s.c(4, 3))       # imm3 IN {'101', '110', '111'}


@sem('add_addsub_ext', 'adds_addsub_ext', 'sub_addsub_ext', 'subs_addsub_ext',
     undef=_undef_addsub_ext)
def _addsub_ext(s: S, e: Encoding, F):
    n = ds(e)
    op1 = s.xsp_read(F('Rn'), n)
    op2 = s.extend_reg(s.x_read(F('Rm'), n), F('option'), F('imm3'))
    res, nzcv = awc(s, op1, op2, e.fixed('op'))
    if e.fixed('S'):
        s.x_write(F('Rd'), res)
        s.flags_write(nzcv)
    else:
        s.xsp_write(F('Rd'), res)


@sem('adc', 'adcs', 'sbc', 'sbcs')
def _addsub_carry(s: S, e: Encoding, F):
    n = ds(e)
    op1 = s.x_read(F('Rn'), n)
    op2 = s.x_read(F('Rm'), n)
    if e.fixed('op'):
        op2 = s.not_(op2)
    res, nzcv = s.add_with_carry(op1, op2, s.carry())
    s.x_write(F('Rd'), res)
    if e.fixed('S'):
        s.flags_write(nzcv)


# -----------------------------------------------------------------------------
# Logical
# -----------------------------------------------------------------------------
def _undef_log_imm(s: S, e: Encoding, F):
    return s.not_(s.logic_imm_valid(F('N'), F('imms')))


@sem('and_log_imm', 'orr_log_imm', 'eor_log_imm', 'ands_log_imm', undef=_undef_log_imm)
def _log_imm(s: S, e: Encoding, F):
    n = ds(e)
    imm = s.decode_bit_masks(F('N'), F('imms'), F('immr'), n)[0]
    op1 = s.x_read(F('Rn'), n)
    opc = e.fixed('opc')
    res = [s.and_, s.orr, s.xor, s.and_][opc](op1, imm)
    if opc == 0b11:
        s.x_write(F('Rd'), res)
        s.flags_write(logic_flags(s, res))
    else:
        s.xsp_write(F('Rd'), res)


@sem('and_log_shift', 'bic_log_shift', 'orr_log_shift', 'orn_log_shift',
     'eor_log_shift', 'eon', 'ands_log_shift', 'bics', undef=_undef_shift_amount)
def _log_shift(s: S, e: Encoding, F):
    n = ds(e)
    op1 = s.x_read(F('Rn'), n)
    op2 = s.shift_reg(s.x_read(F('Rm'), n), F('shift'), s.zext(F('imm6'), n))
    if e.fixed('N'):
        op2 = s.not_(op2)
    opc = e.fixed('opc')
    res = [s.and_, s.orr, s.xor, s.and_][opc](op1, op2)
    s.x_write(F('Rd'), res)
    if opc == 0b11:
        s.flags_write(logic_flags(s, res))


# -----------------------------------------------------------------------------
# Move wide, PC-relative addressing
# -----------------------------------------------------------------------------
@sem('movz', 'movn', 'movk')
def _movewide(s: S, e: Encoding, F):
    n = ds(e)
    pos = s.lsl(s.zext(F('hw'), n), s.c(4, n))
    imm = s.lsl(s.zext(F('imm16'), n), pos)
    opc = e.fixed('opc')
    if opc == 0b00:                                        # MOVN
        res = s.not_(imm)
    elif opc == 0b10:                                      # MOVZ
        res = imm
    else:                                                  # MOVK
        keep = s.not_(s.lsl(s.c(0xFFFF, n), pos))
        res = s.orr(s.and_(s.x_read(F('Rd'), n), keep), imm)
    s.x_write(F('Rd'), res)


@sem('adr', 'adrp')
def _adr(s: S, e: Encoding, F):
    pc = s.pc()
    if e.fixed('op'):                                      # ADRP
        imm = s.sext(s.concat(F('immhi'), F('immlo'), s.c(0, 12)), 64)
        base = s.and_(pc, s.c(~0xFFF, 64))
    else:
        imm = s.sext(s.concat(F('immhi'), F('immlo')), 64)
        base = pc
    s.x_write(F('Rd'), s.add(base, imm))


# -----------------------------------------------------------------------------
# Bitfield, extract
# -----------------------------------------------------------------------------
def _undef_bitfield(s: S, e: Encoding, F):
    # sf == '1' && N != '1', sf == '0' && N != '0' are fixed by the encodings
    if ds(e) == 32:
        return s.orr(s.bits(F('immr'), 5, 1), s.bits(F('imms'), 5, 1))
    return None


@sem('sbfm', 'bfm', 'ubfm', undef=_undef_bitfield)
def _bitfield(s: S, e: Encoding, F):
    n = ds(e)
    wmask, tmask = s.decode_bit_masks(F('N'), F('imms'), F('immr'), n)
    src = s.x_read(F('Rn'), n)
    rotated = s.ror(src, s.zext(F('immr'), n))
    opc = e.fixed('opc')
    if opc == 0b01:                                        # BFM
        dst = s.x_read(F('Rd'), n)
        bot = s.orr(s.and_(dst, s.not_(wmask)), s.and_(rotated, wmask))
        res = s.orr(s.and_(dst, s.not_(tmask)), s.and_(bot, tmask))
    else:
        bot = s.and_(rotated, wmask)
        if opc == 0b00:                                    # SBFM
            top = s.replicate1(s.bit_at(src, F('imms')), n)
            res = s.orr(s.and_(top, s.not_(tmask)), s.and_(bot, tmask))
        else:                                              # UBFM
            res = s.and_(bot, tmask)
    s.x_write(F('Rd'), res)


@sem('extr')
def _extr(s: S, e: Encoding, F):
    n = ds(e)
    op1 = s.x_read(F('Rn'), n)
    op2 = s.x_read(F('Rm'), n)
    lsb = s.zext(F('imms'), n)
    back = s.and_(s.sub(s.c(n, n), lsb), s.c(n - 1, n))
    res = s.select(s.eqc(lsb, 0), op2, s.orr(s.lsr(op2, lsb), s.lsl(op1, back)))
    s.x_write(F('Rd'), res)


# -----------------------------------------------------------------------------
# Data processing: 2 and 3 sources
# -----------------------------------------------------------------------------
@sem('lslv', 'lsrv', 'asrv', 'rorv')
def _shiftv(s: S, e: Encoding, F):
    n = ds(e)
    amount = s.and_(s.x_read(F('Rm'), n), s.c(n - 1, n))  # UInt(operand2) MOD datasize
    fn = [s.lsl, s.lsr, s.asr, s.ror][e.fixed('op2')]
    s.x_write(F('Rd'), fn(s.x_read(F('Rn'), n), amount))


@sem('udiv', 'sdiv')
def _div(s: S, e: Encoding, F):
    n = ds(e)
    fn = s.div_s if e.fixed('o1') else s.div_u             # x / 0 = 0
    s.x_write(F('Rd'), fn(s.x_read(F('Rn'), n), s.x_read(F('Rm'), n), s.c(0, n)))


@sem('madd', 'msub')
def _madd(s: S, e: Encoding, F):
    n = ds(e)
    prod = s.mul(s.x_read(F('Rn'), n), s.x_read(F('Rm'), n))
    acc = s.x_read(F('Ra'), n)
    s.x_write(F('Rd'), s.sub(acc, prod) if e.fixed('o0') else s.add(acc, prod))


@sem('smaddl', 'smsubl', 'umaddl', 'umsubl')
def _maddl(s: S, e: Encoding, F):
    ext = s.zext if e.fixed('U') else s.sext
    prod = s.mul(ext(s.x_read(F('Rn'), 32), 64), ext(s.x_read(F('Rm'), 32), 64))
    acc = s.x_read(F('Ra'), 64)
    s.x_write(F('Rd'), s.sub(acc, prod) if e.fixed('o0') else s.add(acc, prod))


@sem('smulh', 'umulh')
def _mulh(s: S, e: Encoding, F):
    ext = s.zext if e.fixed('U') else s.sext
    prod = s.mul(ext(s.x_read(F('Rn'), 64), 128), ext(s.x_read(F('Rm'), 64), 128))
    s.x_write(F('Rd'), s.bits(prod, 64, 64))


# -----------------------------------------------------------------------------
# Data processing: 1 source
# -----------------------------------------------------------------------------
@sem('rbit_int')
def _rbit(s: S, e: Encoding, F):
    n = ds(e)
    s.x_write(F('Rd'), s.reverse(s.x_read(F('Rn'), n)))


@sem('rev16_int', 'rev32_int', 'rev')
def _rev(s: S, e: Encoding, F):
    n = ds(e)
    container = 8 << e.fixed('opc')
    s.x_write(F('Rd'), s.rev_bytes(s.x_read(F('Rn'), n), container))


@sem('clz_int', 'cls_int')
def _clz(s: S, e: Encoding, F):
    n = ds(e)
    x = s.x_read(F('Rn'), n)
    s.x_write(F('Rd'), s.cls(x) if e.fixed('op') else s.clz(x))


# -----------------------------------------------------------------------------
# Conditional select / compare
# -----------------------------------------------------------------------------
@sem('csel', 'csinc', 'csinv', 'csneg')
def _csel(s: S, e: Encoding, F):
    n = ds(e)
    op1 = s.x_read(F('Rn'), n)
    op2 = s.x_read(F('Rm'), n)
    if e.fixed('op'):
        op2 = s.not_(op2)
    if e.fixed('o2'):
        op2 = s.add(op2, s.c(1, n))
    s.x_write(F('Rd'), s.select(s.condition_holds(F('cond')), op1, op2))


@sem('ccmp_imm', 'ccmp_reg', 'ccmn_imm', 'ccmn_reg')
def _ccmp(s: S, e: Encoding, F):
    n = ds(e)
    op1 = s.x_read(F('Rn'), n)
    op2 = s.zext(F('imm5'), n) if 'imm5' in e.fields else s.x_read(F('Rm'), n)
    _, nzcv = awc(s, op1, op2, e.fixed('op'))
    s.flags_write(s.select(s.condition_holds(F('cond')), nzcv, F('nzcv')))


# -----------------------------------------------------------------------------
# Branches
# -----------------------------------------------------------------------------
def _offset(s: S, imm, zeros: int = 2):
    return s.sext(s.concat(imm, s.c(0, zeros)), 64)


@sem('b_uncond', 'bl')
def _b(s: S, e: Encoding, F):
    pc = s.pc()
    if e.fixed('op'):                                      # BL
        s.x_write_n(30, s.add(pc, s.c(4, 64)))
    s.branch(s.add(pc, _offset(s, F('imm26'))))


@sem('b_cond')
def _bcond(s: S, e: Encoding, F):
    target = s.add(s.pc(), _offset(s, F('imm19')))
    s.branch_if(s.condition_holds(F('cond')), target)


@sem('cbz', 'cbnz')
def _cbz(s: S, e: Encoding, F):
    n = ds(e)
    target = s.add(s.pc(), _offset(s, F('imm19')))
    zero = s.eqc(s.x_read(F('Rt'), n), 0)
    s.branch_if(s.not_(zero) if e.fixed('op') else zero, target)


@sem('tbz', 'tbnz')
def _tbz(s: S, e: Encoding, F):
    target = s.add(s.pc(), _offset(s, F('imm14')))
    bit = s.bit_at(s.x_read(F('Rt'), 64), s.concat(F('b5'), F('b40')))
    s.branch_if(bit if e.fixed('op') else s.not_(bit), target)


@sem('br', 'blr', 'ret')
def _br(s: S, e: Encoding, F):
    target = s.x_read(F('Rn'), 64)
    if e.fixed('op') == 0b01:                              # BLR
        s.x_write_n(30, s.add(s.pc(), s.c(4, 64)))
    s.branch(target)


# -----------------------------------------------------------------------------
# Loads and stores
# -----------------------------------------------------------------------------
# file -> (memory access bits or None for the `size` field, signed, is_load)
LDST = {
    'ldr_imm_gen': (None, False, True), 'str_imm_gen': (None, False, False),
    'ldr_reg_gen': (None, False, True), 'str_reg_gen': (None, False, False),
    'ldur_gen': (None, False, True), 'stur_gen': (None, False, False),
    'ldrb_imm': (8, False, True), 'strb_imm': (8, False, False),
    'ldrb_reg': (8, False, True), 'strb_reg': (8, False, False),
    'ldurb': (8, False, True), 'sturb': (8, False, False),
    'ldrh_imm': (16, False, True), 'strh_imm': (16, False, False),
    'ldrh_reg': (16, False, True), 'strh_reg': (16, False, False),
    'ldurh': (16, False, True), 'sturh': (16, False, False),
    'ldrsb_imm': (8, True, True), 'ldrsb_reg': (8, True, True), 'ldursb': (8, True, True),
    'ldrsh_imm': (16, True, True), 'ldrsh_reg': (16, True, True), 'ldursh': (16, True, True),
    'ldrsw_imm': (32, True, True), 'ldrsw_reg': (32, True, True), 'ldursw': (32, True, True),
}


def _undef_ldst_reg(s: S, e: Encoding, F):
    return s.not_(s.bits(F('option'), 1, 1))               # option[1] == '0'


def _ldst_undef(s: S, e: Encoding, F):
    return _undef_ldst_reg(s, e, F) if e.name.endswith('_ldst_regoff') else None


def _ldst_params(e: Encoding):
    bits, signed, load = LDST[e.file]
    if bits is None:
        bits = 8 << e.fixed('size')
    if signed:
        regsize = 32 if bits < 32 and e.fixed('opc') & 1 else 64   # 64 >> UInt(opc[0])
    else:
        regsize = 64 if bits == 64 else 32
    return bits, signed, load, regsize


@sem(*LDST, undef=_ldst_undef)
def _ldst(s: S, e: Encoding, F):
    bits, signed, load, regsize = _ldst_params(e)
    scale = bits.bit_length() - 4                          # log2(bits / 8)
    mode = e.name.rsplit('_', 1)[1]
    if mode in ('immpost', 'immpre', 'unscaled', 'unpriv'):
        offset = s.sext(F('imm9'), 64)
    elif mode == 'pos':
        offset = s.lsl(s.zext(F('imm12'), 64), s.c(scale, 64))
    else:                                                  # regoff
        shift = s.select(F('S'), s.c(scale, 3), s.c(0, 3))
        offset = s.extend_reg(s.x_read(F('Rm'), 64), F('option'), shift)
    post, wback = mode == 'immpost', mode in ('immpost', 'immpre')

    base = s.xsp_read(F('Rn'), 64)
    address = base if post else s.add(base, offset)
    if e.file in LDST_ORDERED:
        s.check_alignment(address, bits)
    if load:
        data = s.mem_read(address, bits)
        s.x_write(F('Rt'), (s.sext if signed else s.zext)(data, regsize))
    else:
        s.mem_write(address, s.x_read(F('Rt'), bits))
    if wback:
        s.xsp_write(F('Rn'), s.add(address, offset) if post else address)


@sem('ldp_gen', 'stp_gen', 'ldpsw')
def _ldstp(s: S, e: Encoding, F):
    signed = e.file == 'ldpsw'
    scale = 2 if signed else 2 + (e.fixed('opc') >> 1)
    n = 8 << scale
    offset = s.lsl(s.sext(F('imm7'), 64), s.c(scale, 64))
    mode = e.name.rsplit('_', 1)[1]
    post, wback = mode == 'post', mode in ('post', 'pre')

    base = s.xsp_read(F('Rn'), 64)
    address = base if post else s.add(base, offset)
    if e.fixed('L'):
        data = s.mem_read(address, 2 * n)                 # little-endian
        d1, d2 = s.trunc(data, n), s.bits(data, n, n)
        if signed:
            d1, d2 = s.sext(d1, 64), s.sext(d2, 64)
        s.x_write(F('Rt'), d1)
        s.x_write(F('Rt2'), d2)
    else:
        s.mem_write(address, s.concat(s.x_read(F('Rt2'), n), s.x_read(F('Rt'), n)))
    if wback:
        s.xsp_write(F('Rn'), s.add(address, offset) if post else address)


@sem('ldr_lit_gen', 'ldrsw_lit')
def _ldr_lit(s: S, e: Encoding, F):
    address = s.add(s.pc(), _offset(s, F('imm19')))
    if e.file == 'ldrsw_lit':
        s.x_write(F('Rt'), s.sext(s.mem_read(address, 32), 64))
    else:
        s.x_write(F('Rt'), s.mem_read(address, 32 << (e.fixed('opc') & 1)))


# -----------------------------------------------------------------------------
# System
# -----------------------------------------------------------------------------
@sem('nop')
def _nop(s: S, e: Encoding, F):
    pass


@sem('svc')
def _svc(s: S, e: Encoding, F):
    s.env(s.ctx.env_svc, [F('imm16')])


from . import insns_fp, insns_simd, insns_simd2, insns_v8  # noqa: E402,F401  (register handlers)

FILES = list(SEM)
