"""Attach Arm XML assembly syntax to the existing AArch64 LIRA encoding forms."""

from dataclasses import dataclass
import re
from xml.etree.ElementTree import Element

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from python.lira.arch_ser_yaml import to_serializable

from .syntax_aliases import read_aliases


class UnsupportedSyntax(ValueError):
    pass


@dataclass(frozen=True)
class Value:
    name: str
    width: int


class Sequence:
    def __init__(self, arch, instruction):
        self.arch = arch
        self.lines = []
        self.fields = {
            field: self.value("input", str(index), width)
            for index, (field, width) in enumerate(
                zip(instruction["operand_names"], instruction["operand_sizes"], strict=True)
            )
        }

    def value(self, kind, specifier, width, *args):
        result = Value(f"_v{len(self.lines)}", width)
        self.lines.append(
            f"1 {width} {result.name} = {kind} {specifier}"
            + "".join(f" {arg.name}" for arg in args)
            + ";"
        )
        return result

    def const(self, number, width):
        return self.value("const", str(number % (1 << width)), width)

    def op(self, base, width, *args):
        inputs = [arg.width for arg in args]
        name = "syntax_" + "_".join(map(str, (base, *inputs, "to", width)))
        self.arch.operations.setdefault(
            name, dict(name=name, attributes=[], inputs=inputs, outputs=[width], semantic_base=base)
        )
        return self.value("op", name, width, *args)

    def widen(self, value, width=32, signed=False):
        if value.width == width:
            return value
        return self.op("extend_sign" if signed else "extend_zero", width, value)

    def compare(self, left, relation, right):
        if isinstance(right, int):
            right = self.const(right, left.width)
        return self.op(relation, 1, left, right)

    def emit(self, kind, specifier, *args):
        self.lines.append(f"1 = {kind} {specifier}" + "".join(f" {arg.name}" for arg in args) + ";")

    def text(self, value):
        for token in re.findall(r"\s+|\S+", value.lower()):
            self.emit("whitespace", "_") if token.isspace() else self.emit("string", token)

    def decimal(self, value, signed=False, scale=1):
        value = self.widen(value, signed=signed)
        if scale != 1:
            value = self.op("mul", 32, value, self.const(scale, 32))
        self.emit("format", "dec", value)

    def table(self, name, values, index):
        self.arch.tables.setdefault(name, list(values))
        self.emit("table", name, index)


def template_parts(template, *, register_list=False):
    """Keep XML operand links intact and tokenize the surrounding punctuation."""
    parts = []
    for node in template:
        if node.tag == "a" and (node.text or "").startswith("<"):
            parts.append(node)
        else:
            literal = "".join(node.itertext())
            if register_list:
                parts.append(literal)
            else:
                parts.extend(re.findall(r"[{}]|[^{}]+", literal))
    first = parts.pop(0)
    mnemonic, _, remainder = first.strip().partition(" ")
    if remainder.strip():
        # Retain the space inside a register-list opening brace.
        if register_list:
            remainder = first.lstrip().split(None, 1)[1]
        parts.insert(0, remainder.lstrip())
    return mnemonic.lower(), parts


def without_group(parts, include, include_inner=False):
    depth = 0
    result = []
    for part in parts:
        if part == "{":
            depth += 1
        elif part == "}":
            depth -= 1
        elif depth == 0 or (depth == 1 and include) or include_inner:
            result.append(part)
    if result and isinstance(result[-1], str):
        result[-1] = result[-1].rstrip()
    return result


SHIFTS = ("lsl", "lsr", "asr", "ror")
EXTENDS = ("uxtb", "uxth", "uxtw", "uxtx", "sxtb", "sxth", "sxtw", "sxtx")
CONDS = "eq ne hs lo mi pl vs vc hi ls ge lt gt le al nv".split()
ELEMENTS = "bhsd"
REGISTERS = {prefix: [f"{prefix}{i}" for i in range(32)] for prefix in "wxvbhdsq"}
for prefix in "wx":
    REGISTERS[prefix + "zr"] = REGISTERS[prefix][:31] + [prefix + "zr"]
    REGISTERS[prefix + "sp"] = REGISTERS[prefix][:31] + ["wsp" if prefix == "w" else "sp"]


