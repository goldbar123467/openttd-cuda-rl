/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OTRL_STATUS_H
#define OTRL_STATUS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define OTRL_ABI_VERSION UINT32_C(1)
#define OTRL_ERROR_MESSAGE_BYTES 192U

typedef enum otrl_status {
    OTRL_OK = 0,
    OTRL_E_USAGE,
    OTRL_E_IO,
    OTRL_E_TRUNCATED,
    OTRL_E_MAGIC,
    OTRL_E_VERSION,
    OTRL_E_ENDIAN,
    OTRL_E_HASH_ALGORITHM,
    OTRL_E_CHECKSUM,
    OTRL_E_CANONICAL,
    OTRL_E_RESERVED,
    OTRL_E_LIMIT,
    OTRL_E_OVERFLOW,
    OTRL_E_SEQUENCE,
    OTRL_E_STRUCTURE,
    OTRL_E_SCHEMA,
    OTRL_E_IDENTITY,
    OTRL_E_DIVERGENCE,
    OTRL_E_INVARIANT,
    OTRL_E_INTERNAL
} otrl_status;

typedef struct otrl_error {
    uint32_t size;
    uint32_t version;
    uint64_t byte_offset;
    uint64_t record_sequence;
    uint64_t public_step;
    uint64_t native_tick;
    uint32_t field_id;
    uint32_t reserved;
    char message[OTRL_ERROR_MESSAGE_BYTES];
} otrl_error;

const char *otrl_status_string(otrl_status status);
void otrl_error_init(otrl_error *error);

#ifdef __cplusplus
}
#endif
#endif
