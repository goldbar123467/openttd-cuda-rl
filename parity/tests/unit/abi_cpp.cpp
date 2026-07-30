/* SPDX-License-Identifier: GPL-2.0-only */
#include "openttd_rl_parity/comparator.h"
#include "openttd_rl_parity/minimizer.h"
#include "openttd_rl_parity/tape_writer.h"

#include <cstddef>
#include <cstdint>

static_assert(offsetof(otrl_error, size) == 0);
static_assert(offsetof(otrl_error, version) == 4);
static_assert(OTRL_FORMAT_MAJOR == 1);

int main()
{
    return otrl_status_string(OTRL_OK)[0] == 'O' ? 0 : 1;
}
