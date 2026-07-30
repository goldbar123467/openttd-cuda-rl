/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *const OTRL_STATUS_NAMES[] = {
    "OK", "usage", "io", "truncated", "magic", "version", "endian",
    "hash_algorithm", "checksum", "canonical", "reserved", "limit",
    "overflow", "sequence", "structure", "schema", "identity",
    "divergence", "invariant", "internal"
};

const char *otrl_status_string(otrl_status status)
{
    const unsigned int index = (unsigned int)status;
    if (index >= (sizeof(OTRL_STATUS_NAMES) / sizeof(OTRL_STATUS_NAMES[0]))) {
        return "unknown_status";
    }
    return OTRL_STATUS_NAMES[index];
}

void otrl_error_init(otrl_error *error)
{
    if (error != NULL) {
        memset(error, 0, sizeof(*error));
        error->size = (uint32_t)sizeof(*error);
        error->version = OTRL_ABI_VERSION;
        error->record_sequence = UINT64_MAX;
    }
}

void otrl_set_error(otrl_error *error, otrl_status status, size_t offset,
                    uint64_t sequence, uint64_t step, uint64_t tick,
                    uint32_t field_id, const char *format, ...)
{
    va_list arguments;
    if (error == NULL) {
        return;
    }
    otrl_error_init(error);
    error->byte_offset = (uint64_t)offset;
    error->record_sequence = sequence;
    error->public_step = step;
    error->native_tick = tick;
    error->field_id = field_id;
    va_start(arguments, format);
    (void)vsnprintf(error->message, sizeof(error->message), format, arguments);
    va_end(arguments);
    if (error->message[0] == '\0') {
        (void)snprintf(error->message, sizeof(error->message), "%s",
                       otrl_status_string(status));
    }
}

static void *otrl_default_allocate(void *user, size_t bytes)
{
    (void)user;
    return malloc(bytes);
}

static void otrl_default_free(void *user, void *pointer)
{
    (void)user;
    free(pointer);
}

void *otrl_alloc(otrl_context *context, size_t bytes)
{
    if (context == NULL || bytes == 0U) {
        return NULL;
    }
    return context->allocate(context->allocator_user, bytes);
}

void otrl_dealloc(otrl_context *context, void *pointer)
{
    if (context != NULL && pointer != NULL) {
        context->free(context->allocator_user, pointer);
    }
}

int otrl_valid_public_struct(const void *object, uint32_t actual_size,
                             uint32_t required_size, uint32_t version)
{
    return object != NULL && actual_size >= required_size &&
           version == OTRL_ABI_VERSION;
}

otrl_status otrl_context_create(const otrl_context_options *options,
                                otrl_context **out_context,
                                otrl_error *error)
{
    otrl_context temporary;
    otrl_context *result;
    if (out_context == NULL) {
        otrl_set_error(error, OTRL_E_USAGE, 0U, UINT64_MAX, 0U, 0U, 0U,
                       "out_context is required");
        return OTRL_E_USAGE;
    }
    if (options != NULL &&
        !otrl_valid_public_struct(options, options->size,
                                  (uint32_t)sizeof(*options), options->version)) {
        otrl_set_error(error, OTRL_E_USAGE, 0U, UINT64_MAX, 0U, 0U, 0U,
                       "invalid context options ABI");
        return OTRL_E_USAGE;
    }
    memset(&temporary, 0, sizeof(temporary));
    temporary.allocate = otrl_default_allocate;
    temporary.free = otrl_default_free;
    temporary.local_max_tape_bytes = OTRL_MAX_TAPE_BYTES;
    temporary.local_max_record_count = OTRL_MAX_RECORD_COUNT;
    if (options != NULL) {
        size_t index;
        for (index = 0U; index < 4U; ++index) {
            if (options->reserved[index] != 0U) {
                otrl_set_error(error, OTRL_E_RESERVED, 0U, UINT64_MAX, 0U, 0U,
                               0U, "context reserved field is nonzero");
                return OTRL_E_RESERVED;
            }
        }
        if ((options->allocate == NULL) != (options->free == NULL)) {
            otrl_set_error(error, OTRL_E_USAGE, 0U, UINT64_MAX, 0U, 0U, 0U,
                           "allocator and free must be supplied together");
            return OTRL_E_USAGE;
        }
        if (options->allocate != NULL) {
            temporary.allocate = options->allocate;
            temporary.free = options->free;
            temporary.allocator_user = options->allocator_user;
        }
        if (options->local_max_tape_bytes != 0U) {
            if (options->local_max_tape_bytes > OTRL_MAX_TAPE_BYTES) {
                otrl_set_error(error, OTRL_E_LIMIT, 0U, UINT64_MAX, 0U, 0U, 0U,
                               "local tape limit exceeds format limit");
                return OTRL_E_LIMIT;
            }
            temporary.local_max_tape_bytes = options->local_max_tape_bytes;
        }
        if (options->local_max_record_count != 0U) {
            if (options->local_max_record_count > OTRL_MAX_RECORD_COUNT) {
                otrl_set_error(error, OTRL_E_LIMIT, 0U, UINT64_MAX, 0U, 0U, 0U,
                               "local record limit exceeds format limit");
                return OTRL_E_LIMIT;
            }
            temporary.local_max_record_count = options->local_max_record_count;
        }
    }
    result = temporary.allocate(temporary.allocator_user, sizeof(*result));
    if (result == NULL) {
        otrl_set_error(error, OTRL_E_IO, 0U, UINT64_MAX, 0U, 0U, 0U,
                       "context allocation failed");
        return OTRL_E_IO;
    }
    *result = temporary;
    *out_context = result;
    return OTRL_OK;
}

void otrl_context_destroy(otrl_context *context)
{
    if (context != NULL) {
        otrl_free_fn free_function = context->free;
        void *user = context->allocator_user;
        free_function(user, context);
    }
}

void otrl_bytes_destroy(otrl_context *context, uint8_t *bytes)
{
    otrl_dealloc(context, bytes);
}
