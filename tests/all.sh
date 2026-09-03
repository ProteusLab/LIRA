#!/bin/bash
set -ex

echo "=== Python tests ==="
pytest python/tests/unit/ -v
pytest --cov=python/lira python/tests/unit/ --cov-report=term
bash tests/round_trip.sh "python python/tests/integration/copy_.py"

echo "=== Ruby tests ==="
ruby -I ruby -I ruby/lib ruby/tests/unit/test_ir_ser_txt.rb
ruby -I ruby -I ruby/lib ruby/tests/unit/test_arch_ser_yaml.rb
ruby -I ruby -I ruby/lib ruby/tests/unit/test_ir_builder.rb
ruby -r simplecov -I ruby -I ruby/lib -e 'SimpleCov.start; Dir["ruby/tests/unit/*.rb"].each { |f| require_relative f }'
bash tests/round_trip.sh "ruby ruby/tests/integration/copy.rb"

echo "=== Rust tests ==="
cargo test --manifest-path rust/Cargo.toml
bash tests/round_trip.sh "cargo run --manifest-path rust/Cargo.toml --bin copy --"
