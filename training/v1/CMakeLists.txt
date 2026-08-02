cmake_minimum_required(VERSION 3.28...3.28)

project(openttd_rl_v1_training VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

function(v1_enable_strict_warnings target)
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

option(V1_DEPLOYMENT_ONLY "Build only the inference-only ONNX Runtime deployment evaluator" OFF)

if(V1_DEPLOYMENT_ONLY OR DEFINED V1_ONNXRUNTIME_ROOT)
  if(NOT DEFINED V1_ONNXRUNTIME_ROOT OR NOT IS_DIRECTORY "${V1_ONNXRUNTIME_ROOT}")
    message(FATAL_ERROR "V1_ONNXRUNTIME_ROOT must name the pinned extracted ONNX Runtime dependency root")
  endif()
  find_path(
    V1_ONNXRUNTIME_INCLUDE_DIR
    NAMES onnxruntime_cxx_api.h
    PATHS "${V1_ONNXRUNTIME_ROOT}/include"
    NO_DEFAULT_PATH
    REQUIRED
  )
  find_library(
    V1_ONNXRUNTIME_LIBRARY
    NAMES onnxruntime
    PATHS "${V1_ONNXRUNTIME_ROOT}/lib"
    NO_DEFAULT_PATH
    REQUIRED
  )
  find_package(OpenSSL 3.0 REQUIRED COMPONENTS Crypto)

  add_library(openttd_rl_deployment src/deployment_model.cpp)
  target_include_directories(
    openttd_rl_deployment
    PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
  )
  target_include_directories(openttd_rl_deployment SYSTEM PUBLIC "${V1_ONNXRUNTIME_INCLUDE_DIR}")
  target_link_libraries(openttd_rl_deployment PUBLIC "${V1_ONNXRUNTIME_LIBRARY}" OpenSSL::Crypto)
  v1_enable_strict_warnings(openttd_rl_deployment)
  set_property(TARGET openttd_rl_deployment PROPERTY POSITION_INDEPENDENT_CODE ON)
  set_target_properties(openttd_rl_deployment PROPERTIES BUILD_RPATH "${V1_ONNXRUNTIME_ROOT}/lib")

  add_executable(m10_onnx_evaluator src/m10_onnx_evaluator_main.cpp)
  target_link_libraries(m10_onnx_evaluator PRIVATE openttd_rl_deployment)
  v1_enable_strict_warnings(m10_onnx_evaluator)
  set_target_properties(m10_onnx_evaluator PROPERTIES BUILD_RPATH "${V1_ONNXRUNTIME_ROOT}/lib")
  target_link_options(m10_onnx_evaluator PRIVATE "LINKER:--disable-new-dtags")
endif()

if(V1_DEPLOYMENT_ONLY)
  return()
endif()

if(NOT DEFINED V1_NVIDIA_RUNTIME_ROOT OR NOT IS_DIRECTORY "${V1_NVIDIA_RUNTIME_ROOT}")
  message(FATAL_ERROR "V1_NVIDIA_RUNTIME_ROOT must name the pinned extracted LibTorch runtime dependency root")
endif()
set(TORCH_CUDA_ARCH_LIST "12.0")
unset(CMAKE_CUDA_ARCHITECTURES)
unset(CMAKE_CUDA_ARCHITECTURES CACHE)
get_filename_component(V1_LIBTORCH_ROOT "${Torch_DIR}/../../.." ABSOLUTE)
find_library(V1_LIBTORCH_CPU_LIBRARY NAMES torch_cpu PATHS "${V1_LIBTORCH_ROOT}/lib" NO_DEFAULT_PATH REQUIRED)
set(kineto_LIBRARY "${V1_LIBTORCH_CPU_LIBRARY}" CACHE FILEPATH "LibTorch bundled Kineto symbol provider" FORCE)
find_package(Torch 2.13.0 EXACT CONFIG REQUIRED)
list(REMOVE_ITEM TORCH_LIBRARIES "${V1_LIBTORCH_CPU_LIBRARY}")
find_package(CUDAToolkit 13.0 EXACT REQUIRED)
find_package(OpenSSL 3.0 REQUIRED COMPONENTS Crypto)

find_file(V1_CUDNN_LIBRARY NAMES libcudnn.so.9 PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cudnn/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V1_CUSPARSELT_LIBRARY NAMES libcusparseLt.so.0 PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cusparselt/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V1_NCCL_LIBRARY NAMES libnccl.so.2 PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nccl/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V1_NVSHMEM_LIBRARY NAMES libnvshmem_host.so.3 PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nvshmem/lib" NO_DEFAULT_PATH REQUIRED)
set(V1_NVIDIA_LIBRARIES "${V1_CUDNN_LIBRARY}" "${V1_CUSPARSELT_LIBRARY}" "${V1_NCCL_LIBRARY}" "${V1_NVSHMEM_LIBRARY}")
set(V1_NVIDIA_LIBRARY_PATHS
  "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cudnn/lib"
  "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cusparselt/lib"
  "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nccl/lib"
  "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nvshmem/lib"
)

add_library(
  openttd_rl_inference
  src/evaluation_model.cpp
  src/model.cpp
  src/multimodal_model.cpp
  src/ppo.cpp
  src/rng.cpp
)
target_include_directories(openttd_rl_inference PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(openttd_rl_inference PUBLIC "${TORCH_LIBRARIES}" ${V1_NVIDIA_LIBRARIES} OpenSSL::Crypto)
v1_enable_strict_warnings(openttd_rl_inference)
set_property(TARGET openttd_rl_inference PROPERTY POSITION_INDEPENDENT_CODE ON)
set_target_properties(openttd_rl_inference PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")

add_library(
  openttd_rl_training
  src/checkpoint.cpp
  src/learning.cpp
  src/metrics.cpp
  src/multimodal_trainer.cpp
  src/service.cpp
  src/trainer.cpp
)
target_include_directories(openttd_rl_training PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(openttd_rl_training PUBLIC openttd_rl_inference)
v1_enable_strict_warnings(openttd_rl_training)
set_property(TARGET openttd_rl_training PROPERTY POSITION_INDEPENDENT_CODE ON)
set_target_properties(openttd_rl_training PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")

add_executable(rl_trainer src/trainer_main.cpp)
target_link_libraries(rl_trainer PRIVATE openttd_rl_training)
v1_enable_strict_warnings(rl_trainer)
set_target_properties(rl_trainer PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
target_link_options(rl_trainer PRIVATE "LINKER:--disable-new-dtags")

add_executable(m08_cuda_gate src/m08_cuda_main.cpp)
target_link_libraries(m08_cuda_gate PRIVATE openttd_rl_training CUDA::cudart)
v1_enable_strict_warnings(m08_cuda_gate)
set_target_properties(m08_cuda_gate PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
target_link_options(m08_cuda_gate PRIVATE "LINKER:--disable-new-dtags")

add_executable(m08_architecture_smoke src/m08_architecture_smoke_main.cpp)
target_link_libraries(m08_architecture_smoke PRIVATE openttd_rl_training)
v1_enable_strict_warnings(m08_architecture_smoke)
set_target_properties(m08_architecture_smoke PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
target_link_options(m08_architecture_smoke PRIVATE "LINKER:--disable-new-dtags")

add_executable(m08_trainer src/m08_trainer_main.cpp)
target_link_libraries(m08_trainer PRIVATE openttd_rl_training)
v1_enable_strict_warnings(m08_trainer)
set_target_properties(m08_trainer PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
target_link_options(m08_trainer PRIVATE "LINKER:--disable-new-dtags")

add_executable(m09_evaluator src/m09_evaluator_main.cpp)
target_link_libraries(m09_evaluator PRIVATE openttd_rl_inference)
v1_enable_strict_warnings(m09_evaluator)
set_target_properties(m09_evaluator PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
target_link_options(m09_evaluator PRIVATE "LINKER:--disable-new-dtags")

add_executable(m10_export_orchestrator src/m10_export_orchestrator_main.cpp)
target_link_libraries(m10_export_orchestrator PRIVATE openttd_rl_inference)
v1_enable_strict_warnings(m10_export_orchestrator)
set_target_properties(m10_export_orchestrator PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
target_link_options(m10_export_orchestrator PRIVATE "LINKER:--disable-new-dtags")

if(BUILD_TESTING)
  find_program(V1_TEST_PYTHON NAMES python3 REQUIRED)
  add_executable(rl_native_tests tests/native_tests.cpp)
  target_link_libraries(rl_native_tests PRIVATE openttd_rl_training)
  v1_enable_strict_warnings(rl_native_tests)
  set_target_properties(rl_native_tests PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
  target_link_options(rl_native_tests PRIVATE "LINKER:--disable-new-dtags")
  add_test(NAME rl_native_tests COMMAND rl_native_tests)
  set_tests_properties(rl_native_tests PROPERTIES LABELS "v1;m07;ppo;cpu;offline" TIMEOUT 300)
  add_test(
    NAME rl_reference_differential
    COMMAND
      "${V1_TEST_PYTHON}"
      "${CMAKE_CURRENT_SOURCE_DIR}/../../scripts/v1/m07_ppo_reference.py"
      --trainer "$<TARGET_FILE:rl_trainer>"
  )
  set_tests_properties(rl_reference_differential PROPERTIES LABELS "v1;m07;ppo;differential;offline" TIMEOUT 120)
  add_test(
    NAME rl_metric_sources
    COMMAND
      "${V1_TEST_PYTHON}"
      "${CMAKE_CURRENT_SOURCE_DIR}/../../scripts/v1/validate_m07_metrics.py"
      --schema "${CMAKE_CURRENT_SOURCE_DIR}/../../docs/project/schema/v1-m07-metric-event.schema.json"
      --sources "${CMAKE_CURRENT_SOURCE_DIR}/../../config/v1/m07-metric-sources.json"
      --trainer "$<TARGET_FILE:rl_trainer>"
  )
  set_tests_properties(rl_metric_sources PROPERTIES LABELS "v1;m07;metrics;monitor;offline" TIMEOUT 120)
  add_test(NAME rl_tiny_bandit COMMAND rl_trainer --tiny-bandit)
  set_tests_properties(rl_tiny_bandit PROPERTIES LABELS "v1;m07;ppo;learning;cpu;offline" TIMEOUT 120)

  add_executable(rl_m08_native_tests tests/m08_native_tests.cpp)
  target_link_libraries(rl_m08_native_tests PRIVATE openttd_rl_training)
  v1_enable_strict_warnings(rl_m08_native_tests)
  set_target_properties(rl_m08_native_tests PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
  target_link_options(rl_m08_native_tests PRIVATE "LINKER:--disable-new-dtags")
  add_test(NAME rl_m08_native_tests COMMAND rl_m08_native_tests)
  set_tests_properties(rl_m08_native_tests PROPERTIES LABELS "v1;m08;architecture;cpu;offline" TIMEOUT 300)

  add_executable(rl_m09_native_tests tests/m09_native_tests.cpp)
  target_link_libraries(rl_m09_native_tests PRIVATE openttd_rl_inference)
  v1_enable_strict_warnings(rl_m09_native_tests)
  set_target_properties(rl_m09_native_tests PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")
  target_link_options(rl_m09_native_tests PRIVATE "LINKER:--disable-new-dtags")
  add_test(NAME rl_m09_native_tests COMMAND rl_m09_native_tests)
  set_tests_properties(rl_m09_native_tests PROPERTIES LABELS "v1;m09;evaluation;read-only;offline" TIMEOUT 300)
endif()
