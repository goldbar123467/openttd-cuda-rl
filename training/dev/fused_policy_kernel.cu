#include "fused_policy_kernel.h"
#include <cuda_runtime.h>
#include <math_constants.h>

namespace {
// One 64-thread block per row. The final 23 threads participate in reductions
// with neutral values; every thread reaches every barrier. No fast-math mode.
__global__ void policy_kernel(const float *logits, const bool *mask, float *logp,
                              float *probability, float *entropy, int *status)
{
    const int lane = static_cast<int>(threadIdx.x);
    const int row = static_cast<int>(blockIdx.x);
    const int offset = row * 41 + lane;
    const bool active = lane < 41;
    const bool legal = active && mask[offset];
    const float value = active ? logits[offset] : 0.F;
    __shared__ float reduction[64];
    __shared__ int invalid[64];
    reduction[lane] = legal ? value : -CUDART_INF_F;
    invalid[lane] = active && !isfinite(value) ? 1 : 0;
    __syncthreads();
    for (int stride = 32; stride > 0; stride /= 2) {
        if (lane < stride) {
            reduction[lane] = fmaxf(reduction[lane], reduction[lane + stride]);
            invalid[lane] |= invalid[lane + stride];
        }
        __syncthreads();
    }
    const float maximum = reduction[0];
    const int error = invalid[0] ? 1 : (!isfinite(maximum) ? 2 : 0);
    // Uniform branch after a block-wide reduction; no barrier divergence.
    if (error) {
        if (lane == 0) status[row] = error;
        return;
    }
    // Preserve maximum in each thread before reusing the shared array.
    __syncthreads();
    const float shifted = legal ? value - maximum : -CUDART_INF_F;
    reduction[lane] = legal ? expf(shifted) : 0.F;
    __syncthreads();
    for (int stride = 32; stride > 0; stride /= 2) {
        if (lane < stride) reduction[lane] += reduction[lane + stride];
        __syncthreads();
    }
    const float normalizer = logf(reduction[0]);
    const float lp = legal ? shifted - normalizer : -CUDART_INF_F;
    const float p = legal ? expf(lp) : 0.F;
    __syncthreads();
    reduction[lane] = legal ? -p * lp : 0.F;
    __syncthreads();
    for (int stride = 32; stride > 0; stride /= 2) {
        if (lane < stride) reduction[lane] += reduction[lane + stride];
        __syncthreads();
    }
    if (active) {
        logp[offset] = lp;
        probability[offset] = p;
    }
    if (lane == 0) {
        entropy[row] = reduction[0];
        status[row] = isfinite(reduction[0]) ? 0 : 3;
    }
}
}

void launch_fused_policy(const float *logits, const bool *mask, float *log_probabilities,
                         float *probabilities, float *entropy, int *status, int rows, cudaStream_t stream)
{
    policy_kernel<<<rows, 64, 0, stream>>>(logits, mask, log_probabilities, probabilities, entropy, status);
}
