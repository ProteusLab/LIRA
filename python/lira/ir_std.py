from .ir import *
from .arch import *

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


class StmtKind(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    READ = "read"
    WRITE = "write"
    OP = "op"
    ENV = "env"
    COND_ENV = "cond_env"
    CONST = "const"
    DYN_CONST = "dyn_const"


@dataclass
class StmtInput:
    kind: ClassVar[StmtKind] = StmtKind.INPUT
    id_: int

@dataclass
class StmtOutput:
    kind: ClassVar[StmtKind] = StmtKind.OUTPUT
    id_: int
    value: str

@dataclass
class StmtRead:
    kind: ClassVar[StmtKind] = StmtKind.READ
    rf: RegisterFile
    rsi: str

@dataclass
class StmtWrite:
    kind: ClassVar[StmtKind] = StmtKind.WRITE
    rf: RegisterFile
    rsi: str
    value: str

@dataclass
class StmtOp:
    kind: ClassVar[StmtKind] = StmtKind.OP
    op: Operation
    args: list[str]

@dataclass
class StmtEnv:
    kind: ClassVar[StmtKind] = StmtKind.ENV
    env: EnvironmentFunction
    args: list[str]

class CondEnv:
    kind: ClassVar[StmtKind] = StmtKind.COND_ENV
    env: EnvironmentFunction
    cond: str
    on_false: list[str]
    inputs: list[str]

@dataclass
class StmtIndex:
    pass

@dataclass
class StmtConst:
    kind: ClassVar[StmtKind] = StmtKind.CONST
    value: int

@dataclass
class StmtDynConst:
    kind: ClassVar[StmtKind] = StmtKind.DYN_CONST
    name: str

@dataclass
class StmtGather:
    value: str
    index: str
    default: str

@dataclass
class StmtFold:
    op: Operation
    args: list[str]

@dataclass
class StmtScan:
    op: Operation
    args: list[str]

@dataclass
class StmtAlias:
    semantic: Snippet
    args: list[str]
