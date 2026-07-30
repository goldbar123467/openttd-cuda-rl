/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"
#include "openttd_rl_parity/field_schema.h"

#include <errno.h>
#include <fcntl.h>
#include <openssl/evp.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int stream_write_all(int descriptor, const uint8_t *bytes, size_t length)
{
    size_t offset = 0U;
    while (offset < length) {
        ssize_t amount;
        do {
            amount = write(descriptor, bytes + offset, length - offset);
        } while (amount < 0 && errno == EINTR);
        if (amount <= 0) return 0;
        offset += (size_t)amount;
    }
    return 1;
}

static int stream_write_covered(int descriptor, EVP_MD_CTX *digest,
                                const uint8_t *bytes, size_t length)
{
    return EVP_DigestUpdate(digest, bytes, length) == 1 &&
           stream_write_all(descriptor, bytes, length);
}

static int parent_directory(const char *path, char *parent, size_t capacity)
{
    char *slash;
    const int written = snprintf(parent, capacity, "%s", path);
    if (written < 0 || (size_t)written >= capacity) return 0;
    slash = strrchr(parent, '/');
    if (slash == NULL) return snprintf(parent, capacity, ".") == 1;
    if (slash == parent) slash[1] = '\0';
    else *slash = '\0';
    return 1;
}

