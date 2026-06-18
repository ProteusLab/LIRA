use std::path::PathBuf;

use lira::*;

fn cross_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent().unwrap().parent().unwrap()
        .join("tests").join("cross_language")
}

fn reference() -> PathBuf {
    cross_dir().parent().unwrap().join("integration").join("reference.yaml")
}

#[test]
fn test_rust_write_and_self_read() {
    let arch = Arch::read_yaml(&reference()).unwrap();
    let out = cross_dir().join("rs_native.yaml");
    arch.write_yaml(&out).unwrap();
    let arch2 = Arch::read_yaml(&out).unwrap();
    assert_eq!(arch, arch2);
}

#[test]
fn test_rust_reads_python() {
    let py_out = cross_dir().join("py_native.yaml");
    if !py_out.exists() {
        return;
    }
    let arch = Arch::read_yaml(&py_out).unwrap();
    let tmp = cross_dir().join("rs_from_py.yaml");
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch, arch2);
    std::fs::remove_file(&tmp).ok();
}

#[test]
fn test_rust_reads_ruby() {
    let rb_out = cross_dir().join("rb_native.yaml");
    if !rb_out.exists() {
        return;
    }
    let arch = Arch::read_yaml(&rb_out).unwrap();
    let tmp = cross_dir().join("rs_from_rb.yaml");
    arch.write_yaml(&tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch, arch2);
    std::fs::remove_file(&tmp).ok();
}
