use std::path::Path;

pub fn copy_arch(src: &Path, dst: &Path) -> anyhow::Result<()> {
    lira::Arch::read_yaml(src)?.write_yaml(dst)
}
