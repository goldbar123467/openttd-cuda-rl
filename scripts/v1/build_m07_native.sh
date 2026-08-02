#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

cache_root=""
build_root=""
while (($# > 0)); do
    case "$1" in
        --cache-root)
            cache_root=$2
            shift 2
            ;;
        --build-root)
            build_root=$2
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

[[ "$cache_root" = /* && -d "$cache_root" ]] || {
    echo "--cache-root must name an existing absolute directory" >&2
    exit 2
}
[[ "$build_root" = /* && ! -e "$build_root" ]] || {
    echo "--build-root must name a new absolute path" >&2
    exit 2
}

libtorch_root="$cache_root/libtorch-2.13.0-cu130/libtorch"
runtime_root="$cache_root/libtorch-runtime-cu130"
archive="$cache_root/libtorch-shared-with-deps-2.13.0+cu130.zip"
[[ -f "$libtorch_root/share/cmake/Torch/TorchConfig.cmake" && -f "$libtorch_root/lib/libtorch.so" ]] || {
    echo "pinned LibTorch extraction is incomplete" >&2
    exit 1
}
[[ $(<"$libtorch_root/build-version") == "2.13.0+cu130" ]] || {
    echo "pinned LibTorch version marker drifted" >&2
    exit 1
}
[[ $(sha256sum -- "$archive" | cut -d' ' -f1) == "945c5a3d946a28b387ad9dc9fddda7ba03e35fae1375b84ebff15df789436f82" ]] || {
    echo "pinned LibTorch archive digest drifted" >&2
    exit 1
}
for library in \
    "$runtime_root/nvidia/cudnn/lib/libcudnn.so.9" \
    "$runtime_root/nvidia/cusparselt/lib/libcusparseLt.so.0" \
    "$runtime_root/nvidia/nccl/lib/libnccl.so.2" \
    "$runtime_root/nvidia/nvshmem/lib/libnvshmem_host.so.3"; do
    [[ -f "$library" ]] || {
        echo "pinned LibTorch runtime dependency is missing: $library" >&2
        exit 1
    }
done

cmake \
    -S "$REPOSITORY_ROOT/training/v1" \
    -B "$build_root" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
    -DTorch_DIR="$libtorch_root/share/cmake/Torch" \
    -DV1_NVIDIA_RUNTIME_ROOT="$runtime_root"
cmake --build "$build_root" --parallel 2
ctest --test-dir "$build_root" --output-on-failure --no-tests=error
"$build_root/rl_trainer" --probe

echo "M07_NATIVE_BUILD=PASS build_root=$build_root"
