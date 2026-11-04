from enum import Enum
from typing import ClassVar, List, Tuple

from .arch import Attribute, FloatOperation


class TypeCheckError(Exception):
    pass


class BaseFop(str, Enum):
    """Standard float operation bases, synchronized with IEEE 754 binary
    interchange formats (binary16/32/64). Every base names a fixed operation
    family; the operand and result widths select a concrete member.

    Architecture specific operations (FRECPS, FJCVTZS, ...) are intentionally
    NOT bases: converters express them through snippets over the bases below.
    """
    FADD = "fadd"
    FSUB = "fsub"
    FMUL = "fmul"
    FDIV = "fdiv"
    FSQRT = "fsqrt"
    FMULADD = "fmuladd"
    FMAX = "fmax"
    FMIN = "fmin"
    FMAXNM = "fmaxnm"
    FMINNM = "fminnm"
    FCMPQ = "fcmpq"
    FCMPS = "fcmps"
    FRINT = "frint"
    FRINTX = "frintx"
    FCVTF = "fcvtf"
    FTOSI = "ftosi"
    FTOUI = "ftoui"
    SITOF = "sitof"
    UITOF = "uitof"


# IEEE 754 binary interchange format widths supported by the standard bases.
FLOAT_WIDTHS = (16, 32, 64)


class FopModifier(str, Enum):
    """Modifiers of a base, part of the float operation contract. They appear
    in the name (`<base>_<N>[_to_<M>]_<modifier>...`, in the order below) and
    as an attribute (`fpu.<modifier>`).

    `default_nan` computes as if the default-NaN control were set,
    `no_flags` leaves the exception flags unchanged.
    """
    DEFAULT_NAN = "default_nan"
    NO_FLAGS = "no_flags"


def _check_width(value: int, name: str):
    if value not in FLOAT_WIDTHS:
        raise TypeCheckError(f"{name} must be one of {FLOAT_WIDTHS}, got {value}")


def _check_rm(value: int, name: str):
    if value != 3:
        raise TypeCheckError(f"{name} must be 3 (rounding mode), got {value}")


def _check_fbits(value: int, name: str):
    if value != 8:
        raise TypeCheckError(f"{name} must be 8 (fbits), got {value}")


def _resolve_modifiers(modifiers) -> Tuple[str, List[Attribute]]:
    """Validate `modifiers` (FopModifier values); returns the name suffix and
    the `fpu.<modifier>` attributes in the canonical FopModifier order."""
    if any(not isinstance(x, FopModifier) for x in modifiers):
        raise TypeCheckError(f"modifiers must be FopModifier, got {tuple(modifiers)}")
    if len(set(modifiers)) != len(modifiers):
        raise TypeCheckError(f"duplicate modifiers {tuple(modifiers)}")
    mods = [x for x in FopModifier if x in modifiers]
    suffix = ''.join(f'_{x.value}' for x in mods)
    attrs = [Attribute(f'fpu.{x.value}', '') for x in mods]
    return suffix, attrs


class FpUnaryFop(FloatOperation):
    """[N, 3] -> [N]"""

    def __init__(self, bits: int, modifiers=()):
        suffix, attrs = _resolve_modifiers(modifiers)
        super().__init__(
            name=f"{self.fop_base.value}_{bits}{suffix}",
            attributes=attrs,
            inputs=[bits, 3],
            outputs=[bits],
            semantic_base=self.fop_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, fop: FloatOperation) -> "FpUnaryFop":
        return cls(fop.inputs[0])._restore_from(fop)

    def _check_signature(self):
        _check_width(self.inputs[0], "float width")
        _check_rm(self.inputs[1], "rm width")
        if self.outputs[0] != self.inputs[0]:
            raise TypeCheckError(
                f"FpUnaryFop: input {self.inputs[0]} != output {self.outputs[0]}"
            )


class FpBinaryFop(FloatOperation):
    """[N, N, 3] -> [N]"""

    def __init__(self, bits: int, modifiers=()):
        suffix, attrs = _resolve_modifiers(modifiers)
        super().__init__(
            name=f"{self.fop_base.value}_{bits}{suffix}",
            attributes=attrs,
            inputs=[bits, bits, 3],
            outputs=[bits],
            semantic_base=self.fop_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, fop: FloatOperation) -> "FpBinaryFop":
        return cls(fop.inputs[0])._restore_from(fop)

    def _check_signature(self):
        _check_width(self.inputs[0], "input[0]")
        _check_width(self.inputs[1], "input[1]")
        _check_rm(self.inputs[2], "rm width")
        if not (self.inputs[0] == self.inputs[1] == self.outputs[0]):
            raise TypeCheckError(
                f"FpBinaryFop: inputs {self.inputs} != output {self.outputs[0]}"
            )


class FpTernaryFop(FloatOperation):
    """[N, N, N, 3] -> [N]"""

    def __init__(self, bits: int, modifiers=()):
        suffix, attrs = _resolve_modifiers(modifiers)
        super().__init__(
            name=f"{self.fop_base.value}_{bits}{suffix}",
            attributes=attrs,
            inputs=[bits, bits, bits, 3],
            outputs=[bits],
            semantic_base=self.fop_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, fop: FloatOperation) -> "FpTernaryFop":
        return cls(fop.inputs[0])._restore_from(fop)

    def _check_signature(self):
        for i in range(3):
            _check_width(self.inputs[i], f"input[{i}]")
        _check_rm(self.inputs[3], "rm width")
        if not (self.inputs[0] == self.inputs[1] == self.inputs[2] == self.outputs[0]):
            raise TypeCheckError(
                f"FpTernaryFop: inputs {self.inputs} != output {self.outputs[0]}"
            )


