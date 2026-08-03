cmake_minimum_required(VERSION 3.28...3.28)

project(openttd_rl_v2_m23_release VERSION 0.1.0 LANGUAGES CXX)

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

option(V2_M23_DEPLOYMENT_ONLY "Build only the inference-only M23 ONNX Runtime evaluator" OFF)

if(NOT DEFINED V2_ONNXRUNTIME_ROOT OR NOT IS_DIRECTORY "${V2_ONNXRUNTIME_ROOT}")
  message(FATAL_ERROR "V2_ONNXRUNTIME_ROOT must name the pinned extracted ONNX Runtime dependency root")
endif()
find_path(
  V2_ONNXRUNTIME_INCLUDE_DIR
  NAMES onnxruntime_cxx_api.h
  PATHS "${V2_ONNXRUNTIME_ROOT}/include"
  NO_DEFAULT_PATH
  REQUIRED
)
find_library(
  V2_ONNXRUNTIME_LIBRARY
  NAMES onnxruntime
  PATHS "${V2_ONNXRUNTIME_ROOT}/lib"
  NO_DEFAULT_PATH
  REQUIRED
)
find_package(OpenSSL 3.0 REQUIRED COMPONENTS Crypto)

add_library(openttd_rl_v2_m23_golden_format ../src/m23_golden.cpp)
target_include_directories(openttd_rl_v2_m23_golden_format PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/../include")
target_link_libraries(openttd_rl_v2_m23_golden_format PUBLIC OpenSSL::Crypto)
v2_enable_strict_warnings(openttd_rl_v2_m23_golden_format)
set_property(TARGET openttd_rl_v2_m23_golden_format PROPERTY POSITION_INDEPENDENT_CODE ON)

add_library(openttd_rl_v2_m23_onnx ../src/m23_onnx.cpp)
target_include_directories(openttd_rl_v2_m23_onnx PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/../include")
target_include_directories(openttd_rl_v2_m23_onnx SYSTEM PUBLIC "${V2_ONNXRUNTIME_INCLUDE_DIR}")
target_link_libraries(openttd_rl_v2_m23_onnx PUBLIC "${V2_ONNXRUNTIME_LIBRARY}" openttd_rl_v2_m23_golden_format)
v2_enable_strict_warnings(openttd_rl_v2_m23_onnx)
set_property(TARGET openttd_rl_v2_m23_onnx PROPERTY POSITION_INDEPENDENT_CODE ON)
set_target_properties(openttd_rl_v2_m23_onnx PROPERTIES BUILD_RPATH "${V2_ONNXRUNTIME_ROOT}/lib")

add_executable(m23_onnx_evaluator ../src/m23_onnx_evaluator_main.cpp)
target_link_libraries(m23_onnx_evaluator PRIVATE openttd_rl_v2_m23_onnx)
v2_enable_strict_warnings(m23_onnx_evaluator)
set_target_properties(m23_onnx_evaluator PROPERTIES BUILD_RPATH "${V2_ONNXRUNTIME_ROOT}/lib")
target_link_options(m23_onnx_evaluator PRIVATE "LINKER:--disable-new-dtags")

if(V2_M23_DEPLOYMENT_ONLY)
  return()
endif()

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
  openttd_rl_v2_m23_native
  ../src/generalist_policy.cpp
  ../src/m22_evaluation.cpp
  ../src/m23_deployment.cpp
  ../src/scalable_policy.cpp
)
target_include_directories(openttd_rl_v2_m23_native PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/../include")
target_link_libraries(openttd_rl_v2_m23_native PUBLIC "${TORCH_LIBRARIES}" ${V2_NVIDIA_LIBRARIES} OpenSSL::Crypto openttd_rl_v2_m23_golden_format)
v2_enable_strict_warnings(openttd_rl_v2_m23_native)
set_property(TARGET openttd_rl_v2_m23_native PROPERTY POSITION_INDEPENDENT_CODE ON)
set_target_properties(openttd_rl_v2_m23_native PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")

add_executable(m23_deployment_gate ../tests/m23_deployment_gate.cpp)
target_link_libraries(m23_deployment_gate PRIVATE openttd_rl_v2_m23_native)
v2_enable_strict_warnings(m23_deployment_gate)
set_target_properties(m23_deployment_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m23_deployment_gate PRIVATE "LINKER:--disable-new-dtags")

add_executable(m23_native_golden ../src/m23_native_golden_main.cpp)
target_link_libraries(m23_native_golden PRIVATE openttd_rl_v2_m23_native)
v2_enable_strict_warnings(m23_native_golden)
set_target_properties(m23_native_golden PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m23_native_golden PRIVATE "LINKER:--disable-new-dtags")

if(BUILD_TESTING)
  add_test(NAME v2_m23_deployment COMMAND m23_deployment_gate)
  set_tests_properties(v2_m23_deployment PROPERTIES LABELS "v2;m23;deployment;cpu;offline" TIMEOUT 300)
endif()
