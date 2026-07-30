include_guard(GLOBAL)

# P0 release evidence uses Clang source-based coverage. Keeping this helper
# target-scoped permits small test binaries to opt in without instrumenting the
# pinned OpenTTD source tree or unrelated dependencies.
function(p0_enable_coverage target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "p0_enable_coverage: unknown target '${target}'")
  endif()
  if(NOT P0_ENABLE_COVERAGE)
    return()
  endif()
  if(NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "P0 source-based coverage requires the versioned Clang profile")
  endif()

  target_compile_options(
    "${target}"
    PRIVATE
      $<$<COMPILE_LANGUAGE:C>:-fprofile-instr-generate>
      $<$<COMPILE_LANGUAGE:C>:-fcoverage-mapping>
  )
  get_target_property(_p0_target_type "${target}" TYPE)
  if(_p0_target_type MATCHES "^(EXECUTABLE|SHARED_LIBRARY|MODULE_LIBRARY)$")
    target_link_options(
      "${target}"
      PRIVATE
        "-fprofile-instr-generate"
        "-fcoverage-mapping"
    )
  endif()
endfunction()