static otrl_status promote_stream_file(const char *temporary, const char *path,
                                       otrl_error *error)
{
    char parent[4096];
    int directory;
    int result;
    if (!parent_directory(path, parent, sizeof(parent)) ||
        link(temporary, path) != 0) return OTRL_E_IO;
#ifdef O_DIRECTORY
    directory = open(parent, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
#else
    directory = open(parent, O_RDONLY | O_CLOEXEC);
#endif
    if (directory < 0) goto rollback;
    do { result = fsync(directory); } while (result != 0 && errno == EINTR);
    if (result != 0 || unlink(temporary) != 0) goto rollback_open;
    do { result = fsync(directory); } while (result != 0 && errno == EINTR);
    if (result != 0 || close(directory) != 0) goto rollback_closed;
    return OTRL_OK;

rollback_open:
    (void)unlink(path);
    (void)unlink(temporary);
    (void)fsync(directory);
    (void)close(directory);
    otrl_set_error(error, OTRL_E_IO, 0U, UINT64_MAX, 0U, 0U, 0U,
                   "streaming output promotion failed");
    return OTRL_E_IO;
rollback_closed:
    (void)unlink(path);
    otrl_set_error(error, OTRL_E_IO, 0U, UINT64_MAX, 0U, 0U, 0U,
                   "streaming output directory close failed");
    return OTRL_E_IO;
rollback:
    (void)unlink(path);
    (void)unlink(temporary);
    otrl_set_error(error, OTRL_E_IO, 0U, UINT64_MAX, 0U, 0U, 0U,
                   "streaming output directory open failed");
    return OTRL_E_IO;
}

static int diagnostic_type(uint16_t type)
{
    return type == OTRL_RECORD_RNG_DRAW_DIAGNOSTIC ||
           type == OTRL_RECORD_ROUTE_DIAGNOSTIC ||
           type == OTRL_RECORD_CARGO_DIAGNOSTIC ||
           type == OTRL_RECORD_TRACE_WARNING;
}

static int ignorable_diagnostic(const otrl_record_internal *record)
{
    return diagnostic_type(record->type) &&
           (record->flags & OTRL_RECORD_FLAG_REQUIRED) == 0U;
}

static int __attribute__((unused)) identity_span(const uint8_t *header, size_t length,
                         const uint8_t **start, size_t *span)
{
    static const char marker[] = "\"identity\":";
    size_t i;
    for (i = 0U; i + sizeof(marker) - 1U < length; ++i) {
        if (memcmp(header + i, marker, sizeof(marker) - 1U) == 0) {
            size_t cursor = i + sizeof(marker) - 1U;
            size_t depth = 0U;
            int in_string = 0;
            int escaped = 0;
            if (header[cursor] != '{') {
                return 0;
            }
            *start = header + cursor;
            for (; cursor < length; ++cursor) {
                const uint8_t byte = header[cursor];
                if (in_string) {
                    if (escaped) {
                        escaped = 0;
                    } else if (byte == '\\') {
                        escaped = 1;
                    } else if (byte == '"') {
                        in_string = 0;
                    }
                } else if (byte == '"') {
                    in_string = 1;
                } else if (byte == '{') {
                    ++depth;
                } else if (byte == '}') {
                    if (--depth == 0U) {
                        *span = (size_t)(header + cursor + 1U - *start);
                        return 1;
                    }
                }
            }
            return 0;
        }
    }
    return 0;
}

static int header_string(const uint8_t *header, size_t length, const char *key,
                         const uint8_t **value, size_t *value_length)
{
    char marker[96];
    int written = snprintf(marker, sizeof(marker), "\"%s\":\"", key);
    if (written <= 0 || (size_t)written >= sizeof(marker)) return 0;
    for (size_t i = 0U; i + (size_t)written < length; ++i) {
        if (memcmp(header + i, marker, (size_t)written) == 0) {
            size_t end = i + (size_t)written;
            while (end < length && header[end] != '"') ++end;
            if (end == length) return 0;
            *value = header + i + (size_t)written;
            *value_length = end - (i + (size_t)written);
            return 1;
        }
    }
    return 0;
}

static void result_base(otrl_compare_result *result,
                        const otrl_record_internal *record,
                        otrl_divergence_kind kind)
{
    memset(result, 0, sizeof(*result));
    result->size = (uint32_t)sizeof(*result);
    result->version = OTRL_ABI_VERSION;
    result->kind = (uint32_t)kind;
    result->record_sequence = UINT64_MAX;
    result->target_record_sequence = UINT64_MAX;
    result->last_command_intent_sequence = UINT64_MAX;
    result->last_command_test_sequence = UINT64_MAX;
    result->last_command_exec_sequence = UINT64_MAX;
    result->previous_checkpoint_sequence = UINT64_MAX;
    if (record != NULL) {
        result->record_sequence = record->sequence;
        result->public_step = record->public_step;
        result->native_tick = record->native_tick;
        result->record_type = record->type;
    }
}

static void copy_label(char *destination, size_t capacity,
                       const uint8_t *source, size_t length)
{
    const size_t amount = length < capacity - 1U ? length : capacity - 1U;
    memcpy(destination, source, amount);
    destination[amount] = '\0';
}

static void add_context(const otrl_tape *oracle, const otrl_tape *target,
                        uint64_t oracle_index, uint64_t target_index,
                        otrl_compare_result *result)
{
    otrl_record_cursor oracle_cursor;
    otrl_record_cursor target_cursor;
    const otrl_record_internal *record;
    const uint8_t *label;
    size_t label_bytes;
    result->target_record_sequence = UINT64_MAX;
    otrl_record_cursor_init(target, &target_cursor);
    while ((record = otrl_record_cursor_next(&target_cursor)) != NULL) {
        if (record->sequence == target_index) {
            result->target_record_sequence = record->sequence;
            break;
        }
    }
    memcpy(result->oracle_tape_sha256, oracle->digest, 32U);
    memcpy(result->target_tape_sha256, target->digest, 32U);
    if (header_string(oracle->header, oracle->header_bytes, "backend_label",
                      &label, &label_bytes)) {
        copy_label(result->oracle_backend, sizeof(result->oracle_backend), label,
                   label_bytes);
    }
    if (header_string(target->header, target->header_bytes, "backend_label",
                      &label, &label_bytes)) {
        copy_label(result->target_backend, sizeof(result->target_backend), label,
                   label_bytes);
    }
    otrl_record_cursor_init(oracle, &oracle_cursor);
    while ((record = otrl_record_cursor_next(&oracle_cursor)) != NULL &&
           record->sequence < oracle_index) {
        switch (record->type) {
        case OTRL_RECORD_COMMAND_INTENT:
            result->last_command_intent_sequence = record->sequence; break;
        case OTRL_RECORD_COMMAND_TEST_RESULT:
            result->last_command_test_sequence = record->sequence; break;
        case OTRL_RECORD_COMMAND_EXEC_RESULT:
            result->last_command_exec_sequence = record->sequence; break;
        case OTRL_RECORD_NAMED_CHECKPOINT:
            result->previous_checkpoint_sequence = record->sequence; break;
        default: break;
        }
    }
    if (record != NULL && record->sequence == oracle_index &&
        record->type == OTRL_RECORD_AUTHORITATIVE_PROJECTION) {
        const uint8_t *payload = record->payload;
        result->boundary_kind = payload[2];
        result->boundary_ordinal = otrl_get_u64_le(payload + 8U);
    }
}

static size_t field_width(uint16_t type, uint16_t flags)
{
    if (type == OTRL_VALUE_U8 || type == OTRL_VALUE_I8) return 1U;
    if (type == OTRL_VALUE_U16 || type == OTRL_VALUE_I16) return 2U;
    if (type == OTRL_VALUE_U32 || type == OTRL_VALUE_I32) return 4U;
    if (type == OTRL_VALUE_U64 || type == OTRL_VALUE_I64) return 8U;
    if (type == OTRL_VALUE_STABLE_ID) return flags;
    return 1U;
}

static void set_value_difference(otrl_compare_result *result,
                                 const otrl_record_internal *record,
                                 const char *path, uint16_t value_type,
                                 uint32_t width_bits, uint32_t is_signed,
                                 uint32_t element_index,
                                 const uint8_t *oracle_value,
                                 const uint8_t *target_value,
                                 size_t value_bytes)
{
    const size_t copy_bytes = value_bytes < sizeof(result->oracle_value) ?
                              value_bytes : sizeof(result->oracle_value);
    result_base(result, record, OTRL_DIVERGENCE_RECORD);
    result->value_type = value_type;
    result->value_width_bits = width_bits;
    result->value_signed = is_signed;
    result->element_index = element_index;
    result->oracle_value_bytes = (uint32_t)copy_bytes;
    result->target_value_bytes = (uint32_t)copy_bytes;
    memcpy(result->oracle_value, oracle_value, copy_bytes);
    memcpy(result->target_value, target_value, copy_bytes);
    (void)snprintf(result->field_path, sizeof(result->field_path), "%s", path);
}

static otrl_status compare_raw_tail(const otrl_record_internal *left,
                                    const otrl_record_internal *right,
                                    size_t offset, const char *path,
                                    otrl_compare_result *result)
{
    const size_t left_bytes = left->payload_bytes - offset;
    const size_t right_bytes = right->payload_bytes - offset;
    size_t first = 0U;
    while (first < left_bytes && first < right_bytes &&
           left->payload[offset + first] == right->payload[offset + first]) {
        ++first;
    }
    if (first == left_bytes && first == right_bytes) return OTRL_OK;
    {
        static const uint8_t absent = 0U;
        const uint8_t *left_value = first < left_bytes ?
                                    left->payload + offset + first : &absent;
        const uint8_t *right_value = first < right_bytes ?
                                     right->payload + offset + first : &absent;
        set_value_difference(result, left, path, OTRL_VALUE_BYTES, 8U, 0U,
                             (uint32_t)first, left_value, right_value, 1U);
    }
    return OTRL_E_DIVERGENCE;
}

static otrl_status compare_command(const otrl_record_internal *left,
                                   const otrl_record_internal *right,
                                   otrl_compare_result *result)
{
    const int intent = left->type == OTRL_RECORD_COMMAND_INTENT;
    if (left->payload_bytes != right->payload_bytes) {
        result_base(result, left, OTRL_DIVERGENCE_RECORD);
        (void)snprintf(result->field_path, sizeof(result->field_path), "%s",
                       intent ? "command.intent.payload_bytes" :
                                "command.outcome.payload_bytes");
        return OTRL_E_DIVERGENCE;
    }
    if (!intent && left->payload[2] != right->payload[2]) {
        set_value_difference(result, left, "command.outcome.success",
                             OTRL_VALUE_U8, 8U, 0U, 0U,
                             left->payload + 2U, right->payload + 2U, 1U);
        result->command_id = otrl_get_u32_le(left->payload + 4U);
        return OTRL_E_DIVERGENCE;
    }
    if (intent) {
        static const struct {
            size_t offset;
            const char *path;
        } intent_fields[] = {
            {4U, "command.intent.native_command"},
            {8U, "command.intent.company"},
            {12U, "command.intent.command_flags"},
            {16U, "command.intent.raw_bytes"}
        };
        for (size_t i = 0U; i < sizeof(intent_fields) / sizeof(intent_fields[0]); ++i) {
            if (memcmp(left->payload + intent_fields[i].offset,
                       right->payload + intent_fields[i].offset, 4U) != 0) {
                set_value_difference(result, left, intent_fields[i].path,
                                     OTRL_VALUE_U32, 32U, 0U, 0U,
                                     left->payload + intent_fields[i].offset,
                                     right->payload + intent_fields[i].offset, 4U);
                result->command_id = otrl_get_u32_le(left->payload + 4U);
                return OTRL_E_DIVERGENCE;
            }
        }
        if (compare_raw_tail(left, right, 24U, "command.intent.operand",
                             result) != OTRL_OK) {
            result->command_id = otrl_get_u32_le(left->payload + 4U);
            result->command_operand_index = result->element_index;
            return OTRL_E_DIVERGENCE;
        }
    } else {
        static const struct {
            size_t offset;
            const char *path;
            uint16_t type;
            uint32_t width;
            uint32_t is_signed;
        } outcome_fields[] = {
            {4U, "command.outcome.native_command", OTRL_VALUE_U32, 32U, 0U},
            {8U, "command.outcome.cost", OTRL_VALUE_I64, 64U, 1U},
            {16U, "command.outcome.expense_type", OTRL_VALUE_U32, 32U, 0U},
            {20U, "command.outcome.error", OTRL_VALUE_U32, 32U, 0U},
            {24U, "command.outcome.extra_error", OTRL_VALUE_U32, 32U, 0U},
            {28U, "command.outcome.result_bytes", OTRL_VALUE_U32, 32U, 0U}
        };
        for (size_t i = 0U; i < sizeof(outcome_fields) / sizeof(outcome_fields[0]); ++i) {
            const size_t bytes = outcome_fields[i].width / 8U;
            if (memcmp(left->payload + outcome_fields[i].offset,
                       right->payload + outcome_fields[i].offset, bytes) != 0) {
                set_value_difference(result, left, outcome_fields[i].path,
                                     outcome_fields[i].type,
                                     outcome_fields[i].width,
                                     outcome_fields[i].is_signed, 0U,
                                     left->payload + outcome_fields[i].offset,
                                     right->payload + outcome_fields[i].offset,
                                     bytes);
                result->command_id = otrl_get_u32_le(left->payload + 4U);
                return OTRL_E_DIVERGENCE;
            }
        }
        if (compare_raw_tail(left, right, 32U, "command.outcome.result_payload",
                             result) != OTRL_OK) {
            result->command_id = otrl_get_u32_le(left->payload + 4U);
            result->command_operand_index = result->element_index;
            return OTRL_E_DIVERGENCE;
        }
    }
    return OTRL_OK;
}

typedef struct field_cursor {
    const uint8_t *payload;
    size_t length;
    size_t offset;
    uint32_t remaining;
} field_cursor;

typedef struct field_view {
    uint32_t id;
    uint16_t type;
    uint16_t flags;
    uint32_t elements;
    uint32_t bytes;
    const uint8_t *value;
} field_view;

static int next_field(field_cursor *cursor, field_view *field)
{
    size_t end;
    if (cursor->remaining == 0U || cursor->length - cursor->offset < 16U) {
        return 0;
    }
    field->id = otrl_get_u32_le(cursor->payload + cursor->offset);
    field->type = otrl_get_u16_le(cursor->payload + cursor->offset + 4U);
    field->flags = otrl_get_u16_le(cursor->payload + cursor->offset + 6U);
    field->elements = otrl_get_u32_le(cursor->payload + cursor->offset + 8U);
    field->bytes = otrl_get_u32_le(cursor->payload + cursor->offset + 12U);
    cursor->offset += 16U;
    field->value = cursor->payload + cursor->offset;
    if (!otrl_checked_add_size(cursor->offset, field->bytes, &end) ||
        !otrl_checked_align8_size(end, &cursor->offset) ||
        cursor->offset > cursor->length) {
        return 0;
    }
    --cursor->remaining;
    return 1;
}

static otrl_status compare_projection(const otrl_record_internal *left,
                                      const otrl_record_internal *right,
                                      otrl_compare_result *result)
{
    field_cursor a = {left->payload, left->payload_bytes, 24U,
                      otrl_get_u32_le(left->payload + 4U)};
    field_cursor b = {right->payload, right->payload_bytes, 24U,
                      otrl_get_u32_le(right->payload + 4U)};
    if (memcmp(left->payload, right->payload, 24U) != 0) {
        result_base(result, left, OTRL_DIVERGENCE_RECORD);
        return OTRL_E_DIVERGENCE;
    }
    while (a.remaining != 0U || b.remaining != 0U) {
        field_view af;
        field_view bf;
        const int have_a = next_field(&a, &af);
        const int have_b = next_field(&b, &bf);
        if (!have_a || !have_b || af.id != bf.id) {
            result_base(result, left, OTRL_DIVERGENCE_FIELD_PRESENCE);
            result->field_id = have_a ? af.id : (have_b ? bf.id : 0U);
            return OTRL_E_DIVERGENCE;
        }
        if (af.type != bf.type || af.flags != bf.flags ||
            af.elements != bf.elements || af.bytes != bf.bytes) {
            result_base(result, left, OTRL_DIVERGENCE_FIELD_VALUE);
            result->field_id = af.id;
            result->value_type = af.type;
            result->value_width_bits = (uint32_t)(field_width(af.type, af.flags) * 8U);
            result->value_signed = af.type >= OTRL_VALUE_I8 && af.type <= OTRL_VALUE_I64;
            {
                const otrl_field_meta *meta = otrl_field_lookup(af.id);
                (void)snprintf(result->field_path, sizeof(result->field_path), "%s",
                               meta == NULL ? "unknown" : meta->path);
                (void)snprintf(result->source_anchor, sizeof(result->source_anchor),
                               "%s", meta == NULL ? "unknown" : meta->source_anchor);
                (void)snprintf(result->cache_class, sizeof(result->cache_class), "%s",
                               meta == NULL ? "unknown" : meta->cache_class);
            }
            return OTRL_E_DIVERGENCE;
        }
        if (memcmp(af.value, bf.value, af.bytes) != 0) {
            size_t first = 0U;
            size_t width = field_width(af.type, af.flags);
            size_t element_start;
            size_t copy_bytes;
            while (first < af.bytes && af.value[first] == bf.value[first]) {
                ++first;
            }
            element_start = width == 0U ? first : (first / width) * width;
            copy_bytes = af.bytes - element_start;
            if (copy_bytes > sizeof(result->oracle_value)) {
                copy_bytes = sizeof(result->oracle_value);
            }
            result_base(result, left, OTRL_DIVERGENCE_FIELD_VALUE);
            result->field_id = af.id;
            result->value_type = af.type;
            result->value_width_bits = (uint32_t)(width * 8U);
            result->value_signed = af.type >= OTRL_VALUE_I8 && af.type <= OTRL_VALUE_I64;
            result->element_index = width == 0U ? (uint32_t)first :
                                    (uint32_t)(first / width);
            result->oracle_value_bytes = (uint32_t)copy_bytes;
            result->target_value_bytes = (uint32_t)copy_bytes;
            memcpy(result->oracle_value, af.value + element_start, copy_bytes);
            memcpy(result->target_value, bf.value + element_start, copy_bytes);
            {
                const otrl_field_meta *meta = otrl_field_lookup(af.id);
                (void)snprintf(result->field_path, sizeof(result->field_path), "%s",
                               meta == NULL ? "unknown" : meta->path);
                (void)snprintf(result->source_anchor, sizeof(result->source_anchor),
                               "%s", meta == NULL ? "unknown" : meta->source_anchor);
                (void)snprintf(result->cache_class, sizeof(result->cache_class), "%s",
                               meta == NULL ? "unknown" : meta->cache_class);
            }
            return OTRL_E_DIVERGENCE;
        }
    }
    return OTRL_OK;
}

otrl_status otrl_compare(const otrl_tape *oracle, const otrl_tape *target,
                         otrl_compare_result *result, otrl_error *error)
{
    static const char *const identity_keys[] = {
        "source_commit", "build_sha256", "executable_sha256", "fixture_sha256",
        "settings_sha256", "content_sha256", "command_input_sha256",
        "command_schema_sha256", "field_schema_sha256", "instrumentation_sha256"
    };
    uint64_t i = 0U;
    uint64_t j = 0U;
    otrl_record_cursor oracle_cursor;
    otrl_record_cursor target_cursor;
    const otrl_record_internal *left;
    const otrl_record_internal *right;
    int diagnostics_differ = 0;
    otrl_compare_result temporary;
    if (oracle == NULL || target == NULL || result == NULL ||
        !otrl_valid_public_struct(result, result->size,
                                  (uint32_t)sizeof(*result), result->version)) {
        return OTRL_E_USAGE;
    }
    if (result->reserved0 != 0U) {
        return OTRL_E_RESERVED;
    }
    for (size_t reserved = 0U; reserved < 3U; ++reserved) {
        if (result->reserved[reserved] != 0U) {
            return OTRL_E_RESERVED;
        }
    }
    if (oracle->major != target->major || oracle->minor != target->minor) {
        return OTRL_E_VERSION;
    }
    for (size_t identity = 0U;
         identity < sizeof(identity_keys) / sizeof(identity_keys[0]); ++identity) {
        const uint8_t *left_value;
        const uint8_t *right_value;
        size_t left_bytes;
        size_t right_bytes;
        if (!header_string(oracle->header, oracle->header_bytes,
                           identity_keys[identity], &left_value, &left_bytes) ||
            !header_string(target->header, target->header_bytes,
                           identity_keys[identity], &right_value, &right_bytes)) {
            return OTRL_E_SCHEMA;
        }
        if (left_bytes != right_bytes || memcmp(left_value, right_value, left_bytes) != 0) {
            otrl_set_error(error, OTRL_E_IDENTITY, 0U, UINT64_MAX, 0U, 0U, 0U,
                           "identity mismatch: %s", identity_keys[identity]);
            return OTRL_E_IDENTITY;
        }
    }
    result_base(&temporary, NULL, OTRL_DIVERGENCE_NONE);
    otrl_record_cursor_init(oracle, &oracle_cursor);
    otrl_record_cursor_init(target, &target_cursor);
    left = otrl_record_cursor_next(&oracle_cursor);
    right = otrl_record_cursor_next(&target_cursor);
    while (left != NULL || right != NULL) {
        while ((left != NULL && ignorable_diagnostic(left)) ||
               (right != NULL && ignorable_diagnostic(right))) {
            if (left == NULL || right == NULL ||
                !ignorable_diagnostic(left) || !ignorable_diagnostic(right) ||
                left->type != right->type ||
                left->payload_bytes != right->payload_bytes ||
                (left->payload_bytes != 0U &&
                 memcmp(left->payload, right->payload,
                        left->payload_bytes) != 0)) {
                diagnostics_differ = 1;
            }
            if (left != NULL && ignorable_diagnostic(left)) {
                left = otrl_record_cursor_next(&oracle_cursor);
            }
            if (right != NULL && ignorable_diagnostic(right)) {
                right = otrl_record_cursor_next(&target_cursor);
            }
        }
        i = left == NULL ? oracle->record_count : left->sequence;
        j = right == NULL ? target->record_count : right->sequence;
        if (left == NULL || right == NULL) {
            if (left != NULL || right != NULL) {
                result_base(&temporary, left != NULL ? left : right,
                            OTRL_DIVERGENCE_END_OF_STREAM);
                add_context(oracle, target, i, j, &temporary);
                temporary.diagnostics_differ_ignored =
                    (uint32_t)diagnostics_differ;
                *result = temporary;
                return OTRL_E_DIVERGENCE;
            }
            break;
        }
        if (left->type != right->type || left->version != right->version ||
            left->public_step != right->public_step ||
            left->native_tick != right->native_tick) {
            result_base(&temporary, left, OTRL_DIVERGENCE_RECORD);
            add_context(oracle, target, i, j, &temporary);
            temporary.diagnostics_differ_ignored = (uint32_t)diagnostics_differ;
            *result = temporary;
            return OTRL_E_DIVERGENCE;
        }
        if (left->type == OTRL_RECORD_AUTHORITATIVE_PROJECTION) {
            otrl_status status = compare_projection(left, right, &temporary);
            if (status != OTRL_OK) {
                add_context(oracle, target, i, j, &temporary);
                temporary.diagnostics_differ_ignored =
                    (uint32_t)diagnostics_differ;
                *result = temporary;
                return status;
            }
        } else if (left->type == OTRL_RECORD_COMMAND_INTENT ||
                   left->type == OTRL_RECORD_COMMAND_TEST_RESULT ||
                   left->type == OTRL_RECORD_COMMAND_EXEC_RESULT) {
            otrl_status status = compare_command(left, right, &temporary);
            if (status != OTRL_OK) {
                add_context(oracle, target, i, j, &temporary);
                temporary.diagnostics_differ_ignored =
                    (uint32_t)diagnostics_differ;
                *result = temporary;
                return status;
            }
        } else if (left->payload_bytes != right->payload_bytes ||
                   (left->payload_bytes != 0U &&
                    memcmp(left->payload, right->payload,
                           left->payload_bytes) != 0)) {
            result_base(&temporary, left, OTRL_DIVERGENCE_RECORD);
            add_context(oracle, target, i, j, &temporary);
            temporary.diagnostics_differ_ignored = (uint32_t)diagnostics_differ;
            *result = temporary;
            return OTRL_E_DIVERGENCE;
        }
        left = otrl_record_cursor_next(&oracle_cursor);
        right = otrl_record_cursor_next(&target_cursor);
    }
    temporary.diagnostics_differ_ignored = (uint32_t)diagnostics_differ;
    *result = temporary;
    return OTRL_OK;
}

static uint64_t closure_record(const otrl_tape *tape, uint64_t divergence)
{
    otrl_record_cursor cursor;
    const otrl_record_internal *record;
    uint16_t type = 0U;
    otrl_record_cursor_init(tape, &cursor);
    while ((record = otrl_record_cursor_next(&cursor)) != NULL) {
        if (record->sequence == divergence) {
            type = record->type;
            break;
        }
    }
    if (type == OTRL_RECORD_COMMAND_INTENT ||
        type == OTRL_RECORD_COMMAND_TEST_RESULT ||
        type == OTRL_RECORD_COMMAND_EXEC_RESULT) {
        while ((record = otrl_record_cursor_next(&cursor)) != NULL) {
            if (record->type == OTRL_RECORD_AUTHORITATIVE_PROJECTION) {
                return record->sequence;
            }
        }
    }
    return divergence;
}

static otrl_status write_minimized_stream(otrl_context *context,
                                          const otrl_tape *target,
                                          uint64_t required,
                                          char *temporary,
                                          otrl_error *error)
{
    otrl_record_cursor cursor;
    const otrl_record_internal *record;
    uint64_t retained_count = 0U;
    uint64_t record_bytes = OTRL_RECORD_HEADER_BYTES + 8U;
    uint64_t max_step = 0U;
    uint64_t max_tick = 0U;
    uint8_t prefix[OTRL_PREFIX_BYTES] = {0};
    uint8_t record_header[OTRL_RECORD_HEADER_BYTES] = {0};
    uint8_t terminal_payload[8] = {1U, 0U, 0U, 0U, 0U, 0U, 0U, 0U};
    uint8_t trailer[OTRL_TRAILER_BYTES] = {0};
    uint8_t zero_padding[8] = {0};
    EVP_MD_CTX *digest = NULL;
    unsigned int digest_bytes = 0U;
    int descriptor = -1;
    int result;
    otrl_status status = OTRL_E_IO;

    otrl_record_cursor_init(target, &cursor);
    while ((record = otrl_record_cursor_next(&cursor)) != NULL &&
           record->sequence <= required) {
        if (record->type == OTRL_RECORD_TERMINAL) break;
        if ((uint64_t)record->padded_bytes > UINT64_MAX - record_bytes) {
            return OTRL_E_OVERFLOW;
        }
        record_bytes += (uint64_t)record->padded_bytes;
        ++retained_count;
        max_step = record->public_step;
        max_tick = record->native_tick;
    }
    ++retained_count;
    if (record_bytes > UINT64_MAX - OTRL_PREFIX_BYTES - OTRL_TRAILER_BYTES ||
        (uint64_t)target->header_bytes >
            UINT64_MAX - OTRL_PREFIX_BYTES - OTRL_TRAILER_BYTES - record_bytes ||
        OTRL_PREFIX_BYTES + OTRL_TRAILER_BYTES + record_bytes +
            (uint64_t)target->header_bytes > context->local_max_tape_bytes) {
        return OTRL_E_LIMIT;
    }

    memcpy(prefix, "OTRLTAP\0", 8U);
    otrl_put_u16_le(prefix + 8U, OTRL_FORMAT_MAJOR);
    otrl_put_u16_le(prefix + 10U, OTRL_FORMAT_MINOR);
    prefix[12] = OTRL_BYTE_ORDER_LE;
    prefix[13] = OTRL_HASH_SHA256;
    otrl_put_u16_le(prefix + 14U, OTRL_PREFIX_BYTES);
    otrl_put_u32_le(prefix + 16U, target->header_bytes);
    otrl_put_u32_le(prefix + 20U, target->flags & ~OTRL_PREFIX_FLAG_PARTIAL);
    otrl_put_u64_le(prefix + 24U, retained_count);
    otrl_put_u64_le(prefix + 32U, record_bytes);
    otrl_put_u64_le(prefix + 40U, max_step);
    otrl_put_u64_le(prefix + 48U, max_tick);

    descriptor = mkstemp(temporary);
    if (descriptor < 0) goto cleanup;
    if (fcntl(descriptor, F_SETFD, FD_CLOEXEC) != 0 ||
        fchmod(descriptor, 0644) != 0) goto cleanup;
    digest = EVP_MD_CTX_new();
    if (digest == NULL || EVP_DigestInit_ex(digest, EVP_sha256(), NULL) != 1 ||
        !stream_write_covered(descriptor, digest, prefix, sizeof(prefix)) ||
        !stream_write_covered(descriptor, digest, target->header,
                              target->header_bytes)) goto cleanup;

    otrl_record_cursor_init(target, &cursor);
    while ((record = otrl_record_cursor_next(&cursor)) != NULL &&
           record->sequence <= required) {
        const size_t unpadded = OTRL_RECORD_HEADER_BYTES + record->payload_bytes;
        const size_t padding = record->padded_bytes - unpadded;
        if (record->type == OTRL_RECORD_TERMINAL) break;
        memset(record_header, 0, sizeof(record_header));
        otrl_put_u16_le(record_header, record->type);
        otrl_put_u16_le(record_header + 2U, record->version);
        otrl_put_u32_le(record_header + 4U, record->flags);
        otrl_put_u64_le(record_header + 8U, record->sequence);
        otrl_put_u64_le(record_header + 16U, record->public_step);
        otrl_put_u64_le(record_header + 24U, record->native_tick);
        otrl_put_u32_le(record_header + 32U, record->payload_bytes);
        if (!stream_write_covered(descriptor, digest, record_header,
                                  sizeof(record_header)) ||
            (record->payload_bytes != 0U &&
             !stream_write_covered(descriptor, digest, record->payload,
                                   record->payload_bytes)) ||
            (padding != 0U &&
             !stream_write_covered(descriptor, digest, zero_padding, padding))) {
            goto cleanup;
        }
    }
    memset(record_header, 0, sizeof(record_header));
    otrl_put_u16_le(record_header, OTRL_RECORD_TERMINAL);
    otrl_put_u16_le(record_header + 2U, 1U);
    otrl_put_u32_le(record_header + 4U, OTRL_RECORD_FLAG_REQUIRED);
    otrl_put_u64_le(record_header + 8U, retained_count - 1U);
    otrl_put_u64_le(record_header + 16U, max_step);
    otrl_put_u64_le(record_header + 24U, max_tick);
    otrl_put_u32_le(record_header + 32U, sizeof(terminal_payload));
    if (!stream_write_covered(descriptor, digest, record_header,
                              sizeof(record_header)) ||
        !stream_write_covered(descriptor, digest, terminal_payload,
                              sizeof(terminal_payload))) goto cleanup;
    memcpy(trailer, "OTRLEND\0", 8U);
    otrl_put_u64_le(trailer + 8U, retained_count);
    otrl_put_u64_le(trailer + 16U, OTRL_PREFIX_BYTES + target->header_bytes +
                                     record_bytes);
    if (EVP_DigestFinal_ex(digest, trailer + 24U, &digest_bytes) != 1 ||
        digest_bytes != 32U ||
        !stream_write_all(descriptor, trailer, sizeof(trailer))) goto cleanup;
    do { result = fsync(descriptor); } while (result != 0 && errno == EINTR);
    if (result != 0 || close(descriptor) != 0) {
        descriptor = -1;
        goto cleanup;
    }
    descriptor = -1;
    status = OTRL_OK;

cleanup:
    if (descriptor >= 0) (void)close(descriptor);
    EVP_MD_CTX_free(digest);
    if (status != OTRL_OK) {
        (void)unlink(temporary);
        otrl_set_error(error, status, 0U, UINT64_MAX, 0U, 0U, 0U,
                       "streaming minimized-prefix write failed");
    }
    return status;
}

otrl_status otrl_minimize_prefix(otrl_context *context,
                                 const otrl_tape *oracle,
                                 const otrl_tape *target,
                                 const char *output_path,
                                 otrl_compare_result *result,
                                 otrl_error *error)
{
    otrl_compare_result original;
    char temporary[4096];
    otrl_tape *minimized = NULL;
    otrl_compare_result verified;
    otrl_status status;
    uint64_t required;
    uint64_t low;
    uint64_t high;
    int written;
    if (context == NULL || oracle == NULL || target == NULL ||
        output_path == NULL || result == NULL ||
        !otrl_valid_public_struct(result, result->size,
                                  (uint32_t)sizeof(*result), result->version)) {
        return OTRL_E_USAGE;
    }
    memset(&original, 0, sizeof(original));
    original.size = (uint32_t)sizeof(original);
    original.version = OTRL_ABI_VERSION;
    status = otrl_compare(oracle, target, &original, error);
    if (status != OTRL_E_DIVERGENCE) {
        return status == OTRL_OK ? OTRL_E_USAGE : status;
    }
    required = closure_record(target, original.target_record_sequence);
    /* The closed-prefix predicate is monotone for a first-divergence tape.
       Search it with the same verified helper whose nonmonotone path falls
       back to a linear scan. */
    low = 0U;
    high = target->record_count;
    while (low < high) {
        const uint64_t middle = low + (high - low) / 2U;
        if (middle > required) {
            high = middle;
        } else {
            low = middle + 1U;
        }
    }
    required = low - 1U;
    written = snprintf(temporary, sizeof(temporary), "%s.partial.XXXXXX",
                       output_path);
    if (written < 0 || (size_t)written >= sizeof(temporary)) return OTRL_E_USAGE;
    status = write_minimized_stream(context, target, required, temporary, error);
    if (status != OTRL_OK) goto cleanup;
    status = otrl_validate_file(context, temporary, &minimized, error);
    if (status != OTRL_OK) goto cleanup;
    memset(&verified, 0, sizeof(verified));
    verified.size = (uint32_t)sizeof(verified);
    verified.version = OTRL_ABI_VERSION;
    status = otrl_compare(oracle, minimized, &verified, error);
    if (status != OTRL_E_DIVERGENCE || verified.kind != original.kind ||
        verified.field_id != original.field_id ||
        verified.record_type != original.record_type ||
        verified.public_step != original.public_step ||
        verified.native_tick != original.native_tick ||
        verified.boundary_kind != original.boundary_kind ||
        verified.boundary_ordinal != original.boundary_ordinal ||
        verified.element_index != original.element_index ||
        verified.oracle_value_bytes != original.oracle_value_bytes ||
        verified.target_value_bytes != original.target_value_bytes ||
        memcmp(verified.oracle_value, original.oracle_value,
               original.oracle_value_bytes) != 0 ||
        memcmp(verified.target_value, original.target_value,
               original.target_value_bytes) != 0) {
        status = OTRL_E_INVARIANT;
        goto cleanup;
    }
    status = promote_stream_file(temporary, output_path, error);
    if (status == OTRL_OK) {
        *result = verified;
    }

cleanup:
    otrl_tape_destroy(context, minimized);
    (void)unlink(temporary);
    return status;
}
