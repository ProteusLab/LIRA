use std::path::PathBuf;
use lira::*;

use std::sync::atomic::{AtomicUsize, Ordering};

static TMP_COUNTER: AtomicUsize = AtomicUsize::new(0);

fn temp_yaml() -> (PathBuf, impl FnOnce()) {
    let n = TMP_COUNTER.fetch_add(1, Ordering::SeqCst);
    let p = std::env::temp_dir().join(format!("lira_test_{}_{}.yaml", std::process::id(), n));
    let p2 = p.clone();
    (p, move || { std::fs::remove_file(&p2).ok(); })
}

#[test]
fn test_minimal_arch_with_builder() {
    let rf = RegisterFile {
        name: "X".into(), attributes: vec![],
        reg_size: Shape { lanes_base: 32, lanes_mult: None },
        regs: vec![Register { name: "x0".into(), attributes: vec![] }, Register { name: "x1".into(), attributes: vec![] }],
    };
    let mut ab = ArchBuilder::new("minimal", vec![]);
    ab.add_register_file(rf);
    let mut sb = SnippetBuilder::new("s");
    let a = sb.input(0, 32);
    sb.output(&a, 0);
    ab.add_snippet(sb.build().unwrap());
    let arch = ab.build();
    let (tmp, cleanup) = temp_yaml();
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch, arch2);
    cleanup();
}

#[test]
fn test_instruction_via_builder() {
    let rf = RegisterFile {
        name: "X".into(), attributes: vec![],
        reg_size: Shape { lanes_base: 32, lanes_mult: None },
        regs: vec![Register { name: "x0".into(), attributes: vec![] }],
    };
    let enc = InstructionEncoding {
        encoded_size: 32, const_encoding_part: 0, const_mask: 0,
        decode: vec![], encode: String::new(),
        constraint_decode: String::new(), constraint_encode: String::new(),
    };
    let mut ib = InstructionBuilder::new("test", vec![5, 5], vec!["rs1".into(), "rs2".into()], enc);
    let rs1 = ib.add_input_operand(0, 5);
    let rs2 = ib.add_input_operand(1, 5);
    let v = ib.read(&rf, &rs1);
    ib.write(&rf, &rs2, &v);
    let instr = ib.build().unwrap();
    let mut ab = ArchBuilder::new("w_instr", vec![]);
    ab.add_register_file(rf);
    ab.add_instruction(instr);
    let arch = ab.build();
    let (tmp, cleanup) = temp_yaml();
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch, arch2);
    cleanup();
}

#[test]
fn test_null_fields_roundtrip() {
    let mut op = add_op(32);
    op.semantic_base = None;
    op.semantic_func = None;
    let mut ab = ArchBuilder::new("null_test", vec![]);
    ab.add_operation(op);
    let arch = ab.build();
    let (tmp, cleanup) = temp_yaml();
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch2.operations[0].semantic_base, None);
    cleanup();
}

#[test]
fn test_register_attributes() {
    let rf = RegisterFile {
        name: "R".into(), attributes: vec![],
        reg_size: Shape { lanes_base: 32, lanes_mult: None },
        regs: vec![Register { name: "x0".into(), attributes: vec!["zero".into()] }, Register { name: "x1".into(), attributes: vec![] }],
    };
    let mut ab = ArchBuilder::new("attrs", vec![]);
    ab.add_register_file(rf);
    let arch = ab.build();
    let (tmp, cleanup) = temp_yaml();
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch2.register_files[0].regs[0].attributes, vec!["zero"]);
    cleanup();
}

#[test]
fn test_system_register() {
    let field = SystemRegisterField { name: "f".into(), attributes: vec![], lsb: 0, msb: 7 };
    let sr = SystemRegister { name: "csr".into(), attributes: vec![], size: 32, fields: vec![field] };
    let mut ab = ArchBuilder::new("sysreg", vec![]);
    ab.add_system_register(sr);
    let arch = ab.build();
    let (tmp, cleanup) = temp_yaml();
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch2.system_registers[0].fields[0].lsb, 0);
    cleanup();
}

#[test]
fn test_table_int() {
    let table = TableInt { name: "t".into(), attributes: vec![], values: vec![1, 2, 3] };
    let mut ab = ArchBuilder::new("tbl", vec![]);
    ab.add_table_int(table);
    let arch = ab.build();
    let (tmp, cleanup) = temp_yaml();
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch2.tables_int[0].values, vec![1, 2, 3]);
    cleanup();
}

#[test]
fn test_rv32i_lite_roundtrip() {
    let rf = RegisterFile {
        name: "XRegs".into(), attributes: vec![],
        reg_size: Shape { lanes_base: 32, lanes_mult: None },
        regs: {
            let mut regs: Vec<Register> = (0..32).map(|i| Register { name: format!("x{i}"), attributes: vec![] }).collect();
            regs[0].attributes = vec!["zero".into()];
            regs
        },
    };

    let mut ab = ArchBuilder::new("rv32i_lite", vec![]);
    ab.add_register_file(rf.clone());

    let syscall = EnvironmentFunction { name: "sysCall".into(), attributes: vec![], inputs: vec![], outputs: vec![] };
    let read_mem = EnvironmentFunction { name: "readMem16".into(), attributes: vec![], inputs: vec![32], outputs: vec![16] };
    let get_pc = EnvironmentFunction { name: "getPC".into(), attributes: vec![], inputs: vec![], outputs: vec![32] };
    let set_pc = EnvironmentFunction { name: "setPC".into(), attributes: vec![], inputs: vec![32], outputs: vec![] };
    ab.add_env_func(syscall.clone()).add_env_func(read_mem).add_env_func(get_pc).add_env_func(set_pc);

    ab.add_operation(add_op(32));
    ab.add_operation(lsr_op(32));
    ab.add_operation(lsl_op(32));

    let mut sb = SnippetBuilder::new("decode_0");
    let enc = sb.input(0, 32);
    let c7 = sb.const_(7, 32);
    let shifted = sb.lsr(&enc, &c7);
    let low5 = sb.extract_low(&shifted, 5);
    let extended = sb.extend_zero(&low5, 32);
    sb.output(&extended, 0);
    ab.add_snippet(sb.build().unwrap());

    let enc = InstructionEncoding {
        encoded_size: 32, const_encoding_part: 51, const_mask: 0,
        decode: vec![], encode: String::new(),
        constraint_decode: String::new(), constraint_encode: String::new(),
    };
    let mut ib = InstructionBuilder::new("add", vec![32, 32, 32], vec!["rs2".into(), "rs1".into(), "rd".into()], enc);
    let rs2 = ib.add_input_operand(0, 32);
    let rs1 = ib.add_input_operand(1, 32);
    let rd = ib.add_input_operand(2, 32);
    let v1 = ib.read(&rf, &rs1);
    let v2 = ib.read(&rf, &rs2);
    let r = ib.add(&v1, &v2);
    ib.write(&rf, &rd, &r);
    ab.add_instruction(ib.build().unwrap());

    let enc = InstructionEncoding {
        encoded_size: 32, const_encoding_part: 115, const_mask: 0,
        decode: vec![], encode: String::new(),
        constraint_decode: String::new(), constraint_encode: String::new(),
    };
    let mut ib = InstructionBuilder::new("ecall", vec![], vec![], enc);
    ib.env(&syscall, vec![]);
    ab.add_instruction(ib.build().unwrap());

    let arch = ab.build();
    let (tmp, cleanup) = temp_yaml();
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch, arch2);
    cleanup();
}
