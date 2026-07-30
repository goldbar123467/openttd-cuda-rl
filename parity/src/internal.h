/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OTRL_INTERNAL_H
#define OTRL_INTERNAL_H

#include "openttd_rl_parity/comparator.h"

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

typedef struct otrl_record_internal {
    uint16_t type;
    uint16_t version;
    uint32_t flags;
    uint64_t sequence;
    uint64_t public_step;
    uint64_t native_tick;
    uint32_t payload_bytes;
    size_t record_offset;
    size_t padded_bytes;
    uint8_t *payload;
} otrl_record_internal;

struct otrl_context {
    otrl_allocate_fn allocate;
    otrl_free_fn free;
    void *allocator_user;
    uint64_t local_max_tape_bytes;
    uint64_t local_max_record_count;
};

struct otrl_tape {
    uint16_t major;
    uint16_t minor;
    uint32_t flags;
    uint64_t record_count;
    uint64_t record_bytes;
    uint64_t max_step;
    uint64_t max_tick;
    uint32_t header_bytes;
    uint8_t *header;
    otrl_record_internal *records;
    uint8_t digest[32];
    const uint8_t *mapped_bytes;
    size_t mapped_length;
    int owns_mapping;
};

typedef struct otrl_record_cursor {
    const otrl_tape *tape;
    uint64_t index;
    size_t offset;
    size_t released_offset;
    size_t page_size;
    otrl_record_internal scratch;
} otrl_record_cursor;

struct otrl_writer {
    otrl_context *context;
    uint32_t flags;
    uint32_t header_bytes;
    uint8_t *header;
    uint64_t count;
    uint64_t capacity;
    otrl_record_internal *records;
    int finalized;
};

void *otrl_alloc(otrl_context *context, size_t bytes);
void otrl_dealloc(otrl_context *context, void *pointer);
#if defined(__GNUC__) || defined(__clang__)
__attribute__((format(printf, 8, 9)))
#endif
void otrl_set_error(otrl_error *error, otrl_status status, size_t offset,
                    uint64_t sequence, uint64_t step, uint64_t tick,
                    uint32_t field_id, const char *format, ...);
int otrl_valid_public_struct(const void *object, uint32_t actual_size,
                             uint32_t required_size, uint32_t version);
otrl_status otrl_sha256(const uint8_t *bytes, size_t length, uint8_t digest[32]);
otrl_status otrl_sha256_mapped(const uint8_t *bytes, size_t length,
                               uint8_t digest[32]);
otrl_status otrl_validate_canonical_header(const uint8_t *bytes, size_t length,
                                           otrl_error *error);
otrl_status otrl_validate_canonical_json(const uint8_t *bytes, size_t length,
                                         otrl_error *error);
int otrl_utf8_valid(const uint8_t *bytes, size_t length);
otrl_status otrl_parse_projection(const otrl_record_internal *record,
                                  otrl_error *error);
otrl_status otrl_serialize_tape(otrl_writer *writer, uint8_t **out_bytes,
                                size_t *out_length, otrl_error *error);
otrl_status otrl_write_atomic(const char *path, const uint8_t *bytes,
                              size_t length, otrl_error *error);
size_t otrl_find_first_true(const uint8_t *predicate, size_t count,
                            int *used_linear_fallback);
void otrl_record_cursor_init(const otrl_tape *tape, otrl_record_cursor *cursor);
const otrl_record_internal *otrl_record_cursor_next(otrl_record_cursor *cursor);

#endif
