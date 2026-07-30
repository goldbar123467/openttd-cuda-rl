include_guard(GLOBAL)

function(p0_enable_sanitizers target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "p0_enable_sanitizers: unknown target '${target}'")
  endif()

  if(NOT P0_ENABLE_ASAN AND NOT P0_ENABLE_UBSAN)
    return()
  endif()

  if(NOT CMAKE_C_COMPILER_ID MATCHES "^(GNU|Clang)$")
    message(FATAL_ERROR "P0 sanitizers require GCC or Clang")
  endif()

  set(_p0_sanitizers)
  if(P0_ENABLE_ASAN)
    list(APPEND _p0_sanitizers address)
  endif()
  if(P0_ENABLE_UBSAN)
    list(APPEND _p0_sanitizers undefined)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang")
      list(APPEND _p0_sanitizers implicit-conversion)
    endif()
  endif()
  list(JOIN _p0_sanitizers "," _p0_sanitizer_list)

  target_compile_options(
    "${target}"
    PRIVATE
      $<$<COMPILE_LANGUAGE:C>:-fsanitize=${_p0_sanitizer_list}>
      $<$<COMPILE_LANGUAGE:C>:-fno-sanitize-recover=all>
      $<$<COMPILE_LANGUAGE:C>:-fno-omit-frame-pointer>
      $<$<COMPILE_LANGUAGE:C>:-fno-optimize-sibling-calls>
  )
  if(P0_ENABLE_ASAN)
    target_compile_options(
      "${target}"
      PRIVATE $<$<COMPILE_LANGUAGE:C>:-fsanitize-address-use-after-scope>
    )
  endif()
  get_target_property(_p0_target_type "${target}" TYPE)
  if(_p0_target_type MATCHES "^(EXECUTABLE|SHARED_LIBRARY|MODULE_LIBRARY)$")
    target_link_options(
      "${target}"
      PRIVATE
        "-fsanitize=${_p0_sanitizer_list}"
        "-fno-sanitize-recover=all"
        "-fno-omit-frame-pointer"
    )
  endif()
endfunction()

# The clang-fuzz profile is deliberately one reviewed combination:
# libFuzzer + ASan + UBSan, fail-fast recovery policy, and frame pointers.
function(p0_enable_fuzzing target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "p0_enable_fuzzing: unknown target '${target}'")
  endif()
  if(NOT P0_ENABLE_FUZZING)
    return()
  endif()
  if(NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "P0 libFuzzer targets require the versioned Clang profile")
  endif()

  get_target_property(_p0_target_type "${target}" TYPE)
  if(NOT _p0_target_type STREQUAL "EXECUTABLE")
    message(FATAL_ERROR "p0_enable_fuzzing: '${target}' must be an executable target")
  endif()

  set(_p0_fuzz_sanitizers "fuzzer,address,undefined,implicit-conversion")
  target_compile_options(
    "${target}"
    PRIVATE
      $<$<COMPILE_LANGUAGE:C>:-fsanitize=${_p0_fuzz_sanitizers}>
      $<$<COMPILE_LANGUAGE:C>:-fno-sanitize-recover=all>
      $<$<COMPILE_LANGUAGE:C>:-fno-omit-frame-pointer>
      $<$<COMPILE_LANGUAGE:C>:-fno-optimize-sibling-calls>
      $<$<COMPILE_LANGUAGE:C>:-fsanitize-address-use-after-scope>
  )
  target_link_options(
    "${target}"
    PRIVATE
      "-fsanitize=${_p0_fuzz_sanitizers}"
      "-fno-sanitize-recover=all"
      "-fno-omit-frame-pointer"
  )
endfunction()
