from enum import Enum
from typing import ClassVar

from .arch import Operation


class TypeCheckError(Exception):
    pass


class BaseOp(str, Enum):
    NOT = "not"
    NEG = "neg"
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    AND = "and"
    ORR = "orr"
    XOR = "xor"
    LSL = "lsl"
    LSR = "lsr"
    ASR = "asr"
    EQ = "eq"
    NE = "ne"
    SLT = "slt"
    SLE = "sle"
    SGT = "sgt"
    SGE = "sge"
    ULT = "ult"
    ULE = "ule"
    UGT = "ugt"
    UGE = "uge"
    EXTEND_SIGN = "extend_sign"
    EXTEND_ZERO = "extend_zero"
    EXTRACT_LOW = "extract_low"
    SELECT = "select"
    POPCNT = "popcnt"
    CTZ = "ctz"
    CLZ = "clz"
    REVERSE = "reverse"
    DIV_U = "div_u"
    DIV_S = "div_s"
    REM_U = "rem_u"
    REM_S = "rem_s"
    ROR = "ror"
    ROL = "rol"
    ADD_OVERFLOW = "add_overflow"
    SUB_OVERFLOW = "sub_overflow"


def check_bits(value: int, name: str):
    if not isinstance(value, int) or value <= 0:
        raise TypeCheckError(f"{name} must be positive integer, got {value}")


class UnaryOp(Operation):
    def __init__(self, out_bits: int):
        super().__init__(
            name=f"{self.op_base.value}_{out_bits}",
            attributes=[],
            inputs=[out_bits],
            outputs=[out_bits],
            semantic_base=self.op_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, op: Operation) -> "UnaryOp":
        return cls(op.inputs[0])._restore_from(op)

    def _check_signature(self):
        check_bits(self.inputs[0], "input width")
        check_bits(self.outputs[0], "output width")
        if self.inputs[0] != self.outputs[0]:
            raise TypeCheckError(
                f"UnaryOp: input {self.inputs[0]} != output {self.outputs[0]}"
            )


class BinaryOp(Operation):
    def __init__(self, bits: int):
        super().__init__(
            name=f"{self.op_base.value}_{bits}",
            attributes=[],
            inputs=[bits, bits],
            outputs=[bits],
            semantic_base=self.op_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, op: Operation) -> "BinaryOp":
        return cls(op.inputs[0])._restore_from(op)

    def _check_signature(self):
        for i, inp in enumerate(self.inputs):
            check_bits(inp, f"input[{i}]")
        check_bits(self.outputs[0], "output")
        if not (self.inputs[0] == self.inputs[1] == self.outputs[0]):
            raise TypeCheckError(
                f"BinaryOp: inputs {self.inputs} != output {self.outputs[0]}"
            )


class CmpOp(Operation):
    def __init__(self, bits: int, out_bits: int = 1):
        super().__init__(
            name=f"{self.op_base.value}_{bits}",
            attributes=[],
            inputs=[bits, bits],
            outputs=[out_bits],
            semantic_base=self.op_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, op: Operation) -> "CmpOp":
        return cls(op.inputs[0])._restore_from(op)

    def _check_signature(self):
        check_bits(self.inputs[0], "input[0]")
        check_bits(self.inputs[1], "input[1]")
        check_bits(self.outputs[0], "output")
        if self.inputs[0] != self.inputs[1]:
            raise TypeCheckError(
                f"CmpOp: input widths differ {self.inputs[0]} != {self.inputs[1]}"
            )


class TernaryOp(Operation):
    def __init__(self, bits: int):
        super().__init__(
            name=f"{self.op_base.value}_{bits}",
            attributes=[],
            inputs=[bits, bits, bits],
            outputs=[bits],
            semantic_base=self.op_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, op: Operation) -> "TernaryOp":
        return cls(op.inputs[0])._restore_from(op)

    def _check_signature(self):
        for i, inp in enumerate(self.inputs):
            check_bits(inp, f"input[{i}]")
        check_bits(self.outputs[0], "output")
        if not (self.inputs[0] == self.inputs[1] == self.inputs[2] == self.outputs[0]):
            raise TypeCheckError(
                f"TernaryOp: mismatched widths {self.inputs} -> {self.outputs[0]}"
            )


class ExtendOp(Operation):
    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(
            name=f"{self.op_base.value}_{in_bits}_to_{out_bits}",
            attributes=[],
            inputs=[in_bits],
            outputs=[out_bits],
            semantic_base=self.op_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, op: Operation) -> "ExtendOp":
        return cls(op.inputs[0], op.outputs[0])._restore_from(op)

    def _check_signature(self):
        check_bits(self.inputs[0], "input")
        check_bits(self.outputs[0], "output")
        if self.inputs[0] >= self.outputs[0]:
            raise TypeCheckError(
                f"ExtendOp: input {self.inputs[0]} >= output {self.outputs[0]}"
            )