class FpMinMaxFop(FloatOperation):
    """[N, N] -> [N] (no rounding mode operand)"""

    def __init__(self, bits: int, modifiers=()):
        suffix, attrs = _resolve_modifiers(modifiers)
        super().__init__(
            name=f"{self.fop_base.value}_{bits}{suffix}",
            attributes=attrs,
            inputs=[bits, bits],
            outputs=[bits],
            semantic_base=self.fop_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, fop: FloatOperation) -> "FpMinMaxFop":
        return cls(fop.inputs[0])._restore_from(fop)

    def _check_signature(self):
        _check_width(self.inputs[0], "input[0]")
        _check_width(self.inputs[1], "input[1]")
        if not (self.inputs[0] == self.inputs[1] == self.outputs[0]):
            raise TypeCheckError(
                f"FpMinMaxFop: inputs {self.inputs} != output {self.outputs[0]}"
            )


class FpCmpFop(FloatOperation):
    """[N, N] -> [2]"""

    def __init__(self, bits: int, modifiers=()):
        suffix, attrs = _resolve_modifiers(modifiers)
        super().__init__(
            name=f"{self.fop_base.value}_{bits}{suffix}",
            attributes=attrs,
            inputs=[bits, bits],
            outputs=[2],
            semantic_base=self.fop_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, fop: FloatOperation) -> "FpCmpFop":
        return cls(fop.inputs[0])._restore_from(fop)

    def _check_signature(self):
        _check_width(self.inputs[0], "input[0]")
        _check_width(self.inputs[1], "input[1]")
        if self.outputs[0] != 2:
            raise TypeCheckError(
                f"FpCmpFop: output {self.outputs[0]} != 2"
            )


class FpConvertFop(FloatOperation):
    """[N, 3] -> [M]"""

    def __init__(self, in_bits: int, out_bits: int, modifiers=()):
        suffix, attrs = _resolve_modifiers(modifiers)
        super().__init__(
            name=f"{self.fop_base.value}_{in_bits}_to_{out_bits}{suffix}",
            attributes=attrs,
            inputs=[in_bits, 3],
            outputs=[out_bits],
            semantic_base=self.fop_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, fop: FloatOperation) -> "FpConvertFop":
        return cls(fop.inputs[0], fop.outputs[0])._restore_from(fop)

    def _check_signature(self):
        _check_width(self.inputs[0], "input width")
        _check_rm(self.inputs[1], "rm width")
        _check_width(self.outputs[0], "output width")


class FpIntFop(FloatOperation):
    """[N, 8, 3] -> [M] (fixed-point fbits operand; float <-> int)"""

    def __init__(self, in_bits: int, out_bits: int, modifiers=()):
        suffix, attrs = _resolve_modifiers(modifiers)
        super().__init__(
            name=f"{self.fop_base.value}_{in_bits}_to_{out_bits}{suffix}",
            attributes=attrs,
            inputs=[in_bits, 8, 3],
            outputs=[out_bits],
            semantic_base=self.fop_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, fop: FloatOperation) -> "FpIntFop":
        return cls(fop.inputs[0], fop.outputs[0])._restore_from(fop)

    def _check_signature(self):
        _check_width(self.inputs[0], "input width")
        _check_fbits(self.inputs[1], "fbits width")
        _check_rm(self.inputs[2], "rm width")
        _check_width(self.outputs[0], "output width")


class Fsqrt(FpUnaryFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FSQRT

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Frint(FpUnaryFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FRINT

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Frintx(FpUnaryFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FRINTX

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fadd(FpBinaryFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FADD

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fsub(FpBinaryFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FSUB

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fmul(FpBinaryFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FMUL

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fdiv(FpBinaryFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FDIV

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fmuladd(FpTernaryFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FMULADD

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fmax(FpMinMaxFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FMAX

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fmin(FpMinMaxFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FMIN

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fmaxnm(FpMinMaxFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FMAXNM

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fminnm(FpMinMaxFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FMINNM

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fcmpq(FpCmpFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FCMPQ

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fcmps(FpCmpFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FCMPS

    def __init__(self, bits: int, modifiers=()):
        super().__init__(bits, modifiers)


class Fcvtf(FpConvertFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FCVTF

    def __init__(self, in_bits: int, out_bits: int, modifiers=()):
        super().__init__(in_bits, out_bits, modifiers)


class Ftosi(FpIntFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FTOSI

    def __init__(self, in_bits: int, out_bits: int, modifiers=()):
        super().__init__(in_bits, out_bits, modifiers)


class Ftoui(FpIntFop):
    fop_base: ClassVar[BaseFop] = BaseFop.FTOUI

    def __init__(self, in_bits: int, out_bits: int, modifiers=()):
        super().__init__(in_bits, out_bits, modifiers)


class Sitof(FpIntFop):
    fop_base: ClassVar[BaseFop] = BaseFop.SITOF

    def __init__(self, in_bits: int, out_bits: int, modifiers=()):
        super().__init__(in_bits, out_bits, modifiers)


class Uitof(FpIntFop):
    fop_base: ClassVar[BaseFop] = BaseFop.UITOF

    def __init__(self, in_bits: int, out_bits: int, modifiers=()):
        super().__init__(in_bits, out_bits, modifiers)


def from_float_operation(fop: FloatOperation) -> FloatOperation:
    sb = fop.semantic_base

    if sb is None:
        return fop

    cls = FloatOperation.typed_fops.get(sb)
    if cls is None:
        assert False, f"Unexpected float operation with semantic {sb}"

    return cls.from_operation(fop)
