from lira.ir import *
from lira.arch import *

from dataclasses import dataclass

@dataclass
class StmtInput:
    id_: int

@dataclass
class StmtOutput:
    id_: int
    value: str

@dataclass
class StmtRead:
    rf: RegisterFile
    rsi: str

@dataclass
class StmtWrite:
    rf: RegisterFile
    rsi: str
    value: str

@dataclass
class StmtOp:
    op: Operation
    args: list[str]

@dataclass
class StmtEnv:
    env: EnvironmentFunction
    args: list[str]

class CondEnv:
    env: EnvironmentFunction
    cond: str
    on_false: [str]
    inputs: [str]

@dataclass
class StmtIndex:
    pass

@dataclass
class StmtConst:
    value: int

@dataclass
class StmtDynConst:
    name: str

@dataclass
class StmtGather:
    value: str
    index: str
    default: str

@dataclass
class StmtFold:
    op: Operation
    args: [str]

@dataclass
class StmtScan:
    op: Operation
    args: [str]

@dataclass
class StmtAlias:
    semantic: Snippet
    args: [str]
