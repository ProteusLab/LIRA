from lira.arch import Operation


class TypeCheckError(Exception):
    pass


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
            semantic_base="extract_low",
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
        super().__init__(bits, semantic_base="not")


class Neg(UnaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="neg")


class Add(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="add")


class Sub(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="sub")


class Mul(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="mul")


class And(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="and")


class Orr(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="orr")


class Xor(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="xor")


class Lsl(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="lsl")


class Lsr(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="lsr")


class Asr(BinaryOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="asr")


class Eq(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="eq")


class Ne(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="ne")


class Slt(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="slt")


class Sle(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="sle")


class Sgt(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="sgt")


class Sge(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="sge")


class Ult(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="ult")


class Ule(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="ule")


class Ugt(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="ugt")


class Uge(CmpOp):
    def __init__(self, bits: int):
        super().__init__(bits, semantic_base="uge")


class ExtendSign(ExtendOp):
    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits, "extend_sign")


class ExtendZero(ExtendOp):
    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits, "extend_zero")


class ExtractLow(ExtractLowOp):
    def __init__(self, in_bits: int, out_bits: int):
        super().__init__(in_bits, out_bits)