class ExtractLowOp(Operation):
    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(
            name=f"{self.op_base.value}_{in_bits}_to_{out_bits}",
            attributes=[],
            inputs=[in_bits],
            outputs=[out_bits],
            semantic_base=self.op_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    @classmethod
    def from_operation(cls, op: Operation) -> "ExtractLowOp":
        return cls(op.inputs[0], op.outputs[0])._restore_from(op)

    def _check_signature(self):
        check_bits(self.inputs[0], "input")
        check_bits(self.outputs[0], "output")
        if self.outputs[0] > self.inputs[0]:
            raise TypeCheckError(
                f"ExtractLow: output {self.outputs[0]} > input {self.inputs[0]}"
            )


class Not(UnaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.NOT

    def __init__(self, bits: int):
        super().__init__(bits)


class Neg(UnaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.NEG

    def __init__(self, bits: int):
        super().__init__(bits)


class Add(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.ADD

    def __init__(self, bits: int):
        super().__init__(bits)


class Sub(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.SUB

    def __init__(self, bits: int):
        super().__init__(bits)


class Mul(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.MUL

    def __init__(self, bits: int):
        super().__init__(bits)


class And(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.AND

    def __init__(self, bits: int):
        super().__init__(bits)


class Orr(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.ORR

    def __init__(self, bits: int):
        super().__init__(bits)


class Xor(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.XOR

    def __init__(self, bits: int):
        super().__init__(bits)


class Lsl(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.LSL

    def __init__(self, bits: int):
        super().__init__(bits)


class Lsr(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.LSR

    def __init__(self, bits: int):
        super().__init__(bits)


class Asr(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.ASR

    def __init__(self, bits: int):
        super().__init__(bits)


class Eq(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.EQ

    def __init__(self, bits: int):
        super().__init__(bits)


class Ne(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.NE

    def __init__(self, bits: int):
        super().__init__(bits)


class Slt(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.SLT

    def __init__(self, bits: int):
        super().__init__(bits)


class Sle(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.SLE

    def __init__(self, bits: int):
        super().__init__(bits)


class Sgt(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.SGT

    def __init__(self, bits: int):
        super().__init__(bits)


class Sge(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.SGE

    def __init__(self, bits: int):
        super().__init__(bits)


class Ult(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.ULT

    def __init__(self, bits: int):
        super().__init__(bits)


class Ule(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.ULE

    def __init__(self, bits: int):
        super().__init__(bits)


class Ugt(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.UGT

    def __init__(self, bits: int):
        super().__init__(bits)


class Uge(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.UGE

    def __init__(self, bits: int):
        super().__init__(bits)


class ExtendSign(ExtendOp):
    op_base: ClassVar[BaseOp] = BaseOp.EXTEND_SIGN

    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits)


class ExtendZero(ExtendOp):
    op_base: ClassVar[BaseOp] = BaseOp.EXTEND_ZERO

    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits)


class ExtractLow(ExtractLowOp):
    op_base: ClassVar[BaseOp] = BaseOp.EXTRACT_LOW

    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits)


class Popcnt(UnaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.POPCNT

    def __init__(self, bits: int):
        super().__init__(bits)


class Ctz(UnaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.CTZ

    def __init__(self, bits: int):
        super().__init__(bits)


class Clz(UnaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.CLZ

    def __init__(self, bits: int):
        super().__init__(bits)


class Reverse(UnaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.REVERSE

    def __init__(self, bits: int):
        super().__init__(bits)


class RemU(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.REM_U

    def __init__(self, bits: int):
        super().__init__(bits)


class RemS(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.REM_S

    def __init__(self, bits: int):
        super().__init__(bits)


class Ror(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.ROR

    def __init__(self, bits: int):
        super().__init__(bits)


class Rol(BinaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.ROL

    def __init__(self, bits: int):
        super().__init__(bits)


class AddOverflow(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.ADD_OVERFLOW

    def __init__(self, bits: int):
        super().__init__(bits, out_bits=1)


class SubOverflow(CmpOp):
    op_base: ClassVar[BaseOp] = BaseOp.SUB_OVERFLOW

    def __init__(self, bits: int):
        super().__init__(bits, out_bits=1)


class DivU(TernaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.DIV_U

    def __init__(self, bits: int):
        super().__init__(bits)


class DivS(TernaryOp):
    op_base: ClassVar[BaseOp] = BaseOp.DIV_S

    def __init__(self, bits: int):
        super().__init__(bits)


class Select(Operation):
    op_base: ClassVar[BaseOp] = BaseOp.SELECT

    def __init__(self, bits: int):
        name = f"select_{bits}"
        super().__init__(
            name=name,
            attributes=[],
            inputs=[1, bits, bits],
            outputs=[bits],
            semantic_base=self.op_base.value,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    def _check_signature(self):
        check_bits(self.inputs[1], "input[1] width")
        check_bits(self.inputs[2], "input[2] width")
        check_bits(self.outputs[0], "output width")
        if not (self.inputs[1] == self.inputs[2] == self.outputs[0]):
            raise TypeCheckError(
                "Select: mismatched widths of true/false branches and output"
            )

    @classmethod
    def from_operation(cls, op: Operation) -> "Select":
        return cls(op.inputs[1])._restore_from(op)


def from_operation(op: Operation) -> Operation:
    sb = op.semantic_base

    if sb is None:
        return op

    cls = Operation.typed_ops.get(sb)
    if cls is None:
        assert False, f"Unexpected operation with semantic {sb}"

    return cls.from_operation(op)
