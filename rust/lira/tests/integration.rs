use std::path::PathBuf;

use lira::*;

#[test]
fn integration() {
    let input = std::env::var("LIRA_TEST_INTEGRATION_INPUT");
    let output = std::env::var("LIRA_TEST_INTEGRATION_INPUT");
    assert!(input.is_ok(), "please pass paths through env");
    let input = PathBuf::from(input.unwrap());
    let output = PathBuf::from(output.unwrap());

    // Compare to python-generated
    let arch = Arch::read_from_file(&input).unwrap();
    arch.write_to_file(&output).unwrap();
    // Round trip
    let arch2 = Arch::read_from_file(&output).unwrap();

    assert_eq!(arch.register_files, arch2.register_files);
    assert_eq!(arch.system_registers, arch2.system_registers);
    assert_eq!(arch.environment_functions, arch2.environment_functions);
    assert_eq!(arch.tables_int, arch2.tables_int);
    assert_eq!(arch.operations, arch2.operations);
    assert_eq!(arch.snippets, arch2.snippets);
    assert_eq!(arch.instructions, arch2.instructions);
    assert_eq!(arch, arch2);
}