# Each variant pairs a template expansion with its condition and operand overrides.
# A following variant is tried only when the preceding condition is false.
def variants(form, mnemonic, parts):
    fields = form.fields
    tags = [part.text for part in parts if isinstance(part, Element)]
    if (fields.keys() >= {"S", "Rm"} and "option" in fields.keys() | form.fixed.keys()
            and "ldst_regoff" in form.encoding.base_name):
        for option in (2, 3, 6, 7):
            if "option" in form.fixed and form.fixed["option"][0] != option:
                continue
            for scaled in (0, 1):
                # Normalize the XML's register alternative and extend clause.
                rt, rn = (next(part for part in parts if isinstance(part, Element) and
                               re.search(f'"{field}"', part.get("hover", ""))) for field in ("Rt", "Rn"))
                rm = next(part for part in parts if isinstance(part, Element) and
                          part.text == ("<Xm>" if option & 1 else "<Wm>"))
                variant = [rt, ", [", rn, ", ", rm]
                if option != 3 or scaled:
                    variant += [", " + ("lsl" if option == 3 else EXTENDS[option])]
                    if scaled:
                        variant += [f" #{form.access_scale.bit_length() - 1}"]
                yield variant + ["]"], (("option", "eq", option), ("S", "eq", scaled)), {}
    elif form.is_register_list or "{" not in parts:
        yield parts, (), {}
    elif mnemonic == "ret":
        yield [], (("Rn", "eq", 30),), {}
        yield without_group(parts, True), (), {}
    elif "<extend>" in tags and "imm3" in fields and "option" in fields:
        default = 3 if form.reg_width == 64 else 2
        stack = ("any", ("Rn", "eq", 31), ("Rd", "eq", 31)) if mnemonic not in ("cmp", "cmn") else ("Rn", "eq", 31)
        use_lsl = (stack, ("option", "eq", default))
        yield without_group(parts, False), use_lsl + (("imm3", "eq", 0),), {}
        yield without_group(parts, True, True), use_lsl, {"<extend>": "lsl"}
        yield without_group(parts, True), (("imm3", "eq", 0),), {}
        yield without_group(parts, True, True), (), {}
    elif "<shift>" in tags and "sh" in fields:
        yield without_group(parts, False), (("sh", "eq", 0),), {}
        yield without_group(parts, True), (), {"<shift>": "lsl #12"}
    elif "<shift>" in tags and fields.keys() >= {"shift", "imm6"}:
        yield without_group(parts, False), (("shift", "eq", 0), ("imm6", "eq", 0)), {}
        yield without_group(parts, True), (), {}
    elif "ldst" in form.encoding.base_name and any(tag in tags for tag in ("<pimm>", "<simm>", "<imm>")):
        field = next(name for name in ("imm12", "imm9", "imm7") if name in fields)
        yield without_group(parts, False), ((field, "eq", 0),), {}
        yield without_group(parts, True), (), {}
    else:
        raise UnsupportedSyntax("optional group")


