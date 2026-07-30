/* SPDX-License-Identifier: GPL-2.0-only */
#include "openttd_rl_parity/comparator.h"
#include "openttd_rl_parity/minimizer.h"
#include "openttd_rl_parity/tape_writer.h"

#include <stddef.h>
#include <string.h>

int main(void)
{
    otrl_context_options options;
    otrl_context *context = NULL;
    otrl_error error;
    if (offsetof(otrl_context_options, size) != 0U ||
        offsetof(otrl_context_options, version) != 4U ||
        offsetof(otrl_record_view, size) != 0U ||
        offsetof(otrl_compare_result, size) != 0U) return 1;
    memset(&options, 0, sizeof(options));
    options.size = (uint32_t)sizeof(options);
    options.version = OTRL_ABI_VERSION;
    otrl_error_init(&error);
    if (otrl_context_create(&options, &context, &error) != OTRL_OK) return 2;
    otrl_context_destroy(context);
    return 0;
}
