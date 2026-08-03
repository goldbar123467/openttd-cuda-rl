cmake_minimum_required(VERSION 3.28...3.28)

project(openttd_rl_v2_m22_training VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

find_package(Python3 3.12 REQUIRED COMPONENTS Interpreter)

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
  openttd_rl_v2_m22_policy
  ../src/generalist_policy.cpp
  ../src/m22_campaign.cpp
  ../src/m22_checkpoint.cpp
  ../src/m22_corpus.cpp
  ../src/m22_ppo.cpp
  ../src/m22_trainer.cpp
  ../src/scalable_policy.cpp
)
target_include_directories(openttd_rl_v2_m22_policy PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/../include")
target_link_libraries(openttd_rl_v2_m22_policy PUBLIC "${TORCH_LIBRARIES}" ${V2_NVIDIA_LIBRARIES} OpenSSL::Crypto)
v2_enable_strict_warnings(openttd_rl_v2_m22_policy)
set_property(TARGET openttd_rl_v2_m22_policy PROPERTY POSITION_INDEPENDENT_CODE ON)
set_target_properties(openttd_rl_v2_m22_policy PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")

# The final evaluator is intentionally a separate link boundary. It contains no
# trainer, PPO, campaign, checkpoint-recovery, or optimizer implementation.
add_library(
  openttd_rl_v2_m22_evaluation
  ../src/generalist_policy.cpp
  ../src/m22_evaluation.cpp
  ../src/scalable_policy.cpp
)
target_include_directories(openttd_rl_v2_m22_evaluation PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/../include")
target_link_libraries(openttd_rl_v2_m22_evaluation PUBLIC "${TORCH_LIBRARIES}" ${V2_NVIDIA_LIBRARIES} OpenSSL::Crypto)
v2_enable_strict_warnings(openttd_rl_v2_m22_evaluation)
set_property(TARGET openttd_rl_v2_m22_evaluation PROPERTY POSITION_INDEPENDENT_CODE ON)
set_target_properties(openttd_rl_v2_m22_evaluation PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")

add_executable(m22_evaluator ../src/m22_evaluator_main.cpp)
target_link_libraries(m22_evaluator PRIVATE openttd_rl_v2_m22_evaluation CUDA::cudart)
v2_enable_strict_warnings(m22_evaluator)
set_target_properties(m22_evaluator PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_evaluator PRIVATE "LINKER:--disable-new-dtags")

add_executable(m22_evaluation_gate ../tests/m22_evaluation_gate.cpp)
target_link_libraries(m22_evaluation_gate PRIVATE openttd_rl_v2_m22_evaluation)
v2_enable_strict_warnings(m22_evaluation_gate)
set_target_properties(m22_evaluation_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_evaluation_gate PRIVATE "LINKER:--disable-new-dtags")

add_executable(m22_learning_gate ../tests/m22_learning_gate.cpp)
target_link_libraries(m22_learning_gate PRIVATE openttd_rl_v2_m22_policy CUDA::cudart)
v2_enable_strict_warnings(m22_learning_gate)
set_target_properties(m22_learning_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_learning_gate PRIVATE "LINKER:--disable-new-dtags")

add_executable(m22_trainer_gate ../tests/m22_trainer_gate.cpp)
target_link_libraries(m22_trainer_gate PRIVATE openttd_rl_v2_m22_policy CUDA::cudart)
v2_enable_strict_warnings(m22_trainer_gate)
set_target_properties(m22_trainer_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_trainer_gate PRIVATE "LINKER:--disable-new-dtags")

set(M22_REPOSITORY_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../..")
set(M22_CORPUS_BINARY "${CMAKE_CURRENT_BINARY_DIR}/m22-native-corpus-f3ae8f89-0af952bb.bin")
if(NOT EXISTS "${M22_CORPUS_BINARY}")
  execute_process(
    COMMAND
      "${CMAKE_COMMAND}" -E env "PYTHONPATH=${M22_REPOSITORY_ROOT}/scripts/v2"
      "${Python3_EXECUTABLE}" "${M22_REPOSITORY_ROOT}/scripts/v2/encode_m22_native_corpus.py"
      --root "${M22_REPOSITORY_ROOT}" --output "${M22_CORPUS_BINARY}"
    RESULT_VARIABLE M22_CORPUS_RESULT
    OUTPUT_VARIABLE M22_CORPUS_OUTPUT
    ERROR_VARIABLE M22_CORPUS_ERROR
  )
  if(NOT M22_CORPUS_RESULT EQUAL 0)
    message(FATAL_ERROR "M22 corpus encoding failed: ${M22_CORPUS_OUTPUT}${M22_CORPUS_ERROR}")
  endif()
endif()

add_executable(m22_corpus_gate ../tests/m22_corpus_gate.cpp)
target_link_libraries(m22_corpus_gate PRIVATE openttd_rl_v2_m22_policy)
v2_enable_strict_warnings(m22_corpus_gate)
set_target_properties(m22_corpus_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_corpus_gate PRIVATE "LINKER:--disable-new-dtags")

add_executable(m22_checkpoint_gate ../tests/m22_checkpoint_gate.cpp)
target_link_libraries(m22_checkpoint_gate PRIVATE openttd_rl_v2_m22_policy CUDA::cudart)
v2_enable_strict_warnings(m22_checkpoint_gate)
set_target_properties(m22_checkpoint_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_checkpoint_gate PRIVATE "LINKER:--disable-new-dtags")

add_executable(m22_campaign ../src/m22_campaign_main.cpp)
target_link_libraries(m22_campaign PRIVATE openttd_rl_v2_m22_policy CUDA::cudart)
v2_enable_strict_warnings(m22_campaign)
set_target_properties(m22_campaign PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_campaign PRIVATE "LINKER:--disable-new-dtags")

add_executable(m22_campaign_gate ../tests/m22_campaign_gate.cpp)
target_link_libraries(m22_campaign_gate PRIVATE openttd_rl_v2_m22_policy CUDA::cudart)
v2_enable_strict_warnings(m22_campaign_gate)
set_target_properties(m22_campaign_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_campaign_gate PRIVATE "LINKER:--disable-new-dtags")

add_executable(m22_qualification_gate ../tests/m22_qualification_gate.cpp)
target_link_libraries(m22_qualification_gate PRIVATE openttd_rl_v2_m22_policy CUDA::cudart)
v2_enable_strict_warnings(m22_qualification_gate)
set_target_properties(m22_qualification_gate PROPERTIES BUILD_RPATH "${V2_NVIDIA_LIBRARY_PATHS}")
target_link_options(m22_qualification_gate PRIVATE "LINKER:--disable-new-dtags")

if(BUILD_TESTING)
  add_test(NAME v2_m22_evaluation COMMAND m22_evaluation_gate)
  set_tests_properties(v2_m22_evaluation PROPERTIES LABELS "v2;m22;evaluation;cpu;offline" TIMEOUT 300)
  add_test(NAME v2_m22_learning_cpu COMMAND m22_learning_gate --device cpu)
  set_tests_properties(v2_m22_learning_cpu PROPERTIES LABELS "v2;m22;learning;cpu;offline" TIMEOUT 300)
  add_test(NAME v2_m22_learning_cuda COMMAND m22_learning_gate --device cuda:0)
  set_tests_properties(v2_m22_learning_cuda PROPERTIES LABELS "v2;m22;learning;cuda;offline" TIMEOUT 300)
  add_test(NAME v2_m22_trainer_cpu COMMAND m22_trainer_gate --device cpu)
  set_tests_properties(v2_m22_trainer_cpu PROPERTIES LABELS "v2;m22;trainer;cpu;offline" TIMEOUT 600)
  add_test(NAME v2_m22_trainer_cuda COMMAND m22_trainer_gate --device cuda:0)
  set_tests_properties(v2_m22_trainer_cuda PROPERTIES LABELS "v2;m22;trainer;cuda;offline" TIMEOUT 600)
  add_test(NAME v2_m22_corpus COMMAND m22_corpus_gate --corpus "${M22_CORPUS_BINARY}")
  set_tests_properties(v2_m22_corpus PROPERTIES LABELS "v2;m22;corpus;offline" TIMEOUT 60)
  add_test(NAME v2_m22_checkpoint_cpu COMMAND m22_checkpoint_gate --device cpu --corpus "${M22_CORPUS_BINARY}")
  set_tests_properties(v2_m22_checkpoint_cpu PROPERTIES LABELS "v2;m22;checkpoint;cpu;offline" TIMEOUT 600)
  add_test(NAME v2_m22_checkpoint_cuda COMMAND m22_checkpoint_gate --device cuda:0 --corpus "${M22_CORPUS_BINARY}")
  set_tests_properties(v2_m22_checkpoint_cuda PROPERTIES LABELS "v2;m22;checkpoint;cuda;offline" TIMEOUT 600)
  add_test(NAME v2_m22_campaign_cpu COMMAND m22_campaign_gate --device cpu --corpus "${M22_CORPUS_BINARY}")
  set_tests_properties(v2_m22_campaign_cpu PROPERTIES LABELS "v2;m22;campaign;cpu;offline" TIMEOUT 600)
  add_test(NAME v2_m22_campaign_cuda COMMAND m22_campaign_gate --device cuda:0 --corpus "${M22_CORPUS_BINARY}")
  set_tests_properties(v2_m22_campaign_cuda PROPERTIES LABELS "v2;m22;campaign;cuda;offline" TIMEOUT 600)
endif()
