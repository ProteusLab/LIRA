use std::path::PathBuf;

use lira::*;

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent().unwrap()
        .parent().unwrap()
        .to_path_buf()
}

#[test]
fn test_roundtrip_from_reference() {
    let ref_path = project_root().join("tests").join("integration").join("reference.yaml");
    let ref_arch = Arch::read_yaml(&ref_path).unwrap();

    let output = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("integration").join("integration.yaml");
    std::fs::create_dir_all(output.parent().unwrap()).ok();
    let raw = output.with_extension("raw.yaml");

    ref_arch.write_yaml(&raw).unwrap();
    let canonicalize = project_root().join("tools").join("yaml_canonicalize.py");
    std::process::Command::new("python3")
        .arg(&canonicalize).arg(&raw).arg(&output)
        .status().unwrap();
    std::fs::remove_file(&raw).ok();

    let arch2 = Arch::read_yaml(&output).unwrap();
    assert_eq!(ref_arch, arch2);
}
