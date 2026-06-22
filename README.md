# LIRA

LIRA is a framework that provides a data-flow Intermediate Representation.

**Libraries:**
- [python/lira](python/lira) — Python 3 library
- [ruby/lira](ruby/lira) — Ruby library
- [rust/lira](rust/lira) — Rust library

## Install

- Python (pip):
```bash
pip install -e python/
```

- Ruby (gem)
```bash
gem build ruby/lira.gemspec && gem install lira-*.gem
# or via Gemfile:
#   gem "lira", path: "ruby"
```
- Rust (Cargo)
```bash
cargo add --path rust/lira
```

## Examples

- [Python 3 examples](python/examples)
- [Ruby examples](ruby/examples)
- [Rust examples](rust/examples)
