use std::path::PathBuf;

use lira::*;

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

fn tmp_dir() -> PathBuf {
    let dir = project_root().join("tmp");
    std::fs::create_dir_all(&dir).ok();
    dir
}

fn reference() -> PathBuf {
    project_root()
        .join("tests")
        .join("integration")
        .join("reference.yaml")
}

#[test]
fn test_rust_write_and_self_read() {
    let arch = Arch::read_yaml(&reference()).unwrap();
    let out = tmp_dir().join("rs_native.yaml");
    copy::copy_arch(&reference(), &out).unwrap();
    let arch2 = Arch::read_yaml(&out).unwrap();
    assert_eq!(arch, arch2);
}

#[test]
fn test_rust_reads_python() {
    let py_out = tmp_dir().join("py_native.yaml");
    if !py_out.exists() {
        return;
    }
    let arch = Arch::read_yaml(&py_out).unwrap();
    let tmp = tmp_dir().join("rs_from_py.yaml");
    copy::copy_arch(&py_out, &tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch, arch2);
    std::fs::remove_file(&tmp).ok();
}

#[test]
fn test_rust_reads_ruby() {
    let rb_out = tmp_dir().join("rb_native.yaml");
    if !rb_out.exists() {
        return;
    }
    let arch = Arch::read_yaml(&rb_out).unwrap();
    let tmp = tmp_dir().join("rs_from_rb.yaml");
    copy::copy_arch(&rb_out, &tmp).unwrap();
    let arch2 = Arch::read_yaml(&tmp).unwrap();
    assert_eq!(arch, arch2);
    std::fs::remove_file(&tmp).ok();
}
