use std::collections::HashMap;

use crate::*;

#[derive(Debug, Clone)]
pub struct Value {
    pub name: String,
    pub width: usize,
}

impl Value {
    pub fn new(name: String, width: usize) -> Self {
        Value { name, width }
    }
}

pub struct SeqBuilder {
    stmts: Vec<Statement>,
    temp_counter: usize,
    op_cache: HashMap<(String, Vec<usize>, Vec<usize>), Operation>,
}

impl SeqBuilder {
    pub fn new() -> Self {
        SeqBuilder {
            stmts: Vec::new(),
            temp_counter: 0,
            op_cache: HashMap::new(),
        }
    }

    fn new_temp(&mut self, width: usize) -> Value {
        self.temp_counter += 1;
        Value {
            name: format!("_t{}", self.temp_counter),
            width,
        }
    }

    fn check_width_match(&self, a: &Value, b: &Value) {
        assert_eq!(a.width, b.width, "width mismatch: {} vs {}", a.width, b.width);
    }

    pub fn ensure_width(&mut self, val: &Value, width: usize) -> Value {
        if val.width == width {
            return val.clone();
        }
        if val.width < width {
            self.extend_zero(val, width)
        } else {
            self.extract_low(val, width)
        }
    }

    fn get_or_create_op(&mut self, op: Operation) -> Operation {
        let key = (op.name.clone(), op.inputs.clone(), op.outputs.clone());
        self.op_cache.entry(key).or_insert(op).clone()
    }

    fn add_stmt(&mut self, shape: Shape, outputs: Vec<&str>, outputs_types: Vec<usize>, kind: &str, specifier: &str, inputs: Vec<&str>) {
        let stmt = Statement {
            shape,
            outputs: outputs.iter().map(|s| s.to_string()).collect(),
            outputs_types,
            kind: kind.to_string(),
            specifier: specifier.to_string(),
            inputs: inputs.iter().map(|s| s.to_string()).collect(),
        };
        self.stmts.push(stmt);
    }

    fn add_op_stmt(&mut self, op: &Operation, inputs: Vec<&str>, outputs: Vec<&str>) {
        let shape = Shape { lanes_base: 1, lanes_mult: None };
        self.add_stmt(shape, outputs, op.outputs.clone(), "op", &op.name, inputs);
    }

    pub fn op(&mut self, operation: &Operation, inputs: Vec<&Value>) -> anyhow::Result<Value> {
        anyhow::ensure!(operation.outputs.len() == 1, "expected single output, use op_multi");
        let out = self.new_temp(operation.outputs[0]);
        let op = self.get_or_create_op(operation.clone());
        self.add_op_stmt(&op, inputs.iter().map(|v| v.name.as_str()).collect(), vec![out.name.as_str()]);
        Ok(out)
    }

    pub fn op_multi(&mut self, operation: &Operation, inputs: Vec<&Value>) -> anyhow::Result<Vec<Value>> {
        let op = self.get_or_create_op(operation.clone());
        let outputs: Vec<Value> = operation.outputs.iter().map(|&w| self.new_temp(w)).collect();
        self.add_op_stmt(&op,
            inputs.iter().map(|v| v.name.as_str()).collect(),
            outputs.iter().map(|v| v.name.as_str()).collect());
        Ok(outputs)
    }

    pub fn const_(&mut self, value: usize, width: usize) -> Value {
        let out = self.new_temp(width);
        let stmt = Statement {
            shape: Shape { lanes_base: 1, lanes_mult: None },
            outputs: vec![out.name.clone()],
            outputs_types: vec![width],
            kind: "const".to_string(),
            specifier: value.to_string(),
            inputs: vec![],
        };
        self.stmts.push(stmt);
        out
    }

    pub fn dyn_const(&mut self, name: &str, width: usize) -> Value {
        let out = self.new_temp(width);
        let stmt = Statement {
            shape: Shape { lanes_base: 1, lanes_mult: None },
            outputs: vec![out.name.clone()],
            outputs_types: vec![width],
            kind: "dyn_const".to_string(),
            specifier: name.to_string(),
            inputs: vec![],
        };
        self.stmts.push(stmt);
        out
    }

    pub fn input(&mut self, idx: usize, width: usize) -> Value {
        let out = self.new_temp(width);
        let stmt = Statement {
            shape: Shape { lanes_base: 1, lanes_mult: None },
            outputs: vec![out.name.clone()],
            outputs_types: vec![width],
            kind: "input".to_string(),
            specifier: idx.to_string(),
            inputs: vec![],
        };
        self.stmts.push(stmt);
        out
    }

