/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OTRL_COMPARE_H
#define OTRL_COMPARE_H

#include "openttd_rl_parity/tape_reader.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum otrl_divergence_kind {
    OTRL_DIVERGENCE_NONE = 0,
    OTRL_DIVERGENCE_RECORD = 1,
    OTRL_DIVERGENCE_FIELD_PRESENCE = 2,
    OTRL_DIVERGENCE_FIELD_VALUE = 3,
    OTRL_DIVERGENCE_END_OF_STREAM = 4
} otrl_divergence_kind;

typedef struct otrl_compare_result {
    uint32_t size;
    uint32_t version;
    uint32_t kind;
    uint32_t field_id;
    uint64_t record_sequence;
    uint64_t public_step;
    uint64_t native_tick;
    uint16_t record_type;
    uint16_t value_type;
    uint32_t element_index;
    uint32_t oracle_value_bytes;
    uint32_t target_value_bytes;
    uint8_t oracle_value[16];
    uint8_t target_value[16];
    uint64_t target_record_sequence;
    uint64_t boundary_ordinal;
    uint32_t boundary_kind;
    uint32_t value_width_bits;
    uint32_t value_signed;
    uint32_t logical_environment_id;
    uint64_t last_command_intent_sequence;
    uint64_t last_command_test_sequence;
    uint64_t last_command_exec_sequence;
    uint64_t previous_checkpoint_sequence;
    uint8_t oracle_tape_sha256[OTRL_SHA256_BYTES];
    uint8_t target_tape_sha256[OTRL_SHA256_BYTES];
    char oracle_backend[64];
    char target_backend[64];
    char field_path[128];
    char source_anchor[192];
    char cache_class[32];
    uint32_t diagnostics_differ_ignored;
    uint32_t command_id;
    uint32_t command_operand_index;
    uint32_t reserved0;
    uint64_t reserved[3];
} otrl_compare_result;

otrl_status otrl_compare(const otrl_tape *oracle,
                         const otrl_tape *target,
                         otrl_compare_result *result,
                         otrl_error *error);

otrl_status otrl_minimize_prefix(otrl_context *context,
                                 const otrl_tape *oracle,
                                 const otrl_tape *target,
                                 const char *output_path,
                                 otrl_compare_result *result,
                                 otrl_error *error);

#ifdef __cplusplus
}
#endif
#endif
