$LOAD_PATH.unshift(File.expand_path('../..', __dir__))
require 'lira'
require 'minitest/autorun'

include Lira

PROJECT_ROOT = File.expand_path('../../..', __dir__)
REFERENCE = File.join(PROJECT_ROOT, 'tests', 'integration', 'reference.yaml')
CANONICALIZE = File.join(PROJECT_ROOT, 'tools', 'yaml_canonicalize.py')
OUTPUT = File.join(__dir__, 'integration.yaml')

class TestIntegration < Minitest::Test
  def test_roundtrip_from_reference
    ref_arch = ArchSerYaml.read_arch(REFERENCE)

    raw = "#{OUTPUT}.raw"
    begin
      ArchSerYaml.write_arch(ref_arch, raw)
      system('python3', CANONICALIZE, raw, OUTPUT)
      File.delete(raw)

      arch2 = ArchSerYaml.read_arch(OUTPUT)
      assert_equal ref_arch, arch2, 'round-trip equality failed'
    ensure
      File.delete(raw) if File.exist?(raw)
    end
  end
end
