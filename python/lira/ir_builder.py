# lira/builder.py
from typing import List, Optional, Dict, Tuple
from .ir import *
from .arch import *
from .ir_ops import *


class Value:
    def __init__(self, name: str, width: int = 32):
        self.name = name
        self.width = width
        self.shape = Shape(1, None)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Value({self.name}, {self.width})"


class SeqBuilder:
    def __init__(self):
        self.stmts: List[Statement] = []
        self._temp_counter = 0

    def _new_temp(self, width: int = 32) -> Value:
        self._temp_counter += 1
        return Value(f"_t{self._temp_counter}", width)

    def _emit_op(self, op: Operation, inputs: List[str], out_bits: int) -> Value:
        out = self._new_temp(out_bits)
        self.add_op(op, inputs, [out.name])
        return out

    def check_width_match(self, a: Value, b: Value):
        if a.width != b.width:
            raise TypeError(f"width mismatch: {a.width} != {b.width}")

    # ------------------------------------------------------------------
    # NOTE: Building python/lira/ir_ops.py objects
    # ------------------------------------------------------------------
    def add(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Add(a.width), [a.name, b.name], a.width)

    def sub(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Sub(a.width), [a.name, b.name], a.width)

    def mul(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Mul(a.width), [a.name, b.name], a.width)

    def and_(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(And(a.width), [a.name, b.name], a.width)

    def orr(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Orr(a.width), [a.name, b.name], a.width)

    def xor(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Xor(a.width), [a.name, b.name], a.width)

    def lsl(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Lsl(a.width), [a.name, b.name], a.width)

    def lsr(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Lsr(a.width), [a.name, b.name], a.width)

    def asr(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Asr(a.width), [a.name, b.name], a.width)

    def slt(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Slt(a.width), [a.name, b.name], 1)

    def sle(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Sle(a.width), [a.name, b.name], 1)

    def sgt(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Sgt(a.width), [a.name, b.name], 1)

    def sge(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Sge(a.width), [a.name, b.name], 1)

    def ult(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Ult(a.width), [a.name, b.name], 1)

    def ule(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Ule(a.width), [a.name, b.name], 1)

    def ugt(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Ugt(a.width), [a.name, b.name], 1)

    def uge(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Uge(a.width), [a.name, b.name], 1)

    def eq(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Eq(a.width), [a.name, b.name], 1)

    def ne(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Ne(a.width), [a.name, b.name], 1)

    def rem_u(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(RemU(a.width), [a.name, b.name], a.width)

    def rem_s(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(RemS(a.width), [a.name, b.name], a.width)

    def ror(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Ror(a.width), [a.name, b.name], a.width)

    def rol(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(Rol(a.width), [a.name, b.name], a.width)

    def add_overflow(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(AddOverflow(a.width), [a.name, b.name], 1)

    def sub_overflow(self, a: Value, b: Value) -> Value:
        self.check_width_match(a, b)
        return self._emit_op(SubOverflow(a.width), [a.name, b.name], 1)

    def not_(self, a: Value) -> Value:
        return self._emit_op(Not(a.width), [a.name], a.width)

    def neg(self, a: Value) -> Value:
        return self._emit_op(Neg(a.width), [a.name], a.width)

    def popcnt(self, a: Value) -> Value:
        return self._emit_op(Popcnt(a.width), [a.name], a.width)

    def ctz(self, a: Value) -> Value:
        return self._emit_op(Ctz(a.width), [a.name], a.width)

    def clz(self, a: Value) -> Value:
        return self._emit_op(Clz(a.width), [a.name], a.width)

    def reverse(self, a: Value) -> Value:
        return self._emit_op(Reverse(a.width), [a.name], a.width)

    def extend_sign(self, a: Value, to_width: int) -> Value:
        if a.width >= to_width:
            raise ValueError(
                f"extend_sign: input width {a.width} >= output width {to_width}"
            )
        return self._emit_op(ExtendSign(a.width, to_width), [a.name], to_width)

    def extend_zero(self, a: Value, to_width: int) -> Value:
        if a.width >= to_width:
            raise ValueError(
                f"extend_zero: input width {a.width} >= output width {to_width}"
            )
        return self._emit_op(ExtendZero(a.width, to_width), [a.name], to_width)

    def extract_low(self, a: Value, out_width: int) -> Value:
        if out_width > a.width:
            raise ValueError(
                f"extract_low: output width {out_width} > input width {a.width}"
            )
        return self._emit_op(ExtractLow(a.width, out_width), [a.name], out_width)

    def div_u(self, a: Value, b: Value, default: Value) -> Value:
        self.check_width_match(a, b)
        if a.width != default.width:
            raise TypeError("div_u: default width mismatch")
        return self._emit_op(DivU(a.width), [a.name, b.name, default.name], a.width)

    def div_s(self, a: Value, b: Value, default: Value) -> Value:
        self.check_width_match(a, b)
        if a.width != default.width:
            raise TypeError("div_s: default width mismatch")
        return self._emit_op(DivS(a.width), [a.name, b.name, default.name], a.width)

    def select(self, cond: Value, true_val: Value, false_val: Value) -> Value:
        if cond.width != 1:
            raise TypeError("select: condition must be 1-bit")
        if true_val.width != false_val.width:
            raise TypeError("select: true and false branch widths mismatch")
        return self._emit_op(
            Select(true_val.width),
            [cond.name, true_val.name, false_val.name],
            true_val.width,
        )

    # ------------------------------------------------------------------
    # NOTE: Building python/lira/ir_std.py objects
    # ------------------------------------------------------------------
    def read(
        self, rf: RegisterFile, rsi: Value, shape: Shape = Shape(1, None)
    ) -> Value:
        width = rf.reg_size.lanes_base
        out = self._new_temp(width)
        stmt = Statement(shape, [out.name], [width], "read", rf.name, [rsi.name])
        self.stmts.append(stmt)
        return out

    def write(
        self, rf: RegisterFile, rsi: Value, value: Value, shape: Shape = Shape(1, None)
    ):
        stmt = Statement(shape, [], [], "write", rf.name, [rsi.name, value.name])
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
            [v.name for v in inputs],
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
        all_inputs = [cond.name] + [v.name for v in inputs] + [v.name for v in on_false]
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
        stmt = Statement(Shape(1, None), [], [], "output", str(idx), [value.name])
        self.stmts.append(stmt)

    # ------------------------------------------------------------------
    # NOTE: Others
    # ------------------------------------------------------------------
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
        return self._emit_op(operation, [v.name for v in inputs], operation.outputs[0])

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
        self._op_cache: Dict[str, Operation] = {}

    def _cache_op(self, op_class, *args, **kwargs) -> Operation:
        op = op_class(*args, **kwargs)
        if op.name not in self._op_cache:
            self._op_cache[op.name] = op
        return self._op_cache[op.name]

    @property
    def operations_map(self) -> Dict[str, Operation]:
        return {op.name: op for op in self._op_cache.values()}

    # ------------------------------------------------------------------
    # NOTE: Building python/lira/ir_ops.py objects
    # ------------------------------------------------------------------
    def add(self, a: Value, b: Value) -> Value:
        self._cache_op(Add, a.width)
        return self.seq.add(a, b)

    def sub(self, a: Value, b: Value) -> Value:
        self._cache_op(Sub, a.width)
        return self.seq.sub(a, b)

    def mul(self, a: Value, b: Value) -> Value:
        self._cache_op(Mul, a.width)
        return self.seq.mul(a, b)

    def and_(self, a: Value, b: Value) -> Value:
        self._cache_op(And, a.width)
        return self.seq.and_(a, b)

    def orr(self, a: Value, b: Value) -> Value:
        self._cache_op(Orr, a.width)
        return self.seq.orr(a, b)

    def xor(self, a: Value, b: Value) -> Value:
        self._cache_op(Xor, a.width)
        return self.seq.xor(a, b)

    def lsl(self, a: Value, b: Value) -> Value:
        self._cache_op(Lsl, a.width)
        return self.seq.lsl(a, b)

    def lsr(self, a: Value, b: Value) -> Value:
        self._cache_op(Lsr, a.width)
        return self.seq.lsr(a, b)

    def asr(self, a: Value, b: Value) -> Value:
        self._cache_op(Asr, a.width)
        return self.seq.asr(a, b)

    def slt(self, a: Value, b: Value) -> Value:
        self._cache_op(Slt, a.width)
        return self.seq.slt(a, b)

    def sle(self, a: Value, b: Value) -> Value:
        self._cache_op(Sle, a.width)
        return self.seq.sle(a, b)

    def sgt(self, a: Value, b: Value) -> Value:
        self._cache_op(Sgt, a.width)
        return self.seq.sgt(a, b)

    def sge(self, a: Value, b: Value) -> Value:
        self._cache_op(Sge, a.width)
        return self.seq.sge(a, b)

    def ult(self, a: Value, b: Value) -> Value:
        self._cache_op(Ult, a.width)
        return self.seq.ult(a, b)

    def ule(self, a: Value, b: Value) -> Value:
        self._cache_op(Ule, a.width)
        return self.seq.ule(a, b)

    def ugt(self, a: Value, b: Value) -> Value:
        self._cache_op(Ugt, a.width)
        return self.seq.ugt(a, b)

    def uge(self, a: Value, b: Value) -> Value:
        self._cache_op(Uge, a.width)
        return self.seq.uge(a, b)

    def eq(self, a: Value, b: Value) -> Value:
        self._cache_op(Eq, a.width)
        return self.seq.eq(a, b)

    def ne(self, a: Value, b: Value) -> Value:
        self._cache_op(Ne, a.width)
        return self.seq.ne(a, b)

    def rem_u(self, a: Value, b: Value) -> Value:
        self._cache_op(RemU, a.width)
        return self.seq.rem_u(a, b)

    def rem_s(self, a: Value, b: Value) -> Value:
        self._cache_op(RemS, a.width)
        return self.seq.rem_s(a, b)

    def ror(self, a: Value, b: Value) -> Value:
        self._cache_op(Ror, a.width)
        return self.seq.ror(a, b)

    def rol(self, a: Value, b: Value) -> Value:
        self._cache_op(Rol, a.width)
        return self.seq.rol(a, b)

    def add_overflow(self, a: Value, b: Value) -> Value:
        self._cache_op(AddOverflow, a.width)
        return self.seq.add_overflow(a, b)

    def sub_overflow(self, a: Value, b: Value) -> Value:
        self._cache_op(SubOverflow, a.width)
        return self.seq.sub_overflow(a, b)

    def not_(self, a: Value) -> Value:
        self._cache_op(Not, a.width)
        return self.seq.not_(a)

    def neg(self, a: Value) -> Value:
        self._cache_op(Neg, a.width)
        return self.seq.neg(a)

    def popcnt(self, a: Value) -> Value:
        self._cache_op(Popcnt, a.width)
        return self.seq.popcnt(a)

    def ctz(self, a: Value) -> Value:
        self._cache_op(Ctz, a.width)
        return self.seq.ctz(a)

    def clz(self, a: Value) -> Value:
        self._cache_op(Clz, a.width)
        return self.seq.clz(a)

    def reverse(self, a: Value) -> Value:
        self._cache_op(Reverse, a.width)
        return self.seq.reverse(a)

    def extend_sign(self, a: Value, to_width: int) -> Value:
        self._cache_op(ExtendSign, a.width, to_width)
        return self.seq.extend_sign(a, to_width)

    def extend_zero(self, a: Value, to_width: int) -> Value:
        self._cache_op(ExtendZero, a.width, to_width)
        return self.seq.extend_zero(a, to_width)

    def extract_low(self, a: Value, out_width: int) -> Value:
        self._cache_op(ExtractLow, a.width, out_width)
        return self.seq.extract_low(a, out_width)

    def div_u(self, a: Value, b: Value, default: Value) -> Value:
        self._cache_op(DivU, a.width)
        return self.seq.div_u(a, b, default)

    def div_s(self, a: Value, b: Value, default: Value) -> Value:
        self._cache_op(DivS, a.width)
        return self.seq.div_s(a, b, default)

    def select(self, cond: Value, true_val: Value, false_val: Value) -> Value:
        self._cache_op(Select, true_val.width)
        return self.seq.select(cond, true_val, false_val)

    # ------------------------------------------------------------------
    # NOTE: Building python/lira/ir_std.py objects
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # NOTE: Others
    # ------------------------------------------------------------------
    def op(self, operation: Operation, inputs: List[Value]) -> Value:
        self._op_cache[operation.name] = operation
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
