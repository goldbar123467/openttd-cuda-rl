#pragma once
#include <cuda_runtime_api.h>
void launch_fused_policy(const float *logits, const bool *mask, float *log_probabilities,
                         float *probabilities, float *entropy, int *status, int rows, cudaStream_t stream);
