include_guard(GLOBAL)

# Fail closed if behavior-affecting flags prohibited by the P0 contract are
# injected through a preset, command line, or environment-derived cache value.
function(p0_reject_forbidden_build_flags)
  set(_p0_flag_variables
    CMAKE_C_FLAGS
    CMAKE_C_FLAGS_DEBUG
    CMAKE_C_FLAGS_RELEASE
    CMAKE_C_FLAGS_RELWITHDEBINFO
    CMAKE_C_FLAGS_MINSIZEREL
    CMAKE_EXE_LINKER_FLAGS
    CMAKE_SHARED_LINKER_FLAGS
    CMAKE_MODULE_LINKER_FLAGS
  )
  set(_p0_forbidden_patterns
    "(^|[ ;])-ffast-math($|[ ;])"
    "(^|[ ;])-Ofast($|[ ;])"
    "(^|[ ;])-flto([^ ;]*)($|[ ;])"
    "(^|[ ;])-march=[^ ;]+($|[ ;])"
    "(^|[ ;])-mcpu=[^ ;]+($|[ ;])"
    "(^|[ ;])-mtune=[^ ;]+($|[ ;])"
  )

  foreach(_p0_variable IN LISTS _p0_flag_variables)
    if(DEFINED ${_p0_variable})
      foreach(_p0_pattern IN LISTS _p0_forbidden_patterns)
        if(" ${${_p0_variable}} " MATCHES "${_p0_pattern}")
          message(FATAL_ERROR
            "P0 parity build forbids '${CMAKE_MATCH_0}' in ${_p0_variable}")
        endif()
      endforeach()
    endif()
  endforeach()

  set(_p0_ipo_variables
    CMAKE_INTERPROCEDURAL_OPTIMIZATION
    CMAKE_INTERPROCEDURAL_OPTIMIZATION_DEBUG
    CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE
    CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELWITHDEBINFO
    CMAKE_INTERPROCEDURAL_OPTIMIZATION_MINSIZEREL
  )
  foreach(_p0_variable IN LISTS _p0_ipo_variables)
    if(DEFINED ${_p0_variable} AND ${_p0_variable})
      message(FATAL_ERROR
        "P0 parity builds forbid link-time/interprocedural optimization via ${_p0_variable}")
    endif()
  endforeach()
endfunction()

# GNU ar and LLVM ar both accept D to force deterministic archive member
# metadata. The frozen GCC and Clang profiles use one of those implementations.
function(p0_enable_deterministic_c_archives)
  if(NOT CMAKE_C_COMPILER_ID MATCHES "^(GNU|Clang)$")
    message(FATAL_ERROR "P0 deterministic archives require the frozen GCC or Clang profile")
  endif()

  set(CMAKE_C_ARCHIVE_CREATE
    "<CMAKE_AR> qcD <TARGET> <LINK_FLAGS> <OBJECTS>"
    PARENT_SCOPE
  )
  set(CMAKE_C_ARCHIVE_APPEND
    "<CMAKE_AR> qD <TARGET> <LINK_FLAGS> <OBJECTS>"
    PARENT_SCOPE
  )
  set(CMAKE_C_ARCHIVE_FINISH
    "<CMAKE_RANLIB> -D <TARGET>"
    PARENT_SCOPE
  )
endfunction()

# Warnings are intentionally target-scoped: callers must opt in each new P0 C
# target, and no warning policy leaks into the pinned OpenTTD submodule.
function(p0_enable_strict_warnings target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "p0_enable_strict_warnings: unknown target '${target}'")
  endif()

  if(NOT CMAKE_C_COMPILER_ID MATCHES "^(GNU|Clang)$")
    message(FATAL_ERROR
      "P0 strict warnings support only the frozen GCC and Clang profiles; got '${CMAKE_C_COMPILER_ID}'")
  endif()

  target_compile_options(
    "${target}"
    PRIVATE
      $<$<COMPILE_LANGUAGE:C>:-Wall>
      $<$<COMPILE_LANGUAGE:C>:-Wextra>
      $<$<COMPILE_LANGUAGE:C>:-Wpedantic>
      $<$<COMPILE_LANGUAGE:C>:-Wconversion>
      $<$<COMPILE_LANGUAGE:C>:-Wsign-conversion>
      $<$<COMPILE_LANGUAGE:C>:-Wshadow>
      $<$<COMPILE_LANGUAGE:C>:-Wformat=2>
      $<$<COMPILE_LANGUAGE:C>:-Wundef>
      $<$<COMPILE_LANGUAGE:C>:-Wcast-align>
      $<$<COMPILE_LANGUAGE:C>:-Wstrict-prototypes>
      $<$<COMPILE_LANGUAGE:C>:-Wmissing-prototypes>
      $<$<COMPILE_LANGUAGE:C>:-Wwrite-strings>
      $<$<COMPILE_LANGUAGE:C>:-Werror>
  )
endfunction()
