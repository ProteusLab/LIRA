"""Read preferred syntax from selected Arm A64 alias descriptions."""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Union
from xml.etree.ElementTree import Element, parse


Test = tuple[Union[str, int, "Test"], ...]


@dataclass(frozen=True)
class Alias:
    template: Element
    tests: tuple[Test, ...]
    priority: int


ALIAS_FILES = (
    "cmp_subs_addsub_ext",
    "cmp_subs_addsub_imm",
    "cmp_subs_addsub_shift",
    "cmn_adds_addsub_ext",
    "cmn_adds_addsub_imm",
    "cmn_adds_addsub_shift",
    "mov_orr_log_shift",
    "mov_orr_advsimd_reg",
    "mov_ins_advsimd_elt",
    "mov_ins_advsimd_gen",
    "mov_add_addsub_imm",
    "mov_dup_advsimd_elt",
    "mov_umov_advsimd",
    "mul_madd",
    "mneg_msub",
    "mvn_orn_log_shift",
    "tst_ands_log_shift",
    "tst_ands_log_imm",
    "neg_sub_addsub_shift",
    "negs_subs_addsub_shift",
    "ngc_sbc",
    "ngcs_sbcs",
    "ror_extr",
    "cset_csinc",
    "csetm_csinv",
    "cinc_csinc",
    "cinv_csinv",
    "cneg_csneg",
    "bfc_bfm",
    "bfi_bfm",
    "bfxil_bfm",
    "asr_sbfm",
    "sxtb_sbfm",
    "sxth_sbfm",
    "sxtw_sbfm",
    "sbfiz_sbfm",
    "sbfx_sbfm",
    "lsr_ubfm",
    "uxtb_ubfm",
    "uxth_ubfm",
    "lsl_ubfm",
    "ubfiz_ubfm",
    "ubfx_ubfm",
)
OPERATORS = {"==": "eq", "!=": "ne", "<": "ult", "<=": "ule", ">": "ugt", ">=": "uge"}


def diagram_fields(diagram: Element) -> dict[str, str]:
    return {
        box.attrib["name"]: "".join(cell.text or "x" for cell in box)
        for box in diagram.findall("box[@name]")
    }


def masked_test(field: str, bits: str) -> Test:
    mask = int("".join("0" if bit == "x" else "1" for bit in bits), 2)
    return ("masked_eq", field, mask, int(bits.replace("x", "0"), 2))


def implies(stronger: Test, weaker: Test) -> bool:
    _, field, mask, value = weaker
    if len(stronger) == 3:
        lhs, operator, rhs = stronger
        return lhs == field and operator == "eq" and isinstance(rhs, int) and rhs & mask == value
    if stronger[0] == "masked_eq":
        _, lhs, lhs_mask, rhs = stronger
        return lhs == field and lhs_mask & mask == mask and rhs & mask == value
    return False


def diagram_tests(alias: Element, base: Element) -> tuple[Test, ...]:
    base_fields = diagram_fields(base)
    tests = []
    for field, bits in diagram_fields(alias).items():
        if bits == base_fields.get(field):
            continue
        if re.fullmatch(r"[01]+", bits):
            tests.append((field, "eq", int(bits, 2)))
        elif re.fullmatch(r"!= [01]+", bits):
            tests.append((field, "ne", int(bits[3:], 2)))
        elif re.fullmatch(r"!= 1+x+", bits):
            tests.append((field, "ult", int(bits[3:].replace("x", "0"), 2)))
        elif re.fullmatch(r"[01x]+", bits) and any(bit != "x" for bit in bits):
            tests.append(masked_test(field, bits))
        else:
            raise ValueError(f"Unsupported alias bit pattern for {field}: {bits!r}")
    return tuple(tests)


def condition_tests(condition: str) -> tuple[Test, ...]:
    if condition == "Unconditionally":
        return ()
    if condition == "BFXPreferred(sf, opc[1], imms, immr)":
        # The preceding shift and extend aliases cover the more specific cases.
        return (("imms", "uge", "immr"),)
    if condition == "UInt(imms) + 1 == UInt(immr)":
        return (("add_eq", "imms", 1, "immr"),)
    if "||" in condition:
        return (("any", *(condition_tests(branch.strip())[0] for branch in condition.split("||"))),)
    tests = []
    for test in condition.split("&&"):
        test = re.sub(r"UInt\((\w+)\)", r"\1", test.strip())
        field, operator, operand = test.split()
        if operator == "==" and re.fullmatch(r"[01x]+", operand) and "x" in operand:
            tests.append(masked_test(field, operand))
            continue
        if operand.startswith("'") and operand.endswith("'"):
            operand = int(operand[1:-1], 2)
        elif len(operand) > 1 and re.fullmatch(r"[01]+", operand):
            operand = int(operand, 2)
        elif operand.isdecimal():
            operand = int(operand)
        elif not operand.isidentifier():
            raise ValueError(f"Unsupported alias condition: {test}")
        tests.append((field, OPERATORS[operator], operand))
    return tuple(tests)


def read_aliases(xml_dir: Path, *, llvm14: bool = False) -> dict[str, list[Alias]]:
    aliases = defaultdict(list)
    for priority, filename in enumerate(ALIAS_FILES):
        if llvm14 and filename == "bfc_bfm":
            continue
        alias = parse(xml_dir / f"{filename}.xml").getroot()
        base = parse(xml_dir / alias.find("aliasto").attrib["refiform"]).getroot()
        base_classes = {
            encoding.attrib["name"]: (instruction_class.find("regdiagram"), encoding)
            for instruction_class in base.findall("classes/iclass")
            for encoding in instruction_class.findall("encoding")
        }
        for instruction_class in alias.findall("classes/iclass"):
            for encoding in instruction_class.findall("encoding"):
                equivalent = encoding.find("equivalent_to")
                href = equivalent.find("asmtemplate/a").attrib["href"]
                base_name = href.split("#", 1)[1]
                base_diagram, base_encoding = base_classes[base_name]
                variant_tests = condition_tests(encoding.get("bitdiffs", "Unconditionally"))
                base_tests = set(condition_tests(base_encoding.get("bitdiffs", "Unconditionally")))
                tests = diagram_tests(instruction_class.find("regdiagram"), base_diagram)
                tests += variant_tests
                tests += condition_tests(equivalent.findtext("aliascond"))
                tests = tuple(dict.fromkeys(
                    test for test in tests
                    if test not in base_tests and not (
                        test[0] == "masked_eq" and any(
                            other != test and implies(other, test)
                            for other in (*tests, *base_tests)
                        )
                    )
                ))
                if llvm14 and filename == "bfi_bfm":
                    # LLVM 14 uses BFI for the BFC encoding as well.
                    tests = tuple(test for test in tests if test != ("Rn", "ne", 31))
                aliases[base_name].append(Alias(encoding.find("asmtemplate"), tests, priority))
    return dict(aliases)
