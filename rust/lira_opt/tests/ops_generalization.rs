use lira::{Arch, Snippet, StatementSeq};

#[test]
fn operations() -> anyhow::Result<()> {
    let mut arch = Arch::default();

    let generic = StatementSeq::parse(
        "\
1 8 a = get a;
1 8 b = get b;
1 1 c = op.g sgt a b;
1 8 d = op.g select c a b;
",
    )
    .unwrap();
    let specialized = StatementSeq::parse(
        "\
1 8 a = get a;
1 8 b = get b;
1 1 c = op sgt_8 a b;
1 8 d = op select_8 c a b;
",
    )
    .unwrap();

    arch.snippets.push(Snippet {
        name: "s".to_string(),
        seq: generic.clone(),
    });
    let mut arch = lira_opt::Arch(arch);
    arch.specialize_operations()?;

    assert_eq!(arch.0.operations.len(), 2);
    assert_eq!(arch.0.operations[0].name, "sgt_8");
    assert_eq!(arch.0.operations[0].semantic_base.as_ref().unwrap(), "sgt");
    assert_eq!(arch.0.operations[1].name, "select_8");

    assert_eq!(arch.0.snippets.len(), 1);
    assert_eq!(arch.0.snippets[0].seq, specialized);

    arch.generalize_operations();

    assert_eq!(arch.0.snippets.len(), 1);
    assert_eq!(arch.0.snippets[0].seq, generic);

    Ok(())
}
