/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#ifndef FUZZ_MODE
#define FUZZ_MODE 0
#endif

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);

static otrl_context *make_context(void)
{
    otrl_context_options options;
    otrl_context *context = NULL;
    memset(&options, 0, sizeof(options));
    options.size = (uint32_t)sizeof(options);
    options.version = OTRL_ABI_VERSION;
    options.local_max_tape_bytes = UINT64_C(8388608);
    options.local_max_record_count = UINT64_C(100000);
    (void)otrl_context_create(&options, &context, NULL);
    return context;
}

static void __attribute__((unused)) fuzz_one_tape(const uint8_t *data, size_t size)
{
    otrl_context *context = make_context();
    otrl_tape *tape = NULL;
    if (context == NULL) return;
    (void)otrl_validate_bytes(context, data, size, &tape, NULL);
    otrl_tape_destroy(context, tape);
    otrl_context_destroy(context);
}

static void __attribute__((unused)) fuzz_pair(const uint8_t *data, size_t size,
                                              int minimize)
{
    otrl_context *context;
    otrl_tape *left = NULL;
    otrl_tape *right = NULL;
    otrl_compare_result result;
    size_t split;
    if (size < 4U) return;
    split = (size_t)otrl_get_u32_le(data);
    if (split > size - 4U) return;
    context = make_context();
    if (context == NULL) return;
    if (otrl_validate_bytes(context, data + 4U, split, &left, NULL) == OTRL_OK &&
        otrl_validate_bytes(context, data + 4U + split, size - 4U - split,
                            &right, NULL) == OTRL_OK) {
        memset(&result, 0, sizeof(result));
        result.size = (uint32_t)sizeof(result);
        result.version = OTRL_ABI_VERSION;
        (void)otrl_compare(left, right, &result, NULL);
        if (minimize != 0) {
            static unsigned long invocation;
            char path[160];
            const int written = snprintf(path, sizeof(path),
                "/tmp/otrl-minimize-%ld-%lu.tape", (long)getpid(), invocation++);
            if (written > 0 && (size_t)written < sizeof(path)) {
                memset(&result, 0, sizeof(result));
                result.size = (uint32_t)sizeof(result);
                result.version = OTRL_ABI_VERSION;
                (void)otrl_minimize_prefix(context, left, right, path,
                                           &result, NULL);
                (void)unlink(path);
            }
        }
    }
    otrl_tape_destroy(context, right);
    otrl_tape_destroy(context, left);
    otrl_context_destroy(context);
}

static void __attribute__((unused)) fuzz_bounded_command_input(const uint8_t *data, size_t size)
{
    size_t offset = 0U;
    uint32_t commands = 0U;
    while (size - offset >= 8U && commands < OTRL_MAX_COMMAND_COUNT) {
        const uint32_t payload = otrl_get_u32_le(data + offset + 4U);
        size_t next;
        if (payload > OTRL_MAX_RECORD_PAYLOAD_BYTES ||
            !otrl_checked_add_size(offset + 8U, payload, &next) || next > size) {
            return;
        }
        offset = next;
        ++commands;
    }
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
#if FUZZ_MODE == 0
    fuzz_one_tape(data, size);
#elif FUZZ_MODE == 1
    (void)otrl_validate_canonical_header(data, size, NULL);
#elif FUZZ_MODE == 3
    {
        otrl_record_internal record;
        memset(&record, 0, sizeof(record));
        record.type = OTRL_RECORD_AUTHORITATIVE_PROJECTION;
        record.payload = (uint8_t *)(uintptr_t)data;
        record.payload_bytes = size > UINT32_MAX ? UINT32_MAX : (uint32_t)size;
        if (size <= UINT32_MAX) (void)otrl_parse_projection(&record, NULL);
    }
#elif FUZZ_MODE == 5
    fuzz_bounded_command_input(data, size);
#elif FUZZ_MODE == 6 || FUZZ_MODE == 7
    if (size <= OTRL_MAX_RECORD_PAYLOAD_BYTES) {
        (void)otrl_validate_canonical_json(data, size, NULL);
    }
#elif FUZZ_MODE == 8
    fuzz_pair(data, size, 0);
#elif FUZZ_MODE == 9
    fuzz_pair(data, size, 1);
#else
    fuzz_one_tape(data, size);
#endif
    return 0;
}
