from lira.arch import Operation


class TypeCheckError(Exception):
    pass


class BaseOp:
    """Standard LIRA operation names — mirrors Rust `base_op` module."""
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

    def __str__(self) -> str:
        return self.value


def check_bits(value: int, name: str):
    if not isinstance(value, int) or value <= 0:
        raise TypeCheckError(f"{name} must be positive integer, got {value}")


class StdOperation(Operation):
    def _base_name(self) -> str:
        name = type(self).__name__.lower()
        if name.endswith("_op"):
            name = name[:-3]
        return name

    def _generate_name(self) -> str:
        if len(self.outputs) == 1:
            bits = self.outputs[0]
            return f"{self._base_name()}_{bits}"
        return f"{self._base_name()}_{'_'.join(str(b) for b in self.outputs)}"


class UnaryOp(StdOperation):
    def __init__(self, out_bits: int, name: str = "", semantic_base: str = ""):
        if not name:
            name = f"{self._base_name()}_{out_bits}"
        if not semantic_base:
            semantic_base = self._base_name()
        super().__init__(
            name=name,
            attributes=[],
            inputs=[out_bits],
            outputs=[out_bits],
            semantic_base=semantic_base,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    def _check_signature(self):
        check_bits(self.inputs[0], "input width")
        check_bits(self.outputs[0], "output width")
        if self.inputs[0] != self.outputs[0]:
            raise TypeCheckError(
                f"UnaryOp: input {self.inputs[0]} != output {self.outputs[0]}"
            )


class BinaryOp(StdOperation):
    def __init__(self, bits: int, name: str = "", semantic_base: str = ""):
        if not name:
            name = f"{self._base_name()}_{bits}"
        if not semantic_base:
            semantic_base = self._base_name()
        super().__init__(
            name=name,
            attributes=[],
            inputs=[bits, bits],
            outputs=[bits],
            semantic_base=semantic_base,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    def _check_signature(self):
        for i, inp in enumerate(self.inputs):
            check_bits(inp, f"input[{i}]")
        check_bits(self.outputs[0], "output")
        if not (self.inputs[0] == self.inputs[1] == self.outputs[0]):
            raise TypeCheckError(
                f"BinaryOp: inputs {self.inputs} vs output {self.outputs[0]}"
            )


class CmpOp(StdOperation):
    def __init__(
        self, bits: int, out_bits: int = 1, name: str = "", semantic_base: str = ""
    ):
        if not name:
            name = f"{self._base_name()}_{bits}"
        if not semantic_base:
            semantic_base = self._base_name()
        super().__init__(
            name=name,
            attributes=[],
            inputs=[bits, bits],
            outputs=[out_bits],
            semantic_base=semantic_base,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    def _check_signature(self):
        check_bits(self.inputs[0], "input[0]")
        check_bits(self.inputs[1], "input[1]")
        check_bits(self.outputs[0], "output")
        if self.inputs[0] != self.inputs[1]:
            raise TypeCheckError(
                f"CmpOp: input widths differ {self.inputs[0]} vs {self.inputs[1]}"
            )


class TernaryOp(StdOperation):
    def __init__(self, bits: int, name: str = "", semantic_base: str = ""):
        if not name:
            name = f"{self._base_name()}_{bits}"
        if not semantic_base:
            semantic_base = self._base_name()
        super().__init__(
            name=name,
            attributes=[],
            inputs=[bits, bits, bits],
            outputs=[bits],
            semantic_base=semantic_base,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    def _check_signature(self):
        for i, inp in enumerate(self.inputs):
            check_bits(inp, f"input[{i}]")
        check_bits(self.outputs[0], "output")
        if not (self.inputs[0] == self.inputs[1] == self.inputs[2] == self.outputs[0]):
            raise TypeCheckError(
                f"TernaryOp: mismatched widths {self.inputs} -> {self.outputs[0]}"
            )


class ExtendOp(StdOperation):
    def __init__(self, in_bits: int, out_bits: int, kind: str, name: str = ""):
        if not name:
            name = f"{kind}_{in_bits}_to_{out_bits}"
        super().__init__(
            name=name,
            attributes=[],
            inputs=[in_bits],
            outputs=[out_bits],
            semantic_base=kind,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    def _check_signature(self):
        check_bits(self.inputs[0], "input")
        check_bits(self.outputs[0], "output")
        if self.inputs[0] >= self.outputs[0]:
            raise TypeCheckError(
                f"ExtendOp: input {self.inputs[0]} >= output {self.outputs[0]}"
            )


class ExtractLowOp(StdOperation):
    def __init__(self, in_bits: int, out_bits: int, name: str = ""):
        if not name:
            name = f"extract_low_{in_bits}_to_{out_bits}"
        super().__init__(
            name=name,
            attributes=[],
            inputs=[in_bits],
            outputs=[out_bits],
            semantic_base=BaseOp.EXTRACT_LOW,
            semantic_func=None,
            semantic_table=None,
        )
        self._check_signature()

    def _check_signature(self):
        check_bits(self.inputs[0], "input")
        check_bits(self.outputs[0], "output")
        if self.outputs[0] > self.inputs[0]:
            raise TypeCheckError(
                f"ExtractLow: output {self.outputs[0]} > input {self.inputs[0]}"
            )


class Not(UnaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.NOT)


class Neg(UnaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.NEG)


class Add(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.ADD)


class Sub(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.SUB)


class Mul(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.MUL)


class And(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.AND)


class Orr(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.ORR)


class Xor(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.XOR)


class Lsl(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.LSL)


class Lsr(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.LSR)


class Asr(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.ASR)


class Eq(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.EQ)


class Ne(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.NE)


class Slt(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.SLT)


class Sle(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.SLE)


class Sgt(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.SGT)


class Sge(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.SGE)


class Ult(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.ULT)


class Ule(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.ULE)


class Ugt(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.UGT)


class Uge(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.UGE)


class ExtendSign(ExtendOp):
    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits, "extend_sign")


class ExtendZero(ExtendOp):
    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits, "extend_zero")


class ExtractLow(ExtractLowOp):
    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits)


class Popcnt(UnaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.POPCNT)


class Ctz(UnaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.CTZ)


class Clz(UnaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.CLZ)


class Reverse(UnaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.REVERSE)


class RemU(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.REM_U)


class RemS(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.REM_S)


class Ror(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.ROR)


class Rol(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.ROL)


class AddOverflow(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, out_bits=1, semantic_base=BaseOp.ADD_OVERFLOW)


class SubOverflow(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, out_bits=1, semantic_base=BaseOp.SUB_OVERFLOW)


class DivU(TernaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.DIV_U)


class DivS(TernaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base=BaseOp.DIV_S)


class Select(StdOperation):
    def __init__(self, bits: int):
        name = f"select_{bits}"
        super().__init__(
            name=name,
            attributes=[],
            inputs=[1, bits, bits],
            outputs=[bits],
            semantic_base=BaseOp.SELECT,
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