    pub fn output(&mut self, value: &Value, idx: usize) {
        let stmt = Statement {
            shape: Shape { lanes_base: 1, lanes_mult: None },
            outputs: vec![],
            outputs_types: vec![],
            kind: "output".to_string(),
            specifier: idx.to_string(),
            inputs: vec![value.name.clone()],
        };
        self.stmts.push(stmt);
    }

    pub fn add(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = add_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn sub(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = sub_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn mul(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = mul_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn and_(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = and_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn orr(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = orr_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn xor(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = xor_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn lsl(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = lsl_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn lsr(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = lsr_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn asr(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = asr_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn slt(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = slt_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn sle(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = sle_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn sgt(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = sgt_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn sge(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = sge_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn ult(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = ult_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn ule(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = ule_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn ugt(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = ugt_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn uge(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = uge_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn eq(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = eq_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn ne(&mut self, a: &Value, b: &Value) -> Value {
        self.check_width_match(a, b);
        let op = ne_op(a.width);
        self.op(&op, vec![a, b]).unwrap()
    }

    pub fn not(&mut self, a: &Value) -> Value {
        let op = not_op(a.width);
        self.op(&op, vec![a]).unwrap()
    }

    pub fn neg(&mut self, a: &Value) -> Value {
        let op = neg_op(a.width);
        self.op(&op, vec![a]).unwrap()
    }

    pub fn extract_low(&mut self, value: &Value, out_bits: usize) -> Value {
        let op = extract_low_op(value.width, out_bits);
        self.op(&op, vec![value]).unwrap()
    }

    pub fn extend_sign(&mut self, value: &Value, out_bits: usize) -> Value {
        let op = extend_sign_op(value.width, out_bits);
        self.op(&op, vec![value]).unwrap()
    }

    pub fn extend_zero(&mut self, value: &Value, out_bits: usize) -> Value {
        let op = extend_zero_op(value.width, out_bits);
        self.op(&op, vec![value]).unwrap()
    }

    pub fn read(&mut self, rf: &RegisterFile, reg: &Value) -> Value {
        let width = rf.reg_size.lanes_base;
        let out = self.new_temp(width);
        let stmt = Statement {
            shape: Shape { lanes_base: 1, lanes_mult: None },
            outputs: vec![out.name.clone()],
            outputs_types: vec![width],
            kind: "read".to_string(),
            specifier: rf.name.clone(),
            inputs: vec![reg.name.clone()],
        };
        self.stmts.push(stmt);
        out
    }

    pub fn write(&mut self, rf: &RegisterFile, reg: &Value, value: &Value) {
        let stmt = Statement {
            shape: Shape { lanes_base: 1, lanes_mult: None },
            outputs: vec![],
            outputs_types: vec![],
            kind: "write".to_string(),
            specifier: rf.name.clone(),
            inputs: vec![reg.name.clone(), value.name.clone()],
        };
        self.stmts.push(stmt);
    }

    pub fn env(&mut self, env_func: &EnvironmentFunction, inputs: Vec<&Value>) -> Vec<Value> {
        let outputs: Vec<Value> = env_func.outputs.iter().map(|&w| self.new_temp(w)).collect();
        let stmt = Statement {
            shape: Shape { lanes_base: 1, lanes_mult: None },
            outputs: outputs.iter().map(|v| v.name.clone()).collect(),
            outputs_types: env_func.outputs.clone(),
            kind: "env".to_string(),
            specifier: env_func.name.clone(),
            inputs: inputs.iter().map(|v| v.name.clone()).collect(),
        };
        self.stmts.push(stmt);
        outputs
    }

    pub fn cond_env(
        &mut self,
        env_func: &EnvironmentFunction,
        cond: &Value,
        inputs: Vec<&Value>,
        on_false: Vec<&Value>,
    ) -> Vec<Value> {
        let outputs: Vec<Value> = env_func.outputs.iter().map(|&w| self.new_temp(w)).collect();
        let mut all_inputs = vec![cond.name.clone()];
        all_inputs.extend(inputs.iter().map(|v| v.name.clone()));
        all_inputs.extend(on_false.iter().map(|v| v.name.clone()));
        let stmt = Statement {
            shape: Shape { lanes_base: 1, lanes_mult: None },
            outputs: outputs.iter().map(|v| v.name.clone()).collect(),
            outputs_types: env_func.outputs.clone(),
            kind: "cond_env".to_string(),
            specifier: env_func.name.clone(),
            inputs: all_inputs,
        };
        self.stmts.push(stmt);
        outputs
    }

    pub fn build(self) -> anyhow::Result<StatementSeq> {
        let mut seq = StatementSeq::default();
        for stmt in self.stmts {
            seq.try_push(stmt)?;
        }
        Ok(seq)
    }

    pub fn operations_map(&self) -> HashMap<String, Operation> {
        self.op_cache.values().map(|op| (op.name.clone(), op.clone())).collect()
    }
}

pub struct SnippetBuilder {
    pub seq: SeqBuilder,
    pub name: String,
}

impl SnippetBuilder {
    pub fn new(name: &str) -> Self {
        SnippetBuilder { seq: SeqBuilder::new(), name: name.to_string() }
    }

    pub fn build(self) -> anyhow::Result<Snippet> {
        let seq = self.seq.build()?;
        Ok(Snippet { name: self.name, seq })
    }
}

impl std::ops::Deref for SnippetBuilder {
    type Target = SeqBuilder;

    fn deref(&self) -> &Self::Target {
        &self.seq
    }
}

impl std::ops::DerefMut for SnippetBuilder {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.seq
    }
}

pub struct InstructionBuilder {
    pub seq: SeqBuilder,
    pub name: String,
    pub operand_sizes: Vec<usize>,
    pub operand_names: Vec<String>,
    pub encoding: InstructionEncoding,
}

impl InstructionBuilder {
    pub fn new(name: &str, operand_sizes: Vec<usize>, operand_names: Vec<String>, encoding: InstructionEncoding) -> Self {
        InstructionBuilder {
            seq: SeqBuilder::new(),
            name: name.to_string(),
            operand_sizes,
            operand_names,
            encoding,
        }
    }

    pub fn add_input_operand(&mut self, idx: usize, width: usize) -> Value {
        self.seq.input(idx, width)
    }

    pub fn build(self) -> anyhow::Result<Instruction> {
        let seq = self.seq.build()?;
        Ok(Instruction {
            name: self.name,
            attributes: vec![],
            operand_sizes: self.operand_sizes,
            operand_names: self.operand_names,
            encoding: self.encoding,
            semantic: seq,
        })
    }
}

impl std::ops::Deref for InstructionBuilder {
    type Target = SeqBuilder;

    fn deref(&self) -> &Self::Target {
        &self.seq
    }
}

impl std::ops::DerefMut for InstructionBuilder {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.seq
    }
}

#[derive(Default)]
pub struct ArchBuilder {
    pub name: String,
    pub attributes: Vec<String>,
    pub register_files: Vec<RegisterFile>,
    pub system_registers: Vec<SystemRegister>,
    pub environment_functions: Vec<EnvironmentFunction>,
    pub tables_int: Vec<TableInt>,
    pub operations: Vec<Operation>,
    pub snippets: Vec<Snippet>,
    pub instructions: Vec<Instruction>,
}

impl ArchBuilder {
    pub fn new(name: &str, attributes: Vec<String>) -> Self {
        ArchBuilder {
            name: name.to_string(),
            attributes,
            ..Default::default()
        }
    }

    pub fn add_register_file(&mut self, rf: RegisterFile) -> &mut Self {
        self.register_files.push(rf);
        self
    }

    pub fn add_system_register(&mut self, sr: SystemRegister) -> &mut Self {
        self.system_registers.push(sr);
        self
    }

    pub fn add_env_func(&mut self, env: EnvironmentFunction) -> &mut Self {
        self.environment_functions.push(env);
        self
    }

    pub fn add_table_int(&mut self, table: TableInt) -> &mut Self {
        self.tables_int.push(table);
        self
    }

    pub fn add_operation(&mut self, op: Operation) -> &mut Self {
        self.operations.push(op);
        self
    }

    pub fn add_snippet(&mut self, snippet: Snippet) -> &mut Self {
        self.snippets.push(snippet);
        self
    }

    pub fn add_instruction(&mut self, instr: Instruction) -> &mut Self {
        self.instructions.push(instr);
        self
    }

    pub fn build(self) -> Arch {
        Arch {
            name: self.name,
            attributes: self.attributes,
            register_files: self.register_files,
            system_registers: self.system_registers,
            environment_functions: self.environment_functions,
            tables_int: self.tables_int,
            operations: self.operations,
            snippets: self.snippets,
            instructions: self.instructions,
        }
    }
}
