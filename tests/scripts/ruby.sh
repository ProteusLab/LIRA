#!/bin/bash
set -ex

echo "=== Ruby tests ==="
ruby -I ruby -I ruby/lib ruby/tests/unit/test_ir_ser_txt.rb
ruby -I ruby -I ruby/lib ruby/tests/unit/test_arch_ser_yaml.rb
ruby -I ruby -I ruby/lib ruby/tests/unit/test_ir_builder.rb
ruby -r simplecov -I ruby -I ruby/lib -e 'SimpleCov.start; Dir["ruby/tests/unit/*.rb"].each { |f| require_relative f }'
bash tests/scripts/round_trip.sh "ruby ruby/tests/integration/copy.rb"
ruby -I ruby -I ruby/lib ruby/tests/integration/test_integration.rb
