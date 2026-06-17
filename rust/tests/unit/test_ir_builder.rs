use lira::*;

mod test_seq_builder {
    use super::*;

    #[test]
    fn test_const() {
        let mut seq = SeqBuilder::new();
        let v = seq.const_(42, 32);
        assert_eq!(v.width, 32);
        assert!(v.name.starts_with("_t"));
    }

    #[test]
    fn test_add_sub_mul() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(3, 32);
        let b = seq.const_(2, 32);
        assert_eq!(seq.add(&a, &b).width, 32);
        assert_eq!(seq.sub(&a, &b).width, 32);
        assert_eq!(seq.mul(&a, &b).width, 32);
    }

    #[test]
    fn test_bitwise_ops() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(0xFF, 32);
        let b = seq.const_(0x0F, 32);
        assert_eq!(seq.and_(&a, &b).width, 32);
        assert_eq!(seq.orr(&a, &b).width, 32);
        assert_eq!(seq.xor(&a, &b).width, 32);
    }

    #[test]
    fn test_shift_ops() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(1, 32);
        let b = seq.const_(4, 32);
        assert_eq!(seq.lsl(&a, &b).width, 32);
        assert_eq!(seq.lsr(&a, &b).width, 32);
        assert_eq!(seq.asr(&a, &b).width, 32);
    }

    #[test]
    fn test_slt() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(10, 32);
        let b = seq.const_(20, 32);
        let r = seq.slt(&a, &b);
        assert_eq!(r.width, 1);
    }

    #[test]
    fn test_extract_low() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(0xFF, 32);
        let r = seq.extract_low(&a, 8);
        assert_eq!(r.width, 8);
    }

    #[test]
    fn test_extend_sign() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(1, 8);
        let r = seq.extend_sign(&a, 32);
        assert_eq!(r.width, 32);
    }

    #[test]
    fn test_extend_zero() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(1, 8);
        let r = seq.extend_zero(&a, 32);
        assert_eq!(r.width, 32);
    }

    #[test]
    fn test_input_output() {
        let mut seq = SeqBuilder::new();
        let inp = seq.input(0, 32);
        seq.output(&inp, 0);
        let s = seq.build().unwrap();
        assert_eq!(s[0].kind, "input");
        assert_eq!(s[1].kind, "output");
    }

    #[test]
    fn test_ensure_width_extend() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(1, 8);
        let r = seq.ensure_width(&a, 32);
        assert_eq!(r.width, 32);
    }

    #[test]
    fn test_ensure_width_extract() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(1, 32);
        let r = seq.ensure_width(&a, 8);
        assert_eq!(r.width, 8);
    }

    #[test]
    fn test_ensure_width_identity() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(42, 32);
        let r = seq.ensure_width(&a, 32);
        assert_eq!(r.name, a.name);
    }

    #[test]
    fn test_operations_map() {
        let mut seq = SeqBuilder::new();
        let a = seq.const_(1, 32);
        let b = seq.const_(2, 32);
        seq.add(&a, &b);
        seq.sub(&a, &b);
        seq.slt(&a, &b);
        let omap = seq.operations_map();
        assert!(omap.contains_key("add_32"));
        assert!(omap.contains_key("slt_32"));
    }

    fn test_rf() -> RegisterFile {
        RegisterFile {
            name: "XRegs".into(), attributes: vec![],
            reg_size: Shape { lanes_base: 32, lanes_mult: None },
            regs: vec![Register { name: "x0".into(), attributes: vec![] }],
        }
    }

    #[test]
    fn test_read_write() {
        let rf = test_rf();
        let mut seq = SeqBuilder::new();
        let reg = seq.input(0, 5);
        let v = seq.read(&rf, &reg);
        assert_eq!(v.width, 32);
        seq.write(&rf, &reg, &v);
        let s = seq.build().unwrap();
        let kinds: Vec<&str> = s.iter().map(|st| st.kind.as_str()).collect();
        assert!(kinds.contains(&"read"));
        assert!(kinds.contains(&"write"));
    }

    #[test]
    fn test_env() {
        let get_pc = EnvironmentFunction { name: "getPC".into(), attributes: vec![], inputs: vec![], outputs: vec![32] };
        let mut seq = SeqBuilder::new();
        let result = seq.env(&get_pc, vec![]);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].width, 32);
    }

    #[test]
    fn test_cond_env() {
        let write_mem = EnvironmentFunction { name: "writeMem32".into(), attributes: vec![], inputs: vec![32, 32], outputs: vec![] };
        let mut seq = SeqBuilder::new();
        let cond = seq.const_(1, 1);
        let addr = seq.const_(100, 32);
        let fallback = seq.const_(200, 32);
        let result = seq.cond_env(&write_mem, &cond, vec![&addr], vec![&fallback]);
        assert_eq!(result.len(), 0);
    }
}

