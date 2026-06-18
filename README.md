# LIRA

LIRA is a framework that provides a data-flow Intermediate Representation for optimal code generation.

**Libraries:**
- [python/lira](python/lira) — Python 3 library
- [ruby/lira](ruby/lira) — Ruby library
- [rust/lira](rust/lira) — Rust library

## Install

```bash
# Python (pip)
pip install -e python/

# Ruby (gem)
gem build ruby/lira.gemspec && gem install lira-*.gem
# or via Gemfile:
#   gem "lira", path: "ruby"

# Rust (Cargo)
cargo add --path rust/lira
```

## CPM / CMake integration

Configure and build:
```bash
cmake -B build -DLIRA_RUST=OFF
cmake --build build
```

Pull the entire project:
```cmake
include(cmake/CPM.cmake)
CPMAddPackage(
  NAME lira
  GITHUB_REPOSITORY ProteusLab/LIRA
  GIT_TAG v0.1.0
  EXCLUDE_FROM_ALL YES
  SYSTEM YES
)
# Source paths: ${LIRA_PYTHON_DIR}  ${LIRA_RUBY_DIR}  ${LIRA_RUST_DIR}
```

Sub-library selection via `OPTIONS`:
```cmake
CPMAddPackage(
  NAME lira
  GITHUB_REPOSITORY ProteusLab/LIRA
  GIT_TAG v0.1.0
  EXCLUDE_FROM_ALL YES
  OPTIONS "LIRA_RUBY OFF"
  OPTIONS "LIRA_RUST OFF"
)
# Only ${LIRA_PYTHON_DIR} and lira-python target are created
```

CMake interface targets (source-only, no compilation): `lira-python` `lira-ruby` `lira-rust`

## Examples

- [Python 3 examples](python/examples)
- [Ruby examples](ruby/examples)
- [Rust examples](rust/examples)
