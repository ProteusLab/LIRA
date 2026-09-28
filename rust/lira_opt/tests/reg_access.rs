use lira::{Arch, RegisterFile, Shape, StatementSeq};

#[test]
fn writes_merging() -> anyhow::Result<()> {
    let input_head = "\
1 5 r1 = input 0;
1 5 r2 = input 1;
1 5 z = input 2;
1 5 t = input 3;
1 1 c = input 4;
1 5 c5_0 = const 0;
1 5 c5_1 = const 1;
1 5 c5_2 = const 2;
1 5 c5_3 = const 3;
1 5 r1_2 = op.g add r1 c5_2;
1 5 r1_3 = op.g add r1 c5_3;
1 5 r2_1 = op.g add r2 c5_1;
1 16 x = op.g extend_zero r1;
1 64 y = op.g add z t;
1 5 r2_0 = op.g add r2 c5_0;
1 5 r2_0_ = op.g add r2 c5_0;
";

    let input_body1 = "\
1 = write G r1_2 y;
1 = write G r1_3 y;
1 = write G r1_2 z;
1 = write G r2_1 t;
1 = cond.write G c r2_1 t;
1 = write G r1_3 t;
";
    //     let input_body2 = "\
    // 1 = write G r1_2 z;
    // 1 = write G r1_3 y;
    // 1 = write G r2_1 t;
    // 1 = write G r1_3 t;
    // ";
    // let expected = [
    //     "1 = write G r1_2 z;",
    //     "1 = write G r1_3 y;",
    //     "1 = write G r2_1 t;",
    //     "1 = write G r1_3 t;",
    // ];
    let expected = [
        // _ra_w_22 = select 1 z y
        "1 = cond.write G _ra_w_12 r1_2 _ra_w_22",
        "1 = cond.write G _ra_w_01 r1_3 y",
        // _ra_w_14 = orr _ra_w_03 (=1) c
        "1 = cond.write G _ra_w_14 r2_1 _ra_w_24",
        "1 = cond.write G _ra_w_05 r1_3 t",
    ];

    let input = StatementSeq::parse(&format!("{input_head}\n{input_body1}"))?;
    // let expected = StatementSeq::parse(&format!("{input_head}\n{input_body2}"))?;

    let mut arch = Arch::default();
    arch.register_files.push(RegisterFile {
        name: "G".to_string(),
        attributes: vec![],
        reg_size: Shape::new(64, None),
        regs: vec![],
    });
    let got = lira_opt::optimize_reg_writes(&input, &arch.build_index_all())?;

    for stmt in got.iter() {
        eprintln!("{stmt};");
    }

    let writes: Vec<_> = got
        .iter()
        .map(|stmt| stmt.to_string())
        .filter(|stmt| stmt.contains("write"))
        .collect();

    anyhow::ensure!(writes == expected, "{writes:?} != {expected:?}");

    Ok(())
}
