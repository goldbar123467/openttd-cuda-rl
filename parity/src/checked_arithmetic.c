/* SPDX-License-Identifier: GPL-2.0-only */
#include "openttd_rl_parity/tape_reader.h"

#include <stdint.h>

int otrl_checked_add_size(size_t a, size_t b, size_t *out)
{
    if (out == NULL || b > SIZE_MAX - a) {
        return 0;
    }
    *out = a + b;
    return 1;
}

int otrl_checked_mul_size(size_t a, size_t b, size_t *out)
{
    if (out == NULL || (a != 0U && b > SIZE_MAX / a)) {
        return 0;
    }
    *out = a * b;
    return 1;
}

int otrl_checked_align8_size(size_t value, size_t *out)
{
    const size_t remainder = value & 7U;
    const size_t addition = remainder == 0U ? 0U : 8U - remainder;
    return otrl_checked_add_size(value, addition, out);
}
