cmake_minimum_required(VERSION 3.28)
project(openttd_rl_v1_toolchain_probe LANGUAGES CXX CUDA)

if(NOT DEFINED V1_ONNX_PROBE_MODEL OR NOT EXISTS "${V1_ONNX_PROBE_MODEL}")
  message(FATAL_ERROR "V1_ONNX_PROBE_MODEL must name the generated probe model")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CUDA_STANDARD 20)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

find_package(CUDAToolkit 13.0.88 EXACT REQUIRED)
if(NOT TARGET CUDA::cudart)
  message(FATAL_ERROR "required CMake target CUDA::cudart is unavailable")
endif()

# LibTorch 2.13 uses its own architecture selector and warns when CMake's
# selector is present while its package is loaded. Restore the exact real/PTX
# pair immediately after package discovery for project-owned CUDA targets.
set(TORCH_CUDA_ARCH_LIST "12.0")
unset(CMAKE_CUDA_ARCHITECTURES)
unset(CMAKE_CUDA_ARCHITECTURES CACHE)

# This shared LibTorch package embeds Kineto in libtorch_cpu.so but its upstream
# config still searches for a removed standalone libkineto. Point that lookup
# at the actual symbol provider, then remove the duplicate link entry below.
get_filename_component(V1_LIBTORCH_ROOT "${Torch_DIR}/../../.." ABSOLUTE)
find_library(V1_LIBTORCH_CPU_LIBRARY NAMES torch_cpu
  PATHS "${V1_LIBTORCH_ROOT}/lib" NO_DEFAULT_PATH REQUIRED)
set(kineto_LIBRARY "${V1_LIBTORCH_CPU_LIBRARY}" CACHE FILEPATH
  "LibTorch 2.13 bundled Kineto symbol provider" FORCE)
find_package(Torch 2.13.0 EXACT REQUIRED CONFIG)
list(REMOVE_ITEM TORCH_LIBRARIES "${V1_LIBTORCH_CPU_LIBRARY}")
set(CMAKE_CUDA_ARCHITECTURES "120-real;120-virtual" CACHE STRING
  "Required native and virtual Blackwell images" FORCE)

find_path(V1_CUDNN_INCLUDE_DIR NAMES cudnn.h
  PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cudnn/include" NO_DEFAULT_PATH REQUIRED)
find_path(V1_CUSPARSELT_INCLUDE_DIR NAMES cusparseLt.h
  PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cusparselt/include" NO_DEFAULT_PATH REQUIRED)
find_path(V1_NCCL_INCLUDE_DIR NAMES nccl.h
  PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nccl/include" NO_DEFAULT_PATH REQUIRED)
find_path(V1_NVSHMEM_INCLUDE_DIR NAMES nvshmem.h
  PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nvshmem/include" NO_DEFAULT_PATH REQUIRED)
find_file(V1_CUDNN_LIBRARY NAMES libcudnn.so.9
  PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cudnn/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V1_CUSPARSELT_LIBRARY NAMES libcusparseLt.so.0
  PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cusparselt/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V1_NCCL_LIBRARY NAMES libnccl.so.2
  PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nccl/lib" NO_DEFAULT_PATH REQUIRED)
find_file(V1_NVSHMEM_LIBRARY NAMES libnvshmem_host.so.3
  PATHS "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nvshmem/lib" NO_DEFAULT_PATH REQUIRED)

set(V1_NVIDIA_LIBRARIES
  "${V1_CUDNN_LIBRARY}"
  "${V1_CUSPARSELT_LIBRARY}"
  "${V1_NCCL_LIBRARY}"
  "${V1_NVSHMEM_LIBRARY}"
)
set(V1_NVIDIA_LIBRARY_PATHS
  "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cudnn/lib"
  "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/cusparselt/lib"
  "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nccl/lib"
  "${V1_NVIDIA_RUNTIME_ROOT}/nvidia/nvshmem/lib"
)
list(JOIN V1_NVIDIA_LIBRARY_PATHS ":" V1_NVIDIA_LD_LIBRARY_PATH)

add_executable(v1_libtorch_probe libtorch_probe.cpp)
target_link_libraries(v1_libtorch_probe PRIVATE "${TORCH_LIBRARIES}" ${V1_NVIDIA_LIBRARIES})
target_compile_options(v1_libtorch_probe PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_target_properties(v1_libtorch_probe PROPERTIES BUILD_RPATH "${V1_NVIDIA_LIBRARY_PATHS}")

add_executable(v1_cuda_probe cuda_probe.cu)
target_link_libraries(v1_cuda_probe PRIVATE CUDA::cudart)
target_compile_options(v1_cuda_probe PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--Werror all-warnings -gencode=arch=compute_120,code=compute_120>
)
# nvcc leaves its per-process temporary filename in the local ELF symbol table.
# The table is not needed in a Release probe and makes the otherwise identical
# executable's raw digest vary between builds.
target_link_options(v1_cuda_probe PRIVATE
  "LINKER:--strip-all"
)

find_path(ONNXRUNTIME_INCLUDE_DIR
  NAMES onnxruntime_cxx_api.h
  PATHS "${ONNXRUNTIME_ROOT}/include"
  NO_DEFAULT_PATH
  REQUIRED
)
find_library(ONNXRUNTIME_LIBRARY
  NAMES onnxruntime
  PATHS "${ONNXRUNTIME_ROOT}/lib"
  NO_DEFAULT_PATH
  REQUIRED
)

add_executable(v1_onnxruntime_probe onnxruntime_probe.cpp)
target_include_directories(v1_onnxruntime_probe PRIVATE "${ONNXRUNTIME_INCLUDE_DIR}")
target_link_libraries(v1_onnxruntime_probe PRIVATE "${ONNXRUNTIME_LIBRARY}")
target_compile_options(v1_onnxruntime_probe PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_target_properties(v1_onnxruntime_probe PROPERTIES
  BUILD_RPATH "${ONNXRUNTIME_ROOT}/lib"
)

enable_testing()
add_test(NAME v1-libtorch-cpu-cuda-abi COMMAND v1_libtorch_probe)
set_tests_properties(v1-libtorch-cpu-cuda-abi PROPERTIES
  ENVIRONMENT "LD_LIBRARY_PATH=${V1_NVIDIA_LD_LIBRARY_PATH}"
)
add_test(NAME v1-cuda-sm120-real-ptx COMMAND v1_cuda_probe)
add_test(NAME v1-onnxruntime-cpu-abi COMMAND v1_onnxruntime_probe)
add_test(NAME v1-onnxruntime-opset18-graph COMMAND v1_onnxruntime_probe "${V1_ONNX_PROBE_MODEL}")
