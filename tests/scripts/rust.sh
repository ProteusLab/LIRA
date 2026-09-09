#!/bin/bash
set -ex

echo "=== Rust tests ==="
cargo test --manifest-path rust/Cargo.toml
bash tests/scripts/round_trip.sh "cargo run --manifest-path rust/Cargo.toml --bin copy --"
