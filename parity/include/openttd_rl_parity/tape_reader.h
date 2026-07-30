/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OTRL_TAPE_H
#define OTRL_TAPE_H

#include "openttd_rl_parity/status.h"
#include "openttd_rl_parity/tape_format.h"

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct otrl_context otrl_context;
typedef struct otrl_tape otrl_tape;
typedef struct otrl_writer otrl_writer;

typedef void *(*otrl_allocate_fn)(void *user, size_t bytes);
typedef void (*otrl_free_fn)(void *user, void *pointer);

typedef struct otrl_context_options {
    uint32_t size;
    uint32_t version;
    uint64_t local_max_tape_bytes;
    uint64_t local_max_record_count;
    otrl_allocate_fn allocate;
    otrl_free_fn free;
    void *allocator_user;
    uint64_t reserved[4];
} otrl_context_options;

typedef struct otrl_record_view {
    uint32_t size;
    uint32_t version;
    uint16_t type;
    uint16_t record_version;
    uint32_t flags;
    uint64_t sequence;
    uint64_t public_step;
    uint64_t native_tick;
    const uint8_t *payload;
    uint32_t payload_bytes;
    uint32_t reserved;
} otrl_record_view;

typedef otrl_status (*otrl_record_callback)(void *user,
                                            const otrl_record_view *record,
                                            otrl_error *error);

typedef struct otrl_tape_info {
    uint32_t size;
    uint32_t version;
    uint16_t format_major;
    uint16_t format_minor;
    uint32_t flags;
    uint64_t record_count;
    uint64_t record_bytes;
    uint64_t maximum_public_step;
    uint64_t maximum_native_tick;
    const uint8_t *header_json;
    uint32_t header_bytes;
    uint32_t reserved;
    uint8_t covered_sha256[OTRL_SHA256_BYTES];
} otrl_tape_info;

typedef struct otrl_writer_options {
    uint32_t size;
    uint32_t version;
    uint32_t flags;
    uint32_t reserved;
    const uint8_t *header_json;
    uint32_t header_bytes;
    uint32_t reserved2;
    uint64_t reserved3[4];
} otrl_writer_options;

otrl_status otrl_context_create(const otrl_context_options *options,
                                otrl_context **out_context,
                                otrl_error *error);
void otrl_context_destroy(otrl_context *context);

otrl_status otrl_validate_bytes(otrl_context *context,
                                const uint8_t *bytes,
                                size_t length,
                                otrl_tape **out_tape,
                                otrl_error *error);
otrl_status otrl_validate_file(otrl_context *context,
                               const char *path,
                               otrl_tape **out_tape,
                               otrl_error *error);
void otrl_tape_destroy(otrl_context *context, otrl_tape *tape);
otrl_status otrl_tape_get_info(const otrl_tape *tape, otrl_tape_info *out_info,
                               otrl_error *error);
otrl_status otrl_tape_iterate(const otrl_tape *tape,
                              otrl_record_callback callback,
                              void *user,
                              otrl_error *error);

otrl_status otrl_writer_create(otrl_context *context,
                               const otrl_writer_options *options,
                               otrl_writer **out_writer,
                               otrl_error *error);
otrl_status otrl_writer_add_record(otrl_writer *writer,
                                   const otrl_record_view *record,
                                   otrl_error *error);
otrl_status otrl_writer_finalize_bytes(otrl_writer *writer,
                                       uint8_t **out_bytes,
                                       size_t *out_length,
                                       otrl_error *error);
otrl_status otrl_writer_finalize_file(otrl_writer *writer,
                                      const char *path,
                                      otrl_error *error);
void otrl_writer_destroy(otrl_writer *writer);
void otrl_bytes_destroy(otrl_context *context, uint8_t *bytes);

int otrl_checked_add_size(size_t a, size_t b, size_t *out);
int otrl_checked_mul_size(size_t a, size_t b, size_t *out);
int otrl_checked_align8_size(size_t value, size_t *out);

#ifdef __cplusplus
}
#endif
#endif