mod test_snippet_builder {
    use super::*;

    #[test]
    fn test_build_snippet() {
        let mut sb = SnippetBuilder::new("test");
        let a = sb.input(0, 32);
        sb.output(&a, 0);
        let snip = sb.build().unwrap();
        assert_eq!(snip.name, "test");
        assert_eq!(snip.seq.len(), 2);
    }

    #[test]
    fn test_build_decode() {
        let mut sb = SnippetBuilder::new("decode_rs2");
        let enc = sb.input(0, 32);
        let shift = sb.const_(20, 32);
        let shifted = sb.lsr(&enc, &shift);
        let r = sb.extract_low(&shifted, 5);
        sb.output(&r, 0);
        let snip = sb.build().unwrap();
        assert_eq!(snip.seq.len(), 5);
    }

    #[test]
    fn test_build_constraint() {
        let mut sb = SnippetBuilder::new("constraint");
        let enc = sb.input(0, 32);
        let mask = sb.const_(0xFF, 32);
        let masked = sb.and_(&enc, &mask);
        let expected = sb.const_(0x33, 32);
        let ok = sb.slt(&masked, &expected);
        sb.output(&ok, 0);
        let snip = sb.build().unwrap();
        assert_eq!(snip.seq.len(), 6);
    }
}

mod test_instruction_builder {
    use super::*;

    fn test_rf() -> RegisterFile {
        RegisterFile {
            name: "XRegs".into(), attributes: vec![],
            reg_size: Shape { lanes_base: 32, lanes_mult: None },
            regs: (0..32).map(|i| Register { name: format!("x{i}"), attributes: vec![] }).collect(),
        }
    }

    #[test]
    fn test_build_add() {
        let rf = test_rf();
        let enc = InstructionEncoding {
            encoded_size: 32, const_encoding_part: 51, const_mask: 0,
            decode: vec![], encode: String::new(),
            constraint_decode: String::new(), constraint_encode: String::new(),
        };
        let mut ib = InstructionBuilder::new("add", vec![5, 5, 5], vec!["rd".into(), "rs1".into(), "rs2".into()], enc);
        let rd = ib.add_input_operand(0, 5);
        let rs1 = ib.add_input_operand(1, 5);
        let rs2 = ib.add_input_operand(2, 5);
        let v1 = ib.read(&rf, &rs1);
        let v2 = ib.read(&rf, &rs2);
        let r = ib.add(&v1, &v2);
        ib.write(&rf, &rd, &r);
        let instr = ib.build().unwrap();
        assert_eq!(instr.name, "add");
        assert_eq!(instr.semantic.len(), 7);
    }

    #[test]
    fn test_build_ecall() {
        let syscall = EnvironmentFunction { name: "sysCall".into(), attributes: vec![], inputs: vec![], outputs: vec![] };
        let enc = InstructionEncoding {
            encoded_size: 32, const_encoding_part: 115, const_mask: 0,
            decode: vec![], encode: String::new(),
            constraint_decode: String::new(), constraint_encode: String::new(),
        };
        let mut ib = InstructionBuilder::new("ecall", vec![], vec![], enc);
        ib.env(&syscall, vec![]);
        let instr = ib.build().unwrap();
        assert_eq!(instr.name, "ecall");
        assert_eq!(instr.semantic[0].kind, "env");
    }
}

mod test_arch_builder {
    use super::*;

    #[test]
    fn test_build_arch() {
        let rf = RegisterFile {
            name: "X".into(), attributes: vec![],
            reg_size: Shape { lanes_base: 32, lanes_mult: None },
            regs: vec![Register { name: "x0".into(), attributes: vec![] }],
        };
        let mut ab = ArchBuilder::new("test", vec!["attr".into()]);
        ab.add_register_file(rf);
        let arch = ab.build();
        assert_eq!(arch.name, "test");
        assert_eq!(arch.register_files.len(), 1);
    }

    #[test]
    fn test_add_env_operation_snippet() {
        let mut ab = ArchBuilder::new("test", vec![]);
        let env = EnvironmentFunction { name: "ld".into(), attributes: vec!["mem".into()], inputs: vec![32], outputs: vec![32] };
        let op = add_op(32);
        let mut sb = SnippetBuilder::new("s1");
        let a = sb.input(0, 32);
        sb.output(&a, 0);
        let snip = sb.build().unwrap();
        ab.add_env_func(env).add_operation(op).add_snippet(snip);
        let arch = ab.build();
        assert_eq!(arch.environment_functions.len(), 1);
        assert_eq!(arch.operations.len(), 1);
        assert_eq!(arch.snippets.len(), 1);
    }
}
