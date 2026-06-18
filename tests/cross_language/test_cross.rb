$LOAD_PATH.unshift(File.expand_path('../../ruby', __dir__))
$LOAD_PATH.unshift(File.expand_path('../..', __dir__))
require 'lira'
require 'minitest/autorun'

include Lira

CROSS_DIR = File.expand_path(__dir__)
REFERENCE = File.join(CROSS_DIR, '..', 'integration', 'reference.yaml')

RB_OUT = File.join(CROSS_DIR, 'rb_native.yaml')
PY_OUT = File.join(CROSS_DIR, 'py_native.yaml')
RS_OUT = File.join(CROSS_DIR, 'rs_native.yaml')

class TestCrossLanguage < Minitest::Test
  def test_ruby_write_and_self_read
    arch = ArchSerYaml.read_arch(REFERENCE)
    ArchSerYaml.write_arch(arch, RB_OUT)
    arch2 = ArchSerYaml.read_arch(RB_OUT)
    assert_equal arch, arch2
  end

  def test_ruby_reads_python
    skip('py_native.yaml not found') unless File.exist?(PY_OUT)
    arch = ArchSerYaml.read_arch(PY_OUT)
    ArchSerYaml.write_arch(arch, File.join(CROSS_DIR, 'rb_from_py.yaml'))
    arch2 = ArchSerYaml.read_arch(File.join(CROSS_DIR, 'rb_from_py.yaml'))
    assert_equal arch, arch2
  end

  def test_ruby_reads_rust
    skip('rs_native.yaml not found') unless File.exist?(RS_OUT)
    arch = ArchSerYaml.read_arch(RS_OUT)
    ArchSerYaml.write_arch(arch, File.join(CROSS_DIR, 'rb_from_rs.yaml'))
    arch2 = ArchSerYaml.read_arch(File.join(CROSS_DIR, 'rb_from_rs.yaml'))
    assert_equal arch, arch2
  end
end
