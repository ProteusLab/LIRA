cmake_minimum_required(VERSION 3.14)
project(LIRA
  VERSION 0.1.0
  DESCRIPTION "LIRA is a framework that provides a data-flow Intermediate Representation."
  LANGUAGES NONE
)

if(CMAKE_CURRENT_SOURCE_DIR STREQUAL CMAKE_SOURCE_DIR)
  include(${CMAKE_CURRENT_LIST_DIR}/cmake/CPM.cmake)
endif()

option(LIRA_PYTHON "Include Python LIRA library" ON)
option(LIRA_RUBY   "Include Ruby LIRA library"   ON)
option(LIRA_RUST   "Include Rust LIRA library"   ON)

set(LIRA_PYTHON_DIR "${CMAKE_CURRENT_LIST_DIR}/python/lira" CACHE PATH "LIRA Python library path")
set(LIRA_RUBY_DIR   "${CMAKE_CURRENT_LIST_DIR}/ruby/lira"   CACHE PATH "LIRA Ruby library path")
set(LIRA_RUST_DIR   "${CMAKE_CURRENT_LIST_DIR}/rust/lira"   CACHE PATH "LIRA Rust library path")

if(LIRA_PYTHON)
  if(NOT TARGET lira-python)
    add_library(lira-python INTERFACE)
    target_compile_definitions(lira-python INTERFACE
      LIRA_PYTHON_DIR="${LIRA_PYTHON_DIR}")
  endif()
endif()

if(LIRA_RUBY)
  if(NOT TARGET lira-ruby)
    add_library(lira-ruby INTERFACE)
    target_compile_definitions(lira-ruby INTERFACE
      LIRA_RUBY_DIR="${LIRA_RUBY_DIR}")
  endif()
endif()

if(LIRA_RUST)
  if(NOT TARGET lira-rust)
    add_library(lira-rust INTERFACE)
    target_compile_definitions(lira-rust INTERFACE
      LIRA_RUST_DIR="${LIRA_RUST_DIR}")
  endif()
endif()
