/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"

/* Search a proven-monotone closed-boundary predicate logarithmically. The
   pre-scan detects a violated proof obligation and switches to the specified
   linear fallback, which is independently regression-tested. */
size_t otrl_find_first_true(const uint8_t *predicate, size_t count,
                            int *used_linear_fallback)
{
    size_t low = 0U;
    size_t high = count;
    int monotone = 1;
    int seen_true = 0;
    if (used_linear_fallback != NULL) *used_linear_fallback = 0;
    if (predicate == NULL) return count;
    for (size_t i = 0U; i < count; ++i) {
        if (predicate[i] != 0U) {
            seen_true = 1;
        } else if (seen_true) {
            monotone = 0;
            break;
        }
    }
    if (!monotone) {
        if (used_linear_fallback != NULL) *used_linear_fallback = 1;
        for (size_t i = 0U; i < count; ++i) {
            if (predicate[i] != 0U) return i;
        }
        return count;
    }
    while (low < high) {
        const size_t middle = low + (high - low) / 2U;
        if (predicate[middle] != 0U) high = middle;
        else low = middle + 1U;
    }
    return low;
}