class Form:
    def __init__(self, instruction, encoding):
        self.instruction = instruction
        self.encoding = encoding
        self.is_register_list = encoding.file.endswith(("_advsimd_sngl", "_advsimd_mult"))
        self.fields = {field.name: field.width for field in encoding.operands}
        self.fixed = {
            field.name: (value, field.width)
            for field in encoding.fields.values()
            if (value := encoding.fixed(field.name)) is not None
        }
        self.reg_width = 64 if encoding.base_name.split("_")[1].startswith("64") else 32
        suffix = encoding.name[len(encoding.base_name):].lstrip("_").lower()
        self.arrangement = suffix if re.fullmatch(r"(?:1|2|4|8|16)[bhsd]", suffix) else ""
        self.element = suffix[-1:] if re.fullmatch(r"(?:1|2|4|8|16)?[bhsd]", suffix) else ""
        if encoding.file.endswith("_advsimd_sngl"):
            self.element = encoding.base_name[-1]
        if encoding.file in {"and_advsimd", "orr_advsimd_reg", "eor_advsimd"}:
            self.arrangement = "16b" if suffix == "q" else "8b"
            self.element = "b"
        mnemonic = encoding.base_name.split("_")[0]
        self.access_scale = (
            1 if mnemonic in {"LDRB", "LDRSB", "STRB"}
            else 2 if mnemonic in {"LDRH", "LDRSH", "STRH"}
            else 4 if mnemonic in {"LDRSW", "LDPSW"}
            else self.reg_width // 8
        )

    def field(self, seq, name):
        if name in seq.fields:
            return seq.fields[name]
        if name in self.fixed:
            number, width = self.fixed[name]
            return seq.const(number, width)
        raise UnsupportedSyntax(f"unknown field {name}")

    def predicate(self, seq, test):
        field, *args = test
        if field == "any":
            return seq.op("orr", 1, *(self.predicate(seq, part) for part in args))
        if field == "masked_eq":
            name, mask, rhs = args
            value = self.field(seq, name)
            masked = seq.op("and", value.width, value, seq.const(mask, value.width))
            return seq.compare(masked, "eq", rhs)
        if field == "add_eq":
            name, offset, rhs = args
            left = seq.widen(self.field(seq, name))
            right = seq.widen(self.field(seq, rhs))
            return seq.compare(seq.op("add", 32, left, seq.const(offset, 32)), "eq", right)
        relation, rhs = args
        left = self.field(seq, field)
        return seq.compare(left, relation, self.field(seq, rhs) if isinstance(rhs, str) else rhs)

    def register(self, seq, prefix, field, sp=False):
        name = prefix + ("sp" if sp else "zr") if prefix in "wx" else prefix
        seq.table("regs_" + name, REGISTERS[name], self.field(seq, field))

    def operand(self, seq, part, mnemonic, overrides):
        tag = part.text
        hover = part.get("hover", "")
        if tag in overrides:
            seq.text(overrides[tag])
            return
        match = re.search(r'"(\w+)" field', hover)
        field = match[1] if match else None
        if tag in ("<Ws>", "<Xs>") and mnemonic == "ror":
            self.register(seq, tag[1].lower(), "Rn")
        elif re.fullmatch(r"<Vt[234]>", tag) and (match := re.search(r'"Rt" plus ([123]) modulo 32', hover)):
            reg = seq.widen(self.field(seq, "Rt"))
            next_reg = seq.op("add", 32, reg, seq.const(int(match[1]), 32))
            index = seq.op("and", 32, next_reg, seq.const(31, 32))
            seq.table("regs_v", REGISTERS["v"], index)
        elif field and re.fullmatch(r"<[WXVBHSDQ][a-z]\d?(?:\|W?SP)?>", tag):
            self.register(seq, tag[1].lower(), field, "SP" in tag)
        elif tag in ("<cond>", "<invcond>"):
            value = self.field(seq, "cond")
            if tag == "<invcond>":
                value = seq.op("xor", 4, value, seq.const(1, 4))
            seq.table("conditions", CONDS, value)
        elif tag == "<shift>" and "shift" in self.fields:
            seq.table("shifts", SHIFTS, self.field(seq, "shift"))
        elif tag == "<extend>" and "option" in self.fields:
            seq.table("extends", EXTENDS, self.field(seq, "option"))
        elif tag == "<shift>" and mnemonic in {"asr", "lsl", "lsr", "ror"}:
            value = self.field(seq, "imms" if mnemonic == "ror" else "immr")
            if mnemonic == "lsl":
                value = seq.op("sub", 32, seq.const(self.reg_width, 32), seq.widen(value))
            seq.decimal(value)
        elif tag in ("<lsb>", "<width>") and {"imms", "immr"} <= self.fields.keys():
            self.bitfield(seq, mnemonic, tag)
        elif tag in ("<T>", "<Ts>") and self.element:
            seq.text(self.arrangement if tag == "<T>" and self.arrangement else self.element)
        elif tag == "<V>" and self.element:
            seq.text(self.element)
        elif tag in ("<index>", "<index1>", "<index2>") and self.element and "imm5" in self.fields:
            index = ELEMENTS.index(self.element)
            index_field = "imm4" if tag == "<index2>" else "imm5"
            value = seq.widen(self.field(seq, index_field))
            shift = index if index_field == "imm4" else index + 1
            seq.decimal(seq.op("lsr", 32, value, seq.const(shift, 32)))
        elif tag == "<index>" and self.encoding.file.endswith("_advsimd_sngl"):
            value = seq.widen(self.field(seq, "Q"))
            if self.element != "d":
                value = seq.op("add", 32, seq.op("lsl", 32, value, seq.const(1, 32)),
                               seq.widen(self.field(seq, "S")))
            if self.element in "bh":
                size = seq.widen(self.field(seq, "size"))
                if self.element == "h":
                    size = seq.op("lsr", 32, size, seq.const(1, 32))
                width = 2 if self.element == "b" else 1
                value = seq.op("add", 32, seq.op("lsl", 32, value, seq.const(width, 32)), size)
            seq.decimal(value)
        elif tag == "<imm>" and "post-index immediate offset" in hover and self.arrangement:
            count = int(re.search(r"_I([1-4])_", self.encoding.base_name)[1])
            lanes = int(self.arrangement[:-1])
            size = 1 << ELEMENTS.index(self.element)
            seq.text(f"#{count * lanes * size}")
        elif tag == "<imm>" and "b5:b40" in hover:
            high = seq.widen(self.field(seq, "b5"))
            low = seq.widen(self.field(seq, "b40"))
            seq.decimal(seq.op("add", 32, seq.op("lsl", 32, high, seq.const(5, 32)), low))
        elif tag == "<label>" and (match := re.search(r'"(imm\d+)" times 4', hover)):
            seq.text("#")
            seq.decimal(self.field(seq, match[1]), signed=True, scale=4)
        elif field and (field.startswith("imm") or tag in ("<d>", "<n>", "<m>", "<t>", "<nzcv>")):
            scale_match = re.search(rf'{re.escape(tag)}/(\d+)', hover)
            scale = int(scale_match[1]) if scale_match else 1
            seq.decimal(self.field(seq, field), signed=bool(re.search(r"\bsigned\b", hover)), scale=scale)
        else:
            raise UnsupportedSyntax(f"operand {tag}")

    def bitfield(self, seq, mnemonic, tag):
        immr = seq.widen(self.field(seq, "immr"))
        imms = seq.widen(self.field(seq, "imms"))
        insert = mnemonic in {"bfi", "bfc", "sbfiz", "ubfiz"}
        if tag == "<lsb>":
            if insert:
                negated = seq.op("sub", 32, seq.const(self.reg_width, 32), immr)
                immr = seq.op("and", 32, negated, seq.const(self.reg_width - 1, 32))
            seq.decimal(immr)
        else:
            width = imms if insert else seq.op("sub", 32, imms, immr)
            seq.decimal(seq.op("add", 32, width, seq.const(1, 32)))

    def render(self, seq, mnemonic, parts, overrides):
        seq.emit("dyn_string", "mnemonic")
        parts = list(parts)
        if mnemonic.endswith("."):
            self.operand(seq, parts.pop(0), mnemonic, overrides)
        while parts and isinstance(parts[0], str) and not parts[0].strip():
            parts.pop(0)
        if parts and isinstance(parts[0], str):
            parts[0] = parts[0].lstrip()
        if parts:
            seq.emit("whitespace", "_")
        for index, part in enumerate(parts):
            if not isinstance(part, Element):
                seq.text(part)
                continue
            if part.text == "<R>":
                following = parts[index + 1]
                match = re.search(r'"(R\w+)" field', following.get("hover", ""))
                if self.element and match:
                    self.register(seq, "x" if self.element == "d" else "w", match[1])
                    overrides = overrides | {following.text: ""}
                elif "option" in self.fields and match:
                    option = self.field(seq, "option")
                    wide = seq.op("and", 3, option, seq.const(3, 3))
                    wide = seq.compare(wide, "eq", 3)
                    reg = seq.widen(self.field(seq, match[1]))
                    bank = seq.op("select", 32, wide, seq.const(32, 32), seq.const(0, 32))
                    seq.table("wx_registers", REGISTERS["wzr"] + REGISTERS["xzr"],
                              seq.op("add", 32, reg, bank))
                    overrides = overrides | {following.text: ""}
                elif "b5" in self.fields and match:
                    wide = self.field(seq, "b5")
                    reg = seq.widen(self.field(seq, match[1]))
                    bank = seq.op("select", 32, wide, seq.const(32, 32), seq.const(0, 32))
                    seq.table("wx_registers", REGISTERS["wzr"] + REGISTERS["xzr"],
                              seq.op("add", 32, reg, bank))
                    overrides = overrides | {following.text: ""}
                else:
                    raise UnsupportedSyntax("register width")
            else:
                self.operand(seq, part, mnemonic, overrides)


