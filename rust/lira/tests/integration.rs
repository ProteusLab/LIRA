use std::path::PathBuf;

use lira::*;

fn find_tools_dir() -> PathBuf {
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let project_root = crate_dir.parent().unwrap().parent().unwrap();
    project_root.join("tools")
}

fn build_test_arch() -> anyhow::Result<Arch> {
    let registers: Vec<Register> = (0..32).map(|i| Register {
        name: format!("x{i}"),
        attributes: vec![],
    }).collect();
    let rf = RegisterFile {
        name: "X".to_string(),
        attributes: vec![],
        reg_size: Shape { lanes_base: 32, lanes_mult: None },
        regs: registers,
    };

    let ld32 = EnvironmentFunction {
        name: "ld32".to_string(),
        attributes: vec!["mem.read".to_string()],
        inputs: vec![32],
        outputs: vec![32],
    };
    let st32 = EnvironmentFunction {
        name: "st32".to_string(),
        attributes: vec!["mem.write".to_string()],
        inputs: vec![32, 32],
        outputs: vec![],
    };
    let pc_read = EnvironmentFunction {
        name: "pc_read".to_string(),
        attributes: vec!["pc.read".to_string()],
        inputs: vec![],
        outputs: vec![32],
    };
    let pc_write = EnvironmentFunction {
        name: "pc_write".to_string(),
        attributes: vec!["pc.write".to_string()],
        inputs: vec![32],
        outputs: vec![],
    };

    let op_extend_sign = Operation {
        name: "extend_sign_inner_32".to_string(),
        attributes: vec![],
        inputs: vec![32, 32],
        outputs: vec![32],
        semantic_base: None,
        semantic_func: Some("op_extend_sign_inner_32".to_string()),
        semantic_func_128: None,
        semantic_table: None,
    };

    let op_extract_inner = Operation {
        name: "extract_inner_32".to_string(),
        attributes: vec![],
        inputs: vec![32, 32, 32],
        outputs: vec![32],
        semantic_base: None,
        semantic_func: Some("op_extract_inner_32".to_string()),
        semantic_func_128: None,
        semantic_table: None,
    };

    let op_orr_shifted = Operation {
        name: "orr_shifted_32".to_string(),
        attributes: vec![],
        inputs: vec![32, 32, 32],
        outputs: vec![32],
        semantic_base: None,
        semantic_func: Some("op_orr_shifted_32".to_string()),
        semantic_func_128: None,
        semantic_table: None,
    };

    let mut snip = SnippetBuilder::new("op_extend_sign_inner_32");
    let input_val = snip.input(0, 32);
    let width_val = snip.input(1, 32);
    let c32 = snip.const_(32, 32);
    let delta = snip.sub(&c32, &width_val);
    let temp = snip.lsl(&input_val, &delta);
    let r = snip.asr(&temp, &delta);
    snip.output(&r, 0);
    let extend_sign_inner = snip.build()?;

    let mut snip = SnippetBuilder::new("op_extract_inner_32");
    let inp = snip.input(0, 32);
    let lsb = snip.input(1, 32);
    let width = snip.input(2, 32);
    let c32 = snip.const_(32, 32);
    let t1 = snip.sub(&c32, &lsb);
    let shift_l = snip.sub(&t1, &width);
    let temp = snip.lsl(&inp, &shift_l);
    let shift_r = snip.sub(&c32, &width);
    let temp2 = snip.lsr(&temp, &shift_r);
    snip.output(&temp2, 0);
    let extract_inner_snip = snip.build()?;

    let mut snip = SnippetBuilder::new("op_orr_shifted_32");
    let data = snip.input(0, 32);
    let lsb = snip.input(1, 32);
    let value = snip.input(2, 32);
    let insert = snip.lsl(&value, &lsb);
    let r = snip.orr(&data, &insert);
    snip.output(&r, 0);
    let orr_shifted_snip = snip.build()?;

    fn make_decode_extract(name: &str, shift: usize) -> anyhow::Result<Snippet> {
        let mut snip = SnippetBuilder::new(name);
        let enc = snip.input(0, 32);
        let shift_const = snip.const_(shift, 32);
        let shifted = snip.lsr(&enc, &shift_const);
        let r = snip.extract_low(&shifted, 5);
        snip.output(&r, 0);
        snip.build()
    }

    let decode_rs1 = make_decode_extract("decode_b_rs1", 15)?;
    let decode_rs2 = make_decode_extract("decode_b_rs2", 20)?;

    let mut snip = SnippetBuilder::new("decode_b_imm");
    let enc = snip.input(0, 32);
    let c1 = snip.const_(1, 32);
    let c4 = snip.const_(4, 32);
    let c5 = snip.const_(5, 32);
    let c6 = snip.const_(6, 32);
    let c7 = snip.const_(7, 32);
    let c8 = snip.const_(8, 32);
    let c11 = snip.const_(11, 32);
    let c12 = snip.const_(12, 32);
    let c13 = snip.const_(13, 32);
    let c25 = snip.const_(25, 32);
    let c31 = snip.const_(31, 32);

    let t1 = snip.op(&op_extract_inner, vec![&enc, &c31, &c1])?;
    let _t2 = snip.op(&op_extract_inner, vec![&enc, &c25, &c6])?;
    let _t3 = snip.op(&op_extract_inner, vec![&enc, &c8, &c4])?;
    let _t4 = snip.op(&op_extract_inner, vec![&enc, &c7, &c1])?;
    let t5 = snip.const_(0, 32);
    let _t6 = snip.op(&op_orr_shifted, vec![&t5, &t1, &c12])?;
    let _t7 = snip.op(&op_orr_shifted, vec![&t5, &t1, &c11])?;
    let _t8 = snip.op(&op_orr_shifted, vec![&t5, &t1, &c5])?;
    let t9 = snip.op(&op_orr_shifted, vec![&t5, &t1, &c1])?;
    let imm_sext = snip.op(&op_extend_sign, vec![&t9, &c13])?;
    snip.output(&imm_sext, 0);
    let decode_imm = snip.build()?;

    let mut snip = SnippetBuilder::new("encode_b");
    let rs1 = snip.input(0, 5);
    let rs2 = snip.input(1, 5);
    let imm = snip.input(2, 32);
    let base = snip.dyn_const("enc_base", 32);
    let c15 = snip.const_(15, 32);
    let c20 = snip.const_(20, 32);
    let t1 = snip.op(&op_orr_shifted, vec![&base, &rs1, &c15])?;
    let t2 = snip.op(&op_orr_shifted, vec![&t1, &rs2, &c20])?;
    let r = snip.orr(&t2, &imm);
    snip.output(&r, 0);
    let encode_b_snip = snip.build()?;

    let enc_blt = InstructionEncoding {
        encoded_size: 32,
        const_encoding_part: (0b100 << 12) + 0b1100011,
        decode: vec!["decode_b_rs1".to_string(), "decode_b_rs2".to_string(), "decode_b_imm".to_string()],
        encode: "encode_b".to_string(),
        constraint_decode: String::new(),
        constraint_encode: String::new(),
    };

    let mut instr_builder = InstructionBuilder::new(
        "blt",
        vec![5, 5, 32],
        vec!["x1".to_string(), "x2".to_string(), "offset".to_string()],
        enc_blt,
    );
    let x1 = instr_builder.add_input_operand(0, 5);
    let x2 = instr_builder.add_input_operand(1, 5);
    let offset = instr_builder.add_input_operand(2, 32);
    let v1 = instr_builder.read(&rf, &x1);
    let v2 = instr_builder.read(&rf, &x2);
    let cond = instr_builder.slt(&v1, &v2);
    let base = instr_builder.env(&pc_read, vec![]);
    let dest = instr_builder.add(&base[0], &offset);
    instr_builder.cond_env(&pc_write, &cond, vec![&dest], vec![]);
    let blt_instr = instr_builder.build()?;

    let mut arch_builder = ArchBuilder::new("test_arch", vec!["attr.1".to_string(), "attr.2".to_string()]);
    arch_builder.add_register_file(rf);
    arch_builder.add_env_func(ld32).add_env_func(st32).add_env_func(pc_read).add_env_func(pc_write);
    arch_builder.add_operation(op_extend_sign).add_operation(op_extract_inner).add_operation(op_orr_shifted);
    arch_builder.add_snippet(extend_sign_inner).add_snippet(extract_inner_snip).add_snippet(orr_shifted_snip);
    arch_builder.add_snippet(decode_rs1).add_snippet(decode_rs2).add_snippet(decode_imm).add_snippet(encode_b_snip);
    arch_builder.add_instruction(blt_instr);

    Ok(arch_builder.build())
}

#[test]
fn integration() -> anyhow::Result<()> {
    let arch = build_test_arch()?;

    let output = PathBuf::from("lira.yaml");
    let raw = PathBuf::from("lira.raw.yaml");
    arch.write_yaml(&raw)?;

    let canonicalize = find_tools_dir().join("yaml_canonicalize.py");
    std::process::Command::new("python3")
        .arg(canonicalize)
        .arg(&raw)
        .arg(&output)
        .status()?;
    std::fs::remove_file(&raw)?;

    let arch2 = Arch::read_yaml(&output)?;

    assert_eq!(arch, arch2);
    Ok(())
}
