cmake_minimum_required(VERSION 3.28...3.28)

project(openttd_rl_v2_training VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

function(v2_enable_strict_warnings target)
  target_compile_options(
    "${target}"
    PRIVATE
      -Wall
      -Wextra
      -Wpedantic
      -Wconversion
      -Wsign-conversion
      -Werror
  )
endfunction()

if(NOT DEFINED V2_NVIDIA_RUNTIME_ROOT OR NOT IS_DIRECTORY "${V2_NVIDIA_RUNTIME_ROOT}")
  message(FATAL_ERROR "V2_NVIDIA_RUNTIME_ROOT must name the pinned extracted LibTorch runtime dependency root")
endif()

set(TORCH_CUDA_ARCH_LIST "12.0")
unset(CMAKE_CUDA_ARCHITECTURES)
unset(CMAKE_CUDA_ARCHITECTURES CACHE)
get_filename_component(V2_LIBTORCH_ROOT "${Torch_DIR}/../../.." ABSOLUTE)
find_library(V2_LIBTORCH_CPU_LIBRARY NAMES torch_cpu PATHS "${V2_LIBTORCH_ROOT}/lib" NO_DEFAULT_PATH REQUIRED)
set(kineto_LIBRARY "${V2_LIBTORCH_CPU_LIBRARY}" CACHE FILEPATH "LibTorch bundled Kineto symbol provider" FORCE)
find_package(Torch 2.13.0 EXACT CONFIG REQUIRED)
list(REMOVE_ITEM TORCH_LIBRARIES "${V2_LIBTORCH_CPU_LIBRARY}")
find_package(CUDAToolkit 13.0 EXACT REQUIRED)
find_package(OpenSSL 3.0 REQUIRED COMPONENTS Crypto)

find_file(V2_CUDNN_LIBRARY NAMES libcudnn.so.9 PATHS "${V2_NVIDIA_RUNTIME_ROOT}/nvidia/cudnn/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V2_CUSPARSELT_LIBRARY NAMES libcusparseLt.so.0 PATHS "${V2_NVIDIA_RUNTIME_ROOT}/nvidia/cusparselt/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V2_NCCL_LIBRARY NAMES libnccl.so.2 PATHS "${V2_NVIDIA_RUNTIME_ROOT}/nvidia/nccl/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V2_NVSHMEM_LIBRARY NAMES libnvshmem_host.so.3 PATHS "${V2_NVIDIA_RUNTIME_ROOT}/nvidia/nvshmem/lib" NO_DEFAULT_PATH REQUIRED)
set(V2_NVIDIA_LIBRARIES "${V2_CUDNN_LIBRARY}" "${V2_CUSPARSELT_LIBRARY}" "${V2_NCCL_LIBRARY}" "${V2_NVSHMEM_LIBRARY}")
set(V2_NVIDIA_LIBRARY_PATHS
  "${V2_NVIDIA_RUNTIME_ROOT}/nvidia/cudnn/lib"
  "${V2_NVIDIA_RUNTIME_ROOT}/nvidia/cusparselt/lib"
  "${V2_NVIDIA_RUNTIME_ROOT}/nvidia/nccl/lib"
  "${V2_NVIDIA_RUNTIME_ROOT}/nvidia/nvshmem/lib"
)

add_library(
  openttd_rl_v2_policy
  src/checkpoint.cpp
  src/scalable_policy.cpp
)
target_include_directories(openttd_rl_v2_policy PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(openttd_rl_v2_policy PUBLIC "${TORCH_LIBRARIES}" ${V2_NVIDIA_LIBRARIES} OpenSSL::Crypto)
v2_enable_strict_warnings(openttd_rl_v2_policy)
set_property(TARGET openttd_rl_v2_policy PROPERTY POSITION_INDEPENDENT_CODE ON)
set_target_properties(openttd_rl_v2_policy PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")

add_executable(m15_policy_gate tests/m15_policy_gate.cpp)
target_link_libraries(m15_policy_gate PRIVATE openttd_rl_v2_policy CUDA::cudart)
v2_enable_strict_warnings(m15_policy_gate)
set_target_properties(m15_policy_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m15_policy_gate PRIVATE "LINKER:--disable-new-dtags")

if(BUILD_TESTING)
  add_test(NAME v2_m15_policy_cpu COMMAND m15_policy_gate --device cpu)
  set_tests_properties(v2_m15_policy_cpu PROPERTIES LABELS "v2;m15;policy;cpu;offline" TIMEOUT 300)
  add_test(NAME v2_m15_policy_cuda COMMAND m15_policy_gate --device cuda:0)
  set_tests_properties(v2_m15_policy_cuda PROPERTIES LABELS "v2;m15;policy;cuda;offline" TIMEOUT 300)
endif()