class Syntax:
    def __init__(self):
        self.operations = {}
        self.snippets = {}
        self.tables = {}

    def add(self, prefix, seq):
        lines = "\n".join(seq.lines) + "\n"
        key = prefix, lines
        if key not in self.snippets:
            self.snippets[key] = f"a64_{prefix}_{len(self.snippets)}"
        return self.snippets[key]

    def lower(self, form, template, tests):
        mnemonic, parts = template_parts(template, register_list=form.is_register_list)
        entries = []
        for expanded, additional, overrides in variants(form, mnemonic, parts):
            fmt = Sequence(self, form.instruction)
            form.render(fmt, mnemonic, expanded, overrides)
            cond = Sequence(self, form.instruction)
            predicates = [form.predicate(cond, test) for test in (*tests, *additional)]
            value = cond.const(1, 1) if not predicates else predicates.pop(0)
            for predicate in predicates:
                value = cond.op("and", 1, value, predicate)
            cond.emit("output", "0", value)
            entries.append(dict(mnemonic=mnemonic, condition=self.add("condition", cond),
                                syntax=self.add("syntax", fmt)))
        return entries


def attributes(items):
    return [dict(name=item.partition(".")[0], value=item.partition(".")[2]) for item in items]


def migrate(arch):
    """Convert the inline-semantics AArch64 snapshot to LIRA 9462267."""
    arch.pop("float_operations")
    for section in ("register_files", "system_registers", "environment_functions", "tables_int",
                    "tables_str", "operations", "snippets", "instructions"):
        for item in arch[section]:
            item["attributes"] = attributes(item.get("attributes", []))
            item.pop("semantic_func_128", None)
            for reg in item.get("regs", []):
                reg["attributes"] = attributes(reg["attributes"])
    arch["attributes"] = attributes(arch["attributes"])


