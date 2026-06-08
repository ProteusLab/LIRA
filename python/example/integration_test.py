#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path


def _setup_imports():
    root_dir = Path(__file__).parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

_setup_imports()

from lira.ir import Shape
from lira.arch import Register, RegisterFile, EnvironmentFunction, InstructionEncoding, Operation
from lira.ir_builder import ArchBuilder, SnippetBuilder, InstructionBuilder

from lira import arch_ser_txt
from lira import arch_ser_yaml
from lira.arch_ser import SerializationFormat

def build_test_arch() -> ArchBuilder:
    registers = [Register(f"x{i}") for i in range(32)]
    rf = RegisterFile("X", [], Shape(32, None), registers)

    ld32 = EnvironmentFunction("ld32", ["mem.read"], [32], [32])
    st32 = EnvironmentFunction("st32", ["mem.write"], [32, 32], [])
    pc_read = EnvironmentFunction("pc_read", ["pc.read"], [], [32])
    pc_write = EnvironmentFunction("pc_write", ["pc.write"], [32], [])

    # ------------------------------------------------------------------
    # op_extend_sign_inner_32
    # ------------------------------------------------------------------
    snip = SnippetBuilder("op_extend_sign_inner_32")
    input_val = snip.input(0, 32)
    width_val = snip.input(1, 32)
    c32 = snip.const(32)
    delta = snip.sub(c32, width_val)
    temp = snip.lsl(input_val, delta)
    r = snip.asr(temp, delta)
    snip.output(r, 0)
    extend_sign_inner = snip.build()

    op_extend_sign = Operation(
        "extend_sign_inner_32",
        [],
        [32, 32],
        [32],
        semantic_base=None,
        semantic_func="op_extend_sign_inner_32",
    )

    # ------------------------------------------------------------------
    # op_extract_inner_32
    # ------------------------------------------------------------------
    snip = SnippetBuilder("op_extract_inner_32")
    inp = snip.input(0, 32)
    lsb = snip.input(1, 32)
    width = snip.input(2, 32)
    c32 = snip.const(32)
    t1 = snip.sub(c32, lsb)
    shift_l = snip.sub(t1, width)
    temp = snip.lsl(inp, shift_l)
    shift_r = snip.sub(c32, width)
    temp2 = snip.lsr(temp, shift_r)
    snip.output(temp2, 0)
    extract_inner_snip = snip.build()
    op_extract_inner = Operation(
        "extract_inner_32",
        [],
        [32, 32, 32],
        [32],
        semantic_base=None,
        semantic_func="op_extract_inner_32",
    )

    # ------------------------------------------------------------------
    # op_orr_shifted_32
    # ------------------------------------------------------------------
    snip = SnippetBuilder("op_orr_shifted_32")
    data = snip.input(0, 32)
    lsb = snip.input(1, 32)
    value = snip.input(2, 32)
    insert = snip.lsl(value, lsb)
    r = snip.orr(data, insert)
    snip.output(r, 0)
    orr_shifted_snip = snip.build()
    op_orr_shifted = Operation(
        "orr_shifted_32",
        [],
        [32, 32, 32],
        [32],
        semantic_base=None,
        semantic_func="op_orr_shifted_32",
    )

    # ------------------------------------------------------------------
    # decode_b_rs1, decode_b_rs2
    # ------------------------------------------------------------------
    def make_decode_extract(name: str, shift: int):
        snip = SnippetBuilder(name)
        enc = snip.input(0, 32)
        shift_const = snip.const(shift)
        shifted = snip.lsr(enc, shift_const)
        r = snip.extract_low(shifted, 5)
        snip.output(r, 0)
        return snip.build()

    decode_rs1 = make_decode_extract("decode_b_rs1", 15)
    decode_rs2 = make_decode_extract("decode_b_rs2", 20)

    # ------------------------------------------------------------------
    # decode_b_imm
    # ------------------------------------------------------------------
    snip = SnippetBuilder("decode_b_imm")
    enc = snip.input(0, 32)
    c1 = snip.const(1)
    c4 = snip.const(4)
    c5 = snip.const(5)
    c6 = snip.const(6)
    c7 = snip.const(7)
    c8 = snip.const(8)
    c11 = snip.const(11)
    c12 = snip.const(12)
    c13 = snip.const(13)
    c25 = snip.const(25)
    c31 = snip.const(31)

    t1 = snip.op(op_extract_inner, [enc, c31, c1])
    t2 = snip.op(op_extract_inner, [enc, c25, c6])
    t3 = snip.op(op_extract_inner, [enc, c8, c4])
    t4 = snip.op(op_extract_inner, [enc, c7, c1])
    t5 = snip.const(0)
    t6 = snip.op(op_orr_shifted, [t5, t1, c12])
    t7 = snip.op(op_orr_shifted, [t5, t1, c11])
    t8 = snip.op(op_orr_shifted, [t5, t1, c5])
    t9 = snip.op(op_orr_shifted, [t5, t1, c1])
    imm_sext = snip.op(op_extend_sign, [t9, c13])
    snip.output(imm_sext, 0)
    decode_imm = snip.build()

    # ------------------------------------------------------------------
    # encode_b
    # ------------------------------------------------------------------
    snip = SnippetBuilder("encode_b")
    rs1 = snip.input(0, 5)
    rs2 = snip.input(1, 5)
    imm = snip.input(2, 32)
    base = snip.dyn_const("enc_base", 32)
    c15 = snip.const(15)
    c20 = snip.const(20)
    t1 = snip.op(op_orr_shifted, [base, rs1, c15])
    t2 = snip.op(op_orr_shifted, [t1, rs2, c20])
    r = snip.orr(t2, imm)
    snip.output(r, 0)
    encode_b_snip = snip.build()

    # ------------------------------------------------------------------
    # blt
    # ------------------------------------------------------------------
    enc_blt = InstructionEncoding(
        32,
        (0b100 << 12) + 0b1100011,
        ["decode_b_rs1", "decode_b_rs2", "decode_b_imm"],
        "encode_b",
        "",
        "",
    )

    instr_builder = InstructionBuilder(
        "blt", [5, 5, 32], ["x1", "x2", "offset"], enc_blt
    )
    x1 = instr_builder.add_input_operand(0, 5)
    x2 = instr_builder.add_input_operand(1, 5)
    offset = instr_builder.add_input_operand(2, 32)
    v1 = instr_builder.read(rf, x1)
    v2 = instr_builder.read(rf, x2)
    cond = instr_builder.slt(v1, v2)
    base = instr_builder.env(pc_read, [])[0]
    dest = instr_builder.add(base, offset)
    instr_builder.cond_env(pc_write, cond, [dest], [])
    blt_instr = instr_builder.build()

    arch_builder = (
        ArchBuilder("test_arch", ["attr.1", "attr.2"])
        .add_register_file(rf)
        .add_env_func(ld32)
        .add_env_func(st32)
        .add_env_func(pc_read)
        .add_env_func(pc_write)
        .add_operation(op_extend_sign)
        .add_operation(op_extract_inner)
        .add_operation(op_orr_shifted)
        .add_snippet(extend_sign_inner)
        .add_snippet(extract_inner_snip)
        .add_snippet(orr_shifted_snip)
        .add_snippet(decode_rs1)
        .add_snippet(decode_rs2)
        .add_snippet(decode_imm)
        .add_snippet(encode_b_snip)
        .add_instruction(blt_instr)
    )
    return arch_builder


def main():
    parser = argparse.ArgumentParser(
        description="Test LIRA serialization (folder/JSON or single YAML file)"
    )
    parser.add_argument(
        "output",
        type=str,
        help="Output location: for txt format it's a directory, for yaml it's a file path"
    )
    parser.add_argument(
        "--format",
        type=SerializationFormat,
        choices=list(SerializationFormat),
        default=SerializationFormat.YAML,
        help="Serialization format"
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    arch = build_test_arch().build()

    if args.format == SerializationFormat.TXT:
        arch_ser_txt.write_arch(arch, output_path)
        arch2 = arch_ser_txt.read_arch(output_path)
    elif args.format == SerializationFormat.YAML:
        arch_ser_yaml.write_arch(arch, output_path)
        arch2 = arch_ser_yaml.read_arch(output_path)
    else:
        assert False, "Unsupported format"

    assert arch == arch2, "Integration test failed"
    print("Integration test passed successfully")


if __name__ == "__main__":
    main()
