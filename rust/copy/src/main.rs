fn main() -> anyhow::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    assert!(args.len() == 3, "Usage: copy <INPUT> <OUTPUT>");
    lira::Arch::read_yaml(&args[1])?.write_yaml(&args[2])
}