def select_dependencies(arch):
    """Keep encoding, syntax and semantic dependencies of the selected forms."""
    snippets = {item["name"]: item for item in arch["snippets"]}
    operations = {item["name"]: item for item in arch["operations"]}
    needed_snippets = set()
    needed_ops = set()
    needed_tables = set()
    needed_str_tables = set()
    needed_envs = set()
    needed_regs = set()

    def scan(sequence):
        if " = fop " in sequence:
            raise UnsupportedSyntax("floating-point operations require a newer LIRA schema")
        for kind, name in re.findall(r"= (op|fold|alias|table|env|cond_env|read|write) (\S+)", sequence):
            name = name.rstrip(";")
            if kind in ("op", "fold") and name not in needed_ops:
                needed_ops.add(name)
                op = operations[name]
                if op.get("semantic_func"):
                    visit(op["semantic_func"])
                if op.get("semantic_table"):
                    needed_tables.add(op["semantic_table"])
            elif kind == "alias":
                visit(name)
            elif kind == "table":
                (needed_str_tables if name in string_names else needed_tables).add(name)
            elif kind in ("env", "cond_env"):
                needed_envs.add(name)
            elif kind in ("read", "write"):
                needed_regs.add(name)

    def visit(name):
        if name and name not in needed_snippets:
            needed_snippets.add(name)
            scan(snippets[name]["seq"])

    string_names = {item["name"] for item in arch["tables_str"]}
    for insn in arch["instructions"]:
        scan(insn["semantic"])
        encoding = insn["encoding"]
        for name in [*encoding["decode"], encoding["encode"], encoding["constraint_decode"],
                     encoding["constraint_encode"]]:
            visit(name)
        for entry in insn["syntaxes"]:
            visit(entry["syntax"])
            visit(entry["condition"])
    for section, names in (("snippets", needed_snippets), ("operations", needed_ops),
                           ("tables_str", needed_str_tables), ("tables_int", needed_tables),
                           ("environment_functions", needed_envs), ("register_files", needed_regs)):
        arch[section] = [item for item in arch[section] if item["name"] in names]


