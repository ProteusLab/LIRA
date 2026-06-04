# lira/builder.py
from typing import List, Optional, Dict, Tuple
from lira.ir import *
from lira.arch import *
from lira.ir_ops import *


class Value:
    def __init__(self, name: str, width: int = 32):
        self.name = name
        self.width = width

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Value({self.name}, {self.width})"


class SeqBuilder:
    def __init__(self):
        self.stmts: List[Statement] = []
        self._temp_counter = 0
        self._op_cache: Dict[Tuple[type, Tuple, Tuple], Operation] = {}

    def _new_temp(self, width: int = 32) -> Value:
        self._temp_counter += 1
        return Value(f"_t{self._temp_counter}", width)

    def _get_or_create_op(self, op_class, *args, **kwargs) -> Operation:
        key = (op_class, args, tuple(sorted(kwargs.items())))
        if key not in self._op_cache:
            self._op_cache[key] = op_class(*args, **kwargs)
        return self._op_cache[key]

    # ------------------------------------------------------------------
    # NOTE: Standart operations
    # ------------------------------------------------------------------
    def add(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"add width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Add, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def sub(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"sub width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Sub, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def mul(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"mul width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Mul, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def and_(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"and width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(And, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def orr(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"orr width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Orr, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def xor(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"xor width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Xor, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def lsl(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"lsl width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Lsl, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def lsr(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"lsr width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Lsr, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def asr(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"asr width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Asr, a.width)
        out = self._new_temp(a.width)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def slt(self, a: Value, b: Value) -> Value:
        if a.width != b.width:
            raise TypeError(f"slt width mismatch: {a.width} vs {b.width}")
        op = self._get_or_create_op(Slt, a.width)
        out = self._new_temp(1)
        self.add_op(op, [a.name, b.name], [out.name])
        return out

    def extend_sign(self, a: Value, to_width: int) -> Value:
        if a.width >= to_width:
            raise ValueError(
                f"extend_sign: input width {a.width} >= output width {to_width}"
            )
        op = self._get_or_create_op(ExtendSign, a.width, to_width)
        out = self._new_temp(to_width)
        self.add_op(op, [a.name], [out.name])
        return out

    def extract_low(self, a: Value, out_width: int) -> Value:
        if out_width > a.width:
            raise ValueError(
                f"extract_low: output width {out_width} > input width {a.width}"
            )
        op = self._get_or_create_op(ExtractLow, a.width, out_width)
        out = self._new_temp(out_width)
        self.add_op(op, [a.name], [out.name])
        return out

    # ------------------------------------------------------------------
    # NOTE: Registers & Memory
    # ------------------------------------------------------------------
    def read(
        self, rf: RegisterFile, rsi: Value, shape: Shape = Shape(1, None)
    ) -> Value:
        # NOTE: Review it in vector registers integration
        width = rf.reg_size.lanes_base
        out = self._new_temp(width)
        stmt = Statement(shape, [out.name], [width], "read", rf.name, [str(rsi)])
        self.stmts.append(stmt)
        return out

    def write(
        self, rf: RegisterFile, rsi: Value, value: Value, shape: Shape = Shape(1, None)
    ):
        stmt = Statement(shape, [], [], "write", rf.name, [str(rsi), str(value)])
        self.stmts.append(stmt)

    def const(self, value: int, width: int = 32) -> Value:
        out = self._new_temp(width)
        stmt = Statement(Shape(1, None), [out.name], [width], "const", str(value), [])
        self.stmts.append(stmt)
        return out

    def dyn_const(self, name: str, width: int = 32) -> Value:
        out = self._new_temp(width)
        stmt = Statement(Shape(1, None), [out.name], [width], "dyn_const", name, [])
        self.stmts.append(stmt)
        return out

    def env(self, env_func: EnvironmentFunction, inputs: List[Value]) -> List[Value]:
        outputs = [self._new_temp(w) for w in env_func.outputs]
        stmt = Statement(
            Shape(1, None),
            [o.name for o in outputs],
            env_func.outputs,
            "env",
            env_func.name,
            [str(v) for v in inputs],
        )
        self.stmts.append(stmt)
        return outputs

    def cond_env(
        self,
        env_func: EnvironmentFunction,
        cond: Value,
        inputs: List[Value],
        on_false: List[Value],
    ) -> List[Value]:
        outputs = [self._new_temp(w) for w in env_func.outputs]
        all_inputs = [str(cond)] + [str(v) for v in inputs] + [str(v) for v in on_false]
        stmt = Statement(
            Shape(1, None),
            [o.name for o in outputs],
            env_func.outputs,
            "cond_env",
            env_func.name,
            all_inputs,
        )
        self.stmts.append(stmt)
        return outputs

    def input(self, idx: int, width: int = 32) -> Value:
        out = self._new_temp(width)
        stmt = Statement(Shape(1, None), [out.name], [width], "input", str(idx), [])
        self.stmts.append(stmt)
        return out

    def output(self, value: Value, idx: int):
        stmt = Statement(Shape(1, None), [], [], "output", str(idx), [str(value)])
        self.stmts.append(stmt)

    def add_op(
        self,
        op: Operation,
        inputs: List[str],
        outputs: List[str],
        shape: Shape = Shape(1, None),
    ):
        out_types = op.outputs
        stmt = Statement(shape, outputs, out_types, "op", op.name, inputs)
        self.stmts.append(stmt)

    def op(self, operation: Operation, inputs: List[Value]) -> Value:
        if len(operation.outputs) != 1:
            raise ValueError(
                f"Operation {operation.name} has {len(operation.outputs)} outputs, use op_multi"
            )
        out_width = operation.outputs[0]
        out = self._new_temp(out_width)
        self.add_op(operation, [v.name for v in inputs], [out.name])
        return out

    def op_multi(self, operation: Operation, inputs: List[Value]) -> List[Value]:
        outputs = [self._new_temp(w) for w in operation.outputs]
        self.add_op(operation, [v.name for v in inputs], [o.name for o in outputs])
        return outputs

    def build(self) -> StatementSeq:
        return StatementSeq(self.stmts)

    def __iadd__(self, other: "SeqBuilder") -> "SeqBuilder":
        self.stmts.extend(other.stmts)
        self._temp_counter = max(self._temp_counter, other._temp_counter)
        return self


class BaseBuilder:
    def __init__(self):
        self.seq = SeqBuilder()

    def add(self, a: Value, b: Value) -> Value:
        return self.seq.add(a, b)

    def sub(self, a: Value, b: Value) -> Value:
        return self.seq.sub(a, b)

    def mul(self, a: Value, b: Value) -> Value:
        return self.seq.mul(a, b)

    def and_(self, a: Value, b: Value) -> Value:
        return self.seq.and_(a, b)

    def orr(self, a: Value, b: Value) -> Value:
        return self.seq.orr(a, b)

    def xor(self, a: Value, b: Value) -> Value:
        return self.seq.xor(a, b)

    def lsl(self, a: Value, b: Value) -> Value:
        return self.seq.lsl(a, b)

    def lsr(self, a: Value, b: Value) -> Value:
        return self.seq.lsr(a, b)

    def asr(self, a: Value, b: Value) -> Value:
        return self.seq.asr(a, b)

    def slt(self, a: Value, b: Value) -> Value:
        return self.seq.slt(a, b)

    def extend_sign(self, a: Value, to_width: int) -> Value:
        return self.seq.extend_sign(a, to_width)

    def extract_low(self, a: Value, out_width: int) -> Value:
        return self.seq.extract_low(a, out_width)

    def read(
        self, rf: RegisterFile, rsi: Value, shape: Shape = Shape(1, None)
    ) -> Value:
        return self.seq.read(rf, rsi, shape)

    def write(
        self, rf: RegisterFile, rsi: Value, value: Value, shape: Shape = Shape(1, None)
    ):
        self.seq.write(rf, rsi, value, shape)

    def const(self, value: int, width: int = 32) -> Value:
        return self.seq.const(value, width)

    def dyn_const(self, name: str, width: int = 32) -> Value:
        return self.seq.dyn_const(name, width)

    def env(self, env_func: EnvironmentFunction, inputs: List[Value]) -> List[Value]:
        return self.seq.env(env_func, inputs)

    def cond_env(
        self,
        env_func: EnvironmentFunction,
        cond: Value,
        inputs: List[Value],
        on_false: List[Value],
    ) -> List[Value]:
        return self.seq.cond_env(env_func, cond, inputs, on_false)

    def input(self, idx: int, width: int = 32) -> Value:
        return self.seq.input(idx, width)

    def output(self, value: Value, idx: int):
        self.seq.output(value, idx)

    def op(self, operation: Operation, inputs: List[Value]) -> Value:
        return self.seq.op(operation, inputs)

    def op_multi(self, operation: Operation, inputs: List[Value]) -> List[Value]:
        return self.seq.op_multi(operation, inputs)


class SnippetBuilder(BaseBuilder):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def build(self) -> Snippet:
        return Snippet(self.name, self.seq.build())


class InstructionBuilder(BaseBuilder):
    def __init__(
        self,
        name: str,
        operand_sizes: List[int],
        operand_names: List[str],
        encoding: InstructionEncoding,
    ):
        super().__init__()
        self.name = name
        self.operand_sizes = operand_sizes
        self.operand_names = operand_names
        self.encoding = encoding

    def add_input_operand(self, idx: int, width: Optional[int] = None) -> Value:
        if width is None:
            width = self.operand_sizes[idx] if idx < len(self.operand_sizes) else 32
        return self.input(idx, width)

    def build(self) -> Instruction:
        return Instruction(
            name=self.name,
            attributes=[],
            operand_sizes=self.operand_sizes,
            operand_names=self.operand_names,
            encoding=self.encoding,
            semantic=self.seq.build(),
        )


class ArchBuilder:
    def __init__(self, name: str, attributes: List[str] = None):
        self.name = name
        self.attributes = attributes or []
        self.register_files: List[RegisterFile] = []
        self.system_registers: List[SystemRegister] = []
        self.environment_functions: List[EnvironmentFunction] = []
        self.tables_int: List[TableInt] = []
        self.operations: List[Operation] = []
        self.snippets: List[Snippet] = []
        self.instructions: List[Instruction] = []

    def add_register_file(self, rf: RegisterFile):
        self.register_files.append(rf)
        return self

    def add_system_register(self, sr: SystemRegister):
        self.system_registers.append(sr)
        return self

    def add_env_func(self, env: EnvironmentFunction):
        self.environment_functions.append(env)
        return self

    def add_table_int(self, table: TableInt):
        self.tables_int.append(table)
        return self

    def add_operation(self, op: Operation):
        self.operations.append(op)
        return self

    def add_snippet(self, snippet: Snippet):
        self.snippets.append(snippet)
        return self

    def add_instruction(self, instr: Instruction):
        self.instructions.append(instr)
        return self

    def build(self) -> Arch:
        return Arch(
            name=self.name,
            attributes=self.attributes,
            register_files=self.register_files,
            system_registers=self.system_registers,
            environment_functions=self.environment_functions,
            tables_int=self.tables_int,
            operations=self.operations,
            snippets=self.snippets,
            instructions=self.instructions,
        )
