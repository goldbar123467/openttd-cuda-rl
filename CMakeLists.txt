cmake_minimum_required(VERSION 3.28...3.28)

project(
  openttd_p0_oracle_contract
  VERSION 0.1.0
  DESCRIPTION "Strict native tooling for the OpenTTD P0 oracle contract"
  LANGUAGES C
)

include(CTest)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
include(P0Warnings)
include(P0Sanitizers)
include(P0Coverage)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(P0_ENABLE_ASAN "Instrument configured P0 native targets with AddressSanitizer" OFF)
option(P0_ENABLE_UBSAN "Instrument configured P0 native targets with UndefinedBehaviorSanitizer" OFF)
option(P0_ENABLE_COVERAGE "Instrument configured P0 native targets for Clang source-based coverage" OFF)
option(P0_ENABLE_FUZZING "Enable libFuzzer instrumentation on explicit P0 fuzz targets" OFF)

if(P0_ENABLE_COVERAGE AND (P0_ENABLE_ASAN OR P0_ENABLE_UBSAN OR P0_ENABLE_FUZZING))
  message(FATAL_ERROR "P0 coverage must use a build tree separate from sanitizer and fuzz profiles")
endif()

if(P0_ENABLE_FUZZING AND (P0_ENABLE_ASAN OR P0_ENABLE_UBSAN))
  message(FATAL_ERROR "P0 fuzz targets supply their own ASan+UBSan instrumentation")
endif()

p0_reject_forbidden_build_flags()
p0_enable_deterministic_c_archives()

# Apply this function only to native targets owned by the P0 oracle contract.
# Untouched OpenTTD targets deliberately remain outside this policy boundary.
function(p0_configure_c17_target target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "p0_configure_c17_target: unknown target '${target}'")
  endif()

  get_target_property(_p0_target_type "${target}" TYPE)
  if(_p0_target_type STREQUAL "INTERFACE_LIBRARY" OR _p0_target_type STREQUAL "UTILITY")
    message(FATAL_ERROR "p0_configure_c17_target: '${target}' must be a compiled native target")
  endif()

  set_target_properties(
    "${target}"
    PROPERTIES
      C_STANDARD 17
      C_STANDARD_REQUIRED ON
      C_EXTENSIONS OFF
      INTERPROCEDURAL_OPTIMIZATION OFF
  )
  p0_enable_strict_warnings("${target}")
  p0_enable_sanitizers("${target}")
  p0_enable_coverage("${target}")
endfunction()

# Fuzz executables opt in separately so libFuzzer's main function is never
# linked into production tools or ordinary unit-test executables.
function(p0_configure_fuzz_target target)
  if(NOT P0_ENABLE_FUZZING)
    message(FATAL_ERROR "p0_configure_fuzz_target requires P0_ENABLE_FUZZING=ON")
  endif()

  p0_configure_c17_target("${target}")
  p0_enable_fuzzing("${target}")
endfunction()

if(BUILD_TESTING)
  set(P0_TOOLS_PYTHON "$ENV{P0_TOOLS_PYTHON}" CACHE FILEPATH "Hash-locked P0 Python interpreter")
  if(P0_TOOLS_PYTHON STREQUAL "")
    find_program(P0_TOOLS_PYTHON NAMES python3 REQUIRED)
  endif()
  if(NOT IS_ABSOLUTE "${P0_TOOLS_PYTHON}" OR NOT EXISTS "${P0_TOOLS_PYTHON}")
    message(FATAL_ERROR "P0_TOOLS_PYTHON must name an existing absolute interpreter path")
  endif()

  add_test(
    NAME p001_contract
    COMMAND
      "${CMAKE_CURRENT_SOURCE_DIR}/scripts/ci/p001_contract_tests.sh"
      --tools-python "${P0_TOOLS_PYTHON}"
      --schedule-seed 1785314342
  )
  set_tests_properties(
    p001_contract
    PROPERTIES
      LABELS "p0;port001;contract;offline"
      RUN_SERIAL TRUE
      TIMEOUT 900
  )

  add_test(
    NAME p001_comparator
    COMMAND
      "${P0_TOOLS_PYTHON}"
      "${CMAKE_CURRENT_SOURCE_DIR}/oracle/tests/port001/port001_comparator_tests.py"
      --repository-root "${CMAKE_CURRENT_SOURCE_DIR}"
  )
  set_tests_properties(
    p001_comparator
    PROPERTIES
      LABELS "p0;port001;comparator;offline"
      RUN_SERIAL TRUE
      TIMEOUT 120
  )
endif()