def in_scope(encoding):
    stem = encoding.file
    base = encoding.base_name.split("_")[0]
    if any(mark in encoding.base_name for mark in ("_asimd", "_asisd")):
        return (stem in {"ld1_advsimd_sngl", "st1_advsimd_sngl", "ld1_advsimd_mult",
                         "st1_advsimd_mult", "dup_advsimd_elt", "dup_advsimd_gen", "ins_advsimd_gen",
                         "ins_advsimd_elt", "umov_advsimd", "smov_advsimd"}
                or (base in {"ADD", "SUB", "MUL", "AND", "ORR", "EOR"}
                    and "_asimdsame_" in encoding.base_name))
    return (
        base in {"ADD", "ADDS", "SUB", "SUBS", "ADC", "ADCS", "SBC", "SBCS",
                 "AND", "ANDS", "ORR", "EOR", "BIC", "BICS", "ORN", "EON",
                 "BFM", "SBFM", "UBFM", "EXTR", "RET", "BR", "BLR", "B", "BL",
                 "CBZ", "CBNZ", "TBZ", "TBNZ", "CSEL", "CSINC", "CSINV", "CSNEG",
                 "CCMP", "CCMN", "LDR", "LDRB", "LDRH", "LDRSB", "LDRSH", "LDRSW",
                 "STR", "STRB", "STRH", "LDUR", "STUR", "LDP", "STP",
                 "MADD", "MSUB", "UDIV", "SDIV", "CLZ", "CLS", "RBIT", "REV", "REV16", "REV32"}
        and not any(mark in encoding.base_name for mark in ("_log_imm", "_ldst_", "_ldstpair_"))
    ) or (
        base in {"LDR", "LDRB", "LDRH", "LDRSB", "LDRSH", "LDRSW", "STR", "STRB", "STRH",
                 "LDUR", "STUR", "LDP", "STP"}
        and re.search(r"_(?:32|64)[A-Z]*_ldst", encoding.base_name) is not None
        and "fpsimd" not in stem
    )


def write_asm(arch, encodings, xml_dir, output):
    """Write the syntax-bearing subset for consumers of LIRA 9462267."""
    arch = to_serializable(arch)
    aliases = read_aliases(xml_dir, llvm14=True)
    syntax = Syntax()
    selected = []
    for insn in arch["instructions"]:
        encoding = encodings[insn["name"]]
        if encoding.asm_template is None or not in_scope(encoding):
            continue
        form = Form(insn, encoding)
        try:
            entries = syntax.lower(form, encoding.asm_template, ())
            alias_entries = []
            for alias in aliases.get(encoding.base_name, ()):
                alias_entries.extend(syntax.lower(form, alias.template, alias.tests))
        except UnsupportedSyntax as error:
            raise UnsupportedSyntax(f"{encoding.name}: {error}") from error
        insn["syntaxes"] = alias_entries + entries
        selected.append(insn)
    arch["instructions"] = selected
    arch["tables_str"] = [
        dict(name=name, values=values) for name, values in syntax.tables.items()
    ]
    arch["operations"].extend(syntax.operations.values())
    arch["snippets"].extend(
        dict(name=name, seq=LiteralScalarString(lines)) for (_, lines), name in syntax.snippets.items()
    )
    select_dependencies(arch)
    migrate(arch)
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    with output.open("w", encoding="utf-8") as file:
        yaml.dump(arch, file)
    print(f"{output}: {len(selected)} instructions, "
          f"{sum(len(i['syntaxes']) for i in selected)} syntax entries")
