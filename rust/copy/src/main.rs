fn main() -> anyhow::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    assert!(args.len() == 3, "Usage: copy <INPUT> <OUTPUT>");
    copy::copy_arch(std::path::Path::new(&args[1]), std::path::Path::new(&args[2]))
}
