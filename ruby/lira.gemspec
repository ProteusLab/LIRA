require_relative 'lib/lira/version'

Gem::Specification.new do |spec|
  spec.name          = "lira"
  spec.version       = Lira::VERSION
  spec.authors       = ["ProteusLab"]
  spec.summary       = "LIRA is a framework that provides a data-flow Intermediate Representation."
  spec.description   = "LIRA data-flow IR library for building, manipulating, and serializing instruction-set architecture descriptions."

  spec.required_ruby_version = ">= 3.0"

  spec.files = Dir["lira.rb", "lira/**/*.rb", "lib/**/*.rb"]
  spec.require_paths = ["."]

  spec.add_dependency "yaml"
end
