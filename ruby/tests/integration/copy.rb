$LOAD_PATH.unshift(File.expand_path('../..', __dir__))
require 'lira'
include Lira

if ARGV.length != 2
  $stderr.puts "Usage: #{$0} <input.yaml> <output.yaml>"
  exit 1
end

ArchSerYaml.copy_arch(ARGV[0], ARGV[1])
