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

find_package(OpenSSL 3.0 REQUIRED COMPONENTS Crypto)

set(
  OTRL_TAPE_SOURCES
  parity/src/status.c
  parity/src/checked_arithmetic.c
  parity/src/sha256_adapter.c
  parity/src/canonical_json_adapter.c
  parity/src/tape_reader.c
  parity/src/tape_writer.c
  parity/src/comparator.c
  parity/src/minimizer.c
  parity/src/field_schema.c
)

add_library(otrl_tape STATIC ${OTRL_TAPE_SOURCES})
target_include_directories(
  otrl_tape
  PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/parity/include"
  PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/parity/src"
)
target_compile_definitions(otrl_tape PRIVATE _POSIX_C_SOURCE=200809L)
target_link_libraries(otrl_tape PUBLIC OpenSSL::Crypto)
p0_configure_c17_target(otrl_tape)

add_executable(tape parity/tools/tape_main.c)
target_include_directories(tape PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/parity/src")
target_compile_definitions(tape PRIVATE _POSIX_C_SOURCE=200809L _XOPEN_SOURCE=700)
target_link_libraries(tape PRIVATE otrl_tape)
p0_configure_c17_target(tape)

if(P0_ENABLE_FUZZING)
  set(
    OTRL_FUZZ_TARGETS
    fuzz_tape_prefix
    fuzz_tape_header
    fuzz_tape_records
    fuzz_projection_payload
    fuzz_full_tape
    fuzz_command_input
    fuzz_field_schema_json
    fuzz_manifest_json
    fuzz_comparator_pair
    fuzz_minimizer_pair
  )
  set(_otrl_fuzz_mode 0)
  foreach(_otrl_fuzz_target IN LISTS OTRL_FUZZ_TARGETS)
    add_executable("${_otrl_fuzz_target}" parity/tests/fuzz/fuzz_entry.c ${OTRL_TAPE_SOURCES})
    target_include_directories(
      "${_otrl_fuzz_target}"
      PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/parity/src"
        "${CMAKE_CURRENT_SOURCE_DIR}/parity/include"
    )
    target_compile_definitions("${_otrl_fuzz_target}" PRIVATE "FUZZ_MODE=${_otrl_fuzz_mode}")
    target_compile_definitions("${_otrl_fuzz_target}" PRIVATE _POSIX_C_SOURCE=200809L)
    target_link_libraries("${_otrl_fuzz_target}" PRIVATE OpenSSL::Crypto)
    p0_configure_fuzz_target("${_otrl_fuzz_target}")
    math(EXPR _otrl_fuzz_mode "${_otrl_fuzz_mode} + 1")
  endforeach()
endif()

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

  add_executable(p004_unit parity/tests/unit/tape_unit.c)
  target_include_directories(p004_unit PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/parity/src")
  target_link_libraries(p004_unit PRIVATE otrl_tape)
  p0_configure_c17_target(p004_unit)
  add_test(NAME p004_unit COMMAND p004_unit)
  set_tests_properties(p004_unit PROPERTIES LABELS "p0;port004;unit;offline" TIMEOUT 60)

  add_executable(p004_abi_c parity/tests/unit/abi_c.c)
  target_link_libraries(p004_abi_c PRIVATE otrl_tape)
  p0_configure_c17_target(p004_abi_c)
  add_test(NAME p004_abi_c COMMAND p004_abi_c)
  set_tests_properties(p004_abi_c PROPERTIES LABELS "p0;port004;abi;offline" TIMEOUT 60)

  add_executable(p004_fault_inject parity/tools/fault_inject_main.c)
  target_include_directories(
    p004_fault_inject PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/parity/src"
  )
  target_compile_definitions(p004_fault_inject PRIVATE _POSIX_C_SOURCE=200809L)
  target_link_libraries(p004_fault_inject PRIVATE otrl_tape)
  target_link_options(
    p004_fault_inject PRIVATE
      -Wl,--wrap=write
      -Wl,--wrap=fsync
      -Wl,--wrap=close
      -Wl,--wrap=link
      -Wl,--wrap=unlink
  )
  p0_configure_c17_target(p004_fault_inject)
  add_test(NAME p004_fault_inject COMMAND p004_fault_inject)
  set_tests_properties(
    p004_fault_inject
    PROPERTIES LABELS "p0;port004;fault-injection;offline" TIMEOUT 60
  )

  add_test(
    NAME p004_contract
    COMMAND "${P0_TOOLS_PYTHON}"
            "${CMAKE_CURRENT_SOURCE_DIR}/parity/tests/integration/test_port004.py"
            --tape "$<TARGET_FILE:tape>"
  )
  set_tests_properties(
    p004_contract
    PROPERTIES LABELS "p0;port004;contract;offline" RUN_SERIAL TRUE TIMEOUT 300
  )
endif()
