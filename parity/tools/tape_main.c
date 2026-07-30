/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"
#include "openttd_rl_parity/field_schema.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int cli_exit(otrl_status status)
{
    switch (status) {
    case OTRL_OK: return 0;
    case OTRL_E_DIVERGENCE: return 1;
    case OTRL_E_IDENTITY: return 2;
    case OTRL_E_TRUNCATED:
    case OTRL_E_MAGIC:
    case OTRL_E_VERSION:
    case OTRL_E_ENDIAN:
    case OTRL_E_HASH_ALGORITHM:
    case OTRL_E_CHECKSUM:
    case OTRL_E_CANONICAL:
    case OTRL_E_RESERVED:
    case OTRL_E_OVERFLOW:
    case OTRL_E_SEQUENCE:
    case OTRL_E_STRUCTURE:
    case OTRL_E_SCHEMA: return 3;
    case OTRL_E_IO:
    case OTRL_E_LIMIT: return 4;
    case OTRL_E_INVARIANT:
    case OTRL_E_INTERNAL: return 5;
    case OTRL_E_USAGE: return 64;
    default: return 5;
    }
}

static void usage(FILE *stream)
{
    (void)fprintf(stream,
        "usage: tape COMMAND ...\n"
        "  tape inspect FILE\n"
        "  tape validate FILE\n"
        "  tape compare ORACLE TARGET\n"
        "  tape minimize ORACLE TARGET OUTPUT_PREFIX\n"
        "  tape dump FILE --from-tick N --to-tick M --fields ID|all\n"
        "  tape hash FILE\n"
        "  tape finalize PARTIAL OUTPUT\n"
        "  tape schema-check FILE\n"
        "  tape fault-inject INPUT OUTPUT field:ID:MASK\n"
        "  tape fault-inject INPUT OUTPUT identity:KEY:HEX\n");
}

static void print_error(otrl_status status, const otrl_error *error)
{
    (void)fprintf(stderr,
                  "tape: %s: offset=%llu sequence=%llu field=%u: %s\n",
                  otrl_status_string(status),
                  (unsigned long long)error->byte_offset,
                  (unsigned long long)error->record_sequence,
                  error->field_id,
                  error->message[0] == '\0' ? otrl_status_string(status) :
                                              error->message);
}

static otrl_status open_tape(otrl_context *context, const char *path,
                             otrl_tape **tape, otrl_error *error)
{
    return otrl_validate_file(context, path, tape, error);
}

static void print_hex(const uint8_t *bytes, size_t length)
{
    for (size_t i = 0U; i < length; ++i) {
        (void)printf("%02x", bytes[i]);
    }
}

static void print_json_string(const char *text)
{
    (void)putchar('"');
    for (const unsigned char *cursor = (const unsigned char *)text;
         *cursor != 0U; ++cursor) {
        if (*cursor == '"' || *cursor == '\\') {
            (void)putchar('\\');
            (void)putchar((int)*cursor);
        } else if (*cursor < 0x20U) {
            (void)printf("\\u%04x", (unsigned int)*cursor);
        } else {
            (void)putchar((int)*cursor);
        }
    }
    (void)putchar('"');
}

static uint64_t little_value(const uint8_t *bytes, uint32_t length)
{
    uint64_t value = 0U;
    const uint32_t bounded = length > 8U ? 8U : length;
    for (uint32_t i = 0U; i < bounded; ++i) {
        value |= (uint64_t)bytes[i] << (i * 8U);
    }
    return value;
}

static void print_decimal_value(uint64_t value, uint32_t width_bits,
                                uint32_t is_signed)
{
    if (is_signed != 0U && width_bits != 0U && width_bits <= 64U &&
        (value & (UINT64_C(1) << (width_bits - 1U))) != 0U) {
        const uint64_t mask = width_bits == 64U ? UINT64_MAX :
                              (UINT64_C(1) << width_bits) - UINT64_C(1);
        const uint64_t magnitude = ((~value) & mask) + UINT64_C(1);
        (void)printf("-%llu", (unsigned long long)magnitude);
    } else {
        (void)printf("%llu", (unsigned long long)value);
    }
}

static void print_numeric_hex(const uint8_t *bytes, size_t length)
{
    (void)printf("0x");
    for (size_t i = length; i > 0U; --i) {
        (void)printf("%02x", bytes[i - 1U]);
    }
}

static int identity_span(const otrl_tape *tape, const uint8_t **start,
                         size_t *span)
{
    static const char marker[] = "\"identity\":";
    for (size_t i = 0U; i + sizeof(marker) - 1U < tape->header_bytes; ++i) {
        if (memcmp(tape->header + i, marker, sizeof(marker) - 1U) == 0) {
            size_t cursor = i + sizeof(marker) - 1U;
            size_t depth = 0U;
            int in_string = 0;
            int escaped = 0;
            if (tape->header[cursor] != '{') return 0;
            *start = tape->header + cursor;
            for (; cursor < tape->header_bytes; ++cursor) {
                const uint8_t byte = tape->header[cursor];
                if (in_string != 0) {
                    if (escaped != 0) escaped = 0;
                    else if (byte == '\\') escaped = 1;
                    else if (byte == '"') in_string = 0;
                } else if (byte == '"') {
                    in_string = 1;
                } else if (byte == '{') {
                    ++depth;
                } else if (byte == '}' && --depth == 0U) {
                    *span = cursor + 1U - (size_t)(*start - tape->header);
                    return 1;
                }
            }
        }
    }
    return 0;
}

static int record_at_sequence(const otrl_tape *tape, uint64_t sequence,
                              otrl_record_internal *result)
{
    otrl_record_cursor cursor;
    const otrl_record_internal *record;
    if (sequence == UINT64_MAX || sequence >= tape->record_count) return 0;
    otrl_record_cursor_init(tape, &cursor);
    while ((record = otrl_record_cursor_next(&cursor)) != NULL) {
        if (record->sequence == sequence) {
            *result = *record;
            return 1;
        }
    }
    return 0;
}

static void print_command_record(const otrl_record_internal *record)
{
    if (record == NULL) {
        (void)printf("null");
        return;
    }
    if (record->type == OTRL_RECORD_COMMAND_INTENT) {
        (void)printf("{\"command_flags\":%u,\"company\":%u,"
                     "\"native_command\":%u,\"operand_hex\":\"",
                     otrl_get_u32_le(record->payload + 12U),
                     otrl_get_u32_le(record->payload + 8U),
                     otrl_get_u32_le(record->payload + 4U));
        print_hex(record->payload + 24U, record->payload_bytes - 24U);
        (void)printf("\",\"sequence\":%llu}",
                     (unsigned long long)record->sequence);
    } else {
        const uint64_t cost = otrl_get_u64_le(record->payload + 8U);
        (void)printf("{\"cost\":");
        print_decimal_value(cost, 64U, 1U);
        (void)printf(",\"error\":%u,\"expense_type\":%u,"
                     "\"extra_error\":%u,\"native_command\":%u,"
                     "\"result_hex\":\"",
                     otrl_get_u32_le(record->payload + 20U),
                     otrl_get_u32_le(record->payload + 16U),
                     otrl_get_u32_le(record->payload + 24U),
                     otrl_get_u32_le(record->payload + 4U));
        print_hex(record->payload + 32U, record->payload_bytes - 32U);
        (void)printf("\",\"sequence\":%llu,\"success\":%s}",
                     (unsigned long long)record->sequence,
                     record->payload[2] != 0U ? "true" : "false");
    }
}

static const char *checkpoint_name(uint16_t checkpoint_id)
{
    static const char *const names[] = {
        "invalid", "route_completion", "first_production",
        "first_station_capture", "first_loading", "first_unloading",
        "first_accepted_delivery", "first_payment", "continuation_end"
    };
    return checkpoint_id <= 8U ? names[checkpoint_id] : "invalid";
}

static int same_divergence(const otrl_compare_result *left,
                           const otrl_compare_result *right)
{
    return left->kind == right->kind &&
           left->field_id == right->field_id &&
           left->record_type == right->record_type &&
           left->public_step == right->public_step &&
           left->native_tick == right->native_tick &&
           left->boundary_kind == right->boundary_kind &&
           left->boundary_ordinal == right->boundary_ordinal &&
           left->element_index == right->element_index &&
           left->oracle_value_bytes == right->oracle_value_bytes &&
           left->target_value_bytes == right->target_value_bytes &&
           memcmp(left->oracle_value, right->oracle_value,
                  left->oracle_value_bytes) == 0 &&
           memcmp(left->target_value, right->target_value,
                  left->target_value_bytes) == 0;
}

static otrl_status command_validate(otrl_context *context, const char *path,
                                    int inspect, int hash, otrl_error *error)
{
    otrl_tape *tape = NULL;
    otrl_status status = open_tape(context, path, &tape, error);
    if (status != OTRL_OK) return status;
    if (hash) {
        print_hex(tape->digest, 32U);
        (void)putchar('\n');
    } else if (inspect) {
        (void)printf("format=1.0 records=%llu record_bytes=%llu max_step=%llu "
                     "max_tick=%llu flags=%u sha256=",
                     (unsigned long long)tape->record_count,
                     (unsigned long long)tape->record_bytes,
                     (unsigned long long)tape->max_step,
                     (unsigned long long)tape->max_tick, tape->flags);
        print_hex(tape->digest, 32U);
        (void)printf("\nheader=");
        (void)fwrite(tape->header, 1U, tape->header_bytes, stdout);
        (void)putchar('\n');
    } else {
        (void)printf("PASS %s\n", path);
    }
    otrl_tape_destroy(context, tape);
    return OTRL_OK;
}

static otrl_status command_compare(otrl_context *context,
                                   const char *executable_path,
                                   const char *left_path,
                                   const char *right_path, otrl_error *error)
{
    otrl_tape *left = NULL;
    otrl_tape *right = NULL;
    otrl_tape *minimal = NULL;
    otrl_compare_result result;
    otrl_compare_result minimized_result;
    char executable_absolute[4096];
    char left_absolute[4096];
    char right_absolute[4096];
    char minimal_path[4096];
    const uint8_t *left_identity;
    const uint8_t *right_identity;
    size_t left_identity_bytes;
    size_t right_identity_bytes;
    otrl_status status = open_tape(context, left_path, &left, error);
    if (status != OTRL_OK) goto done;
    status = open_tape(context, right_path, &right, error);
    if (status != OTRL_OK) goto done;
    memset(&result, 0, sizeof(result));
    result.size = (uint32_t)sizeof(result);
    result.version = OTRL_ABI_VERSION;
    status = otrl_compare(left, right, &result, error);
    if (status == OTRL_OK) {
        (void)printf("{\"equal\":true,\"status\":\"OK\"}\n");
        (void)fprintf(stderr, "tapes are authoritative-equal%s\n",
                      result.diagnostics_differ_ignored != 0U ?
                      "; optional diagnostics differ" : "");
    } else if (status == OTRL_E_DIVERGENCE) {
        const uint64_t left_value = little_value(result.oracle_value,
                                                  result.oracle_value_bytes);
        const uint64_t right_value = little_value(result.target_value,
                                                   result.target_value_bytes);
        otrl_record_internal last_intent_value;
        otrl_record_internal last_test_value;
        otrl_record_internal last_exec_value;
        otrl_record_internal checkpoint_value;
        const otrl_record_internal *last_intent = NULL;
        const otrl_record_internal *last_test = NULL;
        const otrl_record_internal *last_exec = NULL;
        const otrl_record_internal *checkpoint = NULL;
        int written;
        if (realpath(executable_path, executable_absolute) == NULL ||
            realpath(left_path, left_absolute) == NULL ||
            realpath(right_path, right_absolute) == NULL ||
            !identity_span(left, &left_identity, &left_identity_bytes) ||
            !identity_span(right, &right_identity, &right_identity_bytes)) {
            status = OTRL_E_IO;
            goto done;
        }
        written = snprintf(minimal_path, sizeof(minimal_path), "%s.minimal.tape",
                           right_absolute);
        if (written < 0 || (size_t)written >= sizeof(minimal_path)) {
            status = OTRL_E_IO;
            goto done;
        }
        memset(&minimized_result, 0, sizeof(minimized_result));
        minimized_result.size = (uint32_t)sizeof(minimized_result);
        minimized_result.version = OTRL_ABI_VERSION;
        if (access(minimal_path, F_OK) == 0) {
            status = open_tape(context, minimal_path, &minimal, error);
            if (status != OTRL_OK) goto done;
            status = otrl_compare(left, minimal, &minimized_result, error);
            if (status != OTRL_E_DIVERGENCE ||
                !same_divergence(&result, &minimized_result)) {
                status = OTRL_E_IO;
                goto done;
            }
        } else if (errno == ENOENT) {
            status = otrl_minimize_prefix(context, left, right, minimal_path,
                                          &minimized_result, error);
            if (status != OTRL_OK) goto done;
            status = open_tape(context, minimal_path, &minimal, error);
            if (status != OTRL_OK) goto done;
        } else {
            status = OTRL_E_IO;
            goto done;
        }
        if (record_at_sequence(left, result.last_command_intent_sequence,
                               &last_intent_value)) last_intent = &last_intent_value;
        if (record_at_sequence(left, result.last_command_test_sequence,
                               &last_test_value)) last_test = &last_test_value;
        if (record_at_sequence(left, result.last_command_exec_sequence,
                               &last_exec_value)) last_exec = &last_exec_value;
        if (record_at_sequence(left, result.previous_checkpoint_sequence,
                               &checkpoint_value)) checkpoint = &checkpoint_value;

        (void)printf("{\"backend_labels\":{\"oracle\":");
        print_json_string(result.oracle_backend);
        (void)printf(",\"target\":");
        print_json_string(result.target_backend);
        (void)printf("},\"boundary\":{\"kind\":%u,\"ordinal\":%llu},"
                     "\"cache_class\":", result.boundary_kind,
                     (unsigned long long)result.boundary_ordinal);
        print_json_string(result.cache_class);
        (void)printf(",\"diagnostics_differ_ignored\":%s,"
                     "\"element_index\":%u,\"equal\":false,"
                     "\"field\":{\"id\":%u,\"path\":",
                     result.diagnostics_differ_ignored != 0U ? "true" : "false",
                     result.element_index, result.field_id);
        print_json_string(result.field_path);
        (void)printf(",\"signed\":%s,\"type\":%u,\"width_bits\":%u},"
                     "\"field_id\":%u,\"field_path\":",
                     result.value_signed != 0U ? "true" : "false",
                     result.value_type, result.value_width_bits,
                     result.field_id);
        print_json_string(result.field_path);
        (void)printf(",\"identities\":{\"oracle\":");
        (void)fwrite(left_identity, 1U, left_identity_bytes, stdout);
        (void)printf(",\"target\":");
        (void)fwrite(right_identity, 1U, right_identity_bytes, stdout);
        (void)printf("},\"kind\":%u,\"last_command\":{\"execute\":",
                     result.kind);
        print_command_record(last_exec);
        (void)printf(",\"intent\":");
        print_command_record(last_intent);
        (void)printf(",\"test\":");
        print_command_record(last_test);
        (void)printf("},\"logical_environment_id\":%u,"
                     "\"minimal_prefix\":{\"digest\":\"",
                     result.logical_environment_id);
        print_hex(minimal->digest, 32U);
        (void)printf("\",\"path\":");
        print_json_string(minimal_path);
        (void)printf("},\"native_tick\":%llu,\"oracle_digest\":\"",
                     (unsigned long long)result.native_tick);
        print_hex(result.oracle_tape_sha256, 32U);
        (void)printf("\",\"oracle_value\":{\"decimal\":");
        if (result.value_width_bits == 0U || result.oracle_value_bytes == 0U) {
            (void)printf("null,\"hex\":null},\"oracle_value_decimal\":null,"
                         "\"oracle_value_hex\":null");
        } else {
            (void)putchar('"');
            print_decimal_value(left_value, result.value_width_bits,
                                result.value_signed);
            (void)printf("\",\"hex\":\"");
            print_numeric_hex(result.oracle_value, result.oracle_value_bytes);
            (void)printf("\"},\"oracle_value_decimal\":\"");
            print_decimal_value(left_value, result.value_width_bits,
                                result.value_signed);
            (void)printf("\",\"oracle_value_hex\":\"");
            print_numeric_hex(result.oracle_value, result.oracle_value_bytes);
            (void)putchar('"');
        }
        (void)printf(",\"previous_checkpoint\":");
        if (checkpoint == NULL) {
            (void)printf("null");
        } else {
            const uint16_t checkpoint_id = otrl_get_u16_le(checkpoint->payload + 2U);
            (void)printf("{\"id\":%u,\"name\":", checkpoint_id);
            print_json_string(checkpoint_name(checkpoint_id));
            (void)printf(",\"sequence\":%llu}",
                         (unsigned long long)checkpoint->sequence);
        }
        (void)printf(",\"public_step\":%llu,\"record_sequence\":%llu,"
                     "\"record_type\":%u,\"reproduce\":{\"compare\":[",
                     (unsigned long long)result.public_step,
                     (unsigned long long)result.record_sequence,
                     result.record_type);
        print_json_string(executable_absolute);
        (void)printf(",\"compare\",");
        print_json_string(left_absolute);
        (void)putchar(',');
        print_json_string(right_absolute);
        (void)printf("],\"minimize\":[");
        print_json_string(executable_absolute);
        (void)printf(",\"minimize\",");
        print_json_string(left_absolute);
        (void)putchar(',');
        print_json_string(right_absolute);
        (void)putchar(',');
        print_json_string(minimal_path);
        (void)printf("]},\"source_anchor\":");
        print_json_string(result.source_anchor);
        (void)printf(",\"status\":\"divergence\",\"target_digest\":\"");
        print_hex(result.target_tape_sha256, 32U);
        (void)printf("\",\"target_record_sequence\":%llu,"
                     "\"target_value\":{\"decimal\":",
                     (unsigned long long)result.target_record_sequence);
        if (result.value_width_bits == 0U || result.target_value_bytes == 0U) {
            (void)printf("null,\"hex\":null},\"target_value_decimal\":null,"
                         "\"target_value_hex\":null,\"value_signed\":%s,"
                         "\"value_type\":%u,\"value_width_bits\":%u}\n",
                         result.value_signed != 0U ? "true" : "false",
                         result.value_type, result.value_width_bits);
        } else {
            (void)putchar('"');
            print_decimal_value(right_value, result.value_width_bits,
                                result.value_signed);
            (void)printf("\",\"hex\":\"");
            print_numeric_hex(result.target_value, result.target_value_bytes);
            (void)printf("\"},\"target_value_decimal\":\"");
            print_decimal_value(right_value, result.value_width_bits,
                                result.value_signed);
            (void)printf("\",\"target_value_hex\":\"");
            print_numeric_hex(result.target_value, result.target_value_bytes);
            (void)printf("\",\"value_signed\":%s,\"value_type\":%u,"
                         "\"value_width_bits\":%u}\n",
                         result.value_signed != 0U ? "true" : "false",
                         result.value_type, result.value_width_bits);
        }
        (void)fprintf(stderr,
                      "first divergence: sequence=%llu type=%u field=%u\n",
                      (unsigned long long)result.record_sequence,
                      result.record_type, result.field_id);
        status = OTRL_E_DIVERGENCE;
    }
done:
    otrl_tape_destroy(context, minimal);
    otrl_tape_destroy(context, right);
    otrl_tape_destroy(context, left);
    return status;
}

static otrl_status command_minimize(otrl_context *context,
                                    const char *left_path,
                                    const char *right_path,
                                    const char *output_path,
                                    otrl_error *error)
{
    otrl_tape *left = NULL;
    otrl_tape *right = NULL;
    otrl_compare_result result;
    otrl_status status = open_tape(context, left_path, &left, error);
    if (status != OTRL_OK) goto done;
    status = open_tape(context, right_path, &right, error);
    if (status != OTRL_OK) goto done;
    memset(&result, 0, sizeof(result));
    result.size = (uint32_t)sizeof(result);
    result.version = OTRL_ABI_VERSION;
    status = otrl_minimize_prefix(context, left, right, output_path, &result,
                                  error);
    if (status == OTRL_OK) {
        (void)printf("{\"field_id\":%u,\"output\":\"%s\","
                     "\"record_sequence\":%llu,\"status\":\"PASS\"}\n",
                     result.field_id, output_path,
                     (unsigned long long)result.record_sequence);
    }
done:
    otrl_tape_destroy(context, right);
    otrl_tape_destroy(context, left);
    return status;
}

static otrl_status command_dump(otrl_context *context, const char *path,
                                uint64_t from, uint64_t to, uint32_t filter,
                                otrl_error *error)
{
    otrl_tape *tape = NULL;
    otrl_record_cursor cursor;
    const otrl_record_internal *record;
    otrl_status status = open_tape(context, path, &tape, error);
    if (status != OTRL_OK) return status;
    otrl_record_cursor_init(tape, &cursor);
    while ((record = otrl_record_cursor_next(&cursor)) != NULL) {
        if (record->native_tick < from || record->native_tick > to) continue;
        (void)printf("sequence=%llu type=%u step=%llu tick=%llu bytes=%u\n",
                     (unsigned long long)record->sequence, record->type,
                     (unsigned long long)record->public_step,
                     (unsigned long long)record->native_tick,
                     record->payload_bytes);
        if (record->type == OTRL_RECORD_AUTHORITATIVE_PROJECTION) {
            size_t offset = 24U;
            const uint32_t count = otrl_get_u32_le(record->payload + 4U);
            for (uint32_t field = 0U; field < count; ++field) {
                const uint32_t id = otrl_get_u32_le(record->payload + offset);
                const uint16_t type = otrl_get_u16_le(record->payload + offset + 4U);
                const uint32_t bytes = otrl_get_u32_le(record->payload + offset + 12U);
                size_t end = offset + 16U + bytes;
                (void)otrl_checked_align8_size(end, &end);
                if (filter == 0U || filter == id) {
                    (void)printf("  field=%u type=%u value=0x", id, type);
                    print_hex(record->payload + offset + 16U, bytes);
                    (void)putchar('\n');
                }
                offset = end;
            }
        }
    }
    otrl_tape_destroy(context, tape);
    return OTRL_OK;
}

static otrl_status read_file(otrl_context *context, const char *path,
                             uint8_t **out, size_t *out_length)
{
    struct stat information;
    FILE *file;
    uint8_t *bytes;
    if (stat(path, &information) != 0 || information.st_size < 0 ||
        (uint64_t)information.st_size > OTRL_MAX_TAPE_BYTES ||
        (uint64_t)information.st_size > SIZE_MAX) return OTRL_E_IO;
    *out_length = (size_t)information.st_size;
    bytes = otrl_alloc(context, *out_length == 0U ? 1U : *out_length);
    if (bytes == NULL) return OTRL_E_IO;
    file = fopen(path, "rb");
    if (file == NULL || (*out_length != 0U &&
        fread(bytes, 1U, *out_length, file) != *out_length) ||
        fclose(file) != 0) {
        if (file != NULL) (void)fclose(file);
        otrl_dealloc(context, bytes);
        return OTRL_E_IO;
    }
    *out = bytes;
    return OTRL_OK;
}

static otrl_status command_fault(otrl_context *context, const char *input,
                                 const char *output, const char *spec,
                                 otrl_error *error)
{
    otrl_tape *tape = NULL;
    uint8_t *bytes = NULL;
    size_t length = 0U;
    otrl_status status = open_tape(context, input, &tape, error);
    if (status != OTRL_OK) return status;
    status = read_file(context, input, &bytes, &length);
    if (status != OTRL_OK) goto done;
    if (strncmp(spec, "field:", 6U) == 0) {
        char *end = NULL;
        const unsigned long field_id = strtoul(spec + 6U, &end, 10);
        unsigned long mask;
        int found = 0;
        otrl_record_cursor cursor;
        const otrl_record_internal *record;
        if (end == spec + 6U || end == NULL || *end != ':') {
            status = OTRL_E_USAGE;
            goto done;
        }
        mask = strtoul(end + 1U, &end, 0);
        if (end == NULL || *end != '\0' || field_id == 0U ||
            field_id > UINT32_MAX || mask == 0U || mask > UINT8_MAX) {
            status = OTRL_E_USAGE;
            goto done;
        }
        otrl_record_cursor_init(tape, &cursor);
        while (!found && (record = otrl_record_cursor_next(&cursor)) != NULL) {
            if (record->type != OTRL_RECORD_AUTHORITATIVE_PROJECTION) continue;
            size_t offset = 24U;
            const uint32_t count = otrl_get_u32_le(record->payload + 4U);
            for (uint32_t index = 0U; index < count; ++index) {
                const uint32_t id = otrl_get_u32_le(record->payload + offset);
                const uint32_t count_bytes =
                    otrl_get_u32_le(record->payload + offset + 12U);
                size_t end_offset = offset + 16U + count_bytes;
                (void)otrl_checked_align8_size(end_offset, &end_offset);
                if (id == (uint32_t)field_id && count_bytes != 0U) {
                    bytes[record->record_offset + 40U + offset + 16U] ^=
                        (uint8_t)mask;
                    found = 1;
                    break;
                }
                offset = end_offset;
            }
        }
        if (!found) { status = OTRL_E_USAGE; goto done; }
    } else if (strncmp(spec, "identity:", 9U) == 0) {
        const char *separator = strrchr(spec + 9U, ':');
        char marker[160];
        int marker_length;
        int found = 0;
        if (separator == NULL || separator[1] == '\0' || separator[2] != '\0') {
            status = OTRL_E_USAGE;
            goto done;
        }
        marker_length = snprintf(marker, sizeof(marker), "\"%.*s\":\"",
                                 (int)(separator - (spec + 9U)), spec + 9U);
        if (marker_length <= 0 || (size_t)marker_length >= sizeof(marker)) {
            status = OTRL_E_USAGE;
            goto done;
        }
        for (size_t i = 64U; i + (size_t)marker_length <
             64U + tape->header_bytes; ++i) {
            if (memcmp(bytes + i, marker, (size_t)marker_length) == 0) {
                bytes[i + (size_t)marker_length] = (uint8_t)separator[1];
                found = 1;
                break;
            }
        }
        if (!found) { status = OTRL_E_USAGE; goto done; }
    } else {
        status = OTRL_E_USAGE;
        goto done;
    }
    status = otrl_sha256(bytes, length - 64U, bytes + length - 40U);
    if (status == OTRL_OK) status = otrl_write_atomic(output, bytes, length, error);
done:
    otrl_dealloc(context, bytes);
    otrl_tape_destroy(context, tape);
    return status;
}

static otrl_status command_finalize(otrl_context *context, const char *input,
                                    const char *output, otrl_error *error)
{
    uint8_t *bytes = NULL;
    size_t length = 0U;
    otrl_writer *writer = NULL;
    otrl_writer_options options;
    size_t offset;
    uint64_t sequence = 0U;
    otrl_status status = read_file(context, input, &bytes, &length);
    if (status != OTRL_OK) return status;
    if (length < 64U || memcmp(bytes, "OTRLTAP\0", 8U) != 0 ||
        otrl_get_u16_le(bytes + 8U) != OTRL_FORMAT_MAJOR ||
        otrl_get_u16_le(bytes + 10U) != OTRL_FORMAT_MINOR ||
        bytes[12] != OTRL_BYTE_ORDER_LE || bytes[13] != OTRL_HASH_SHA256 ||
        otrl_get_u16_le(bytes + 14U) != OTRL_PREFIX_BYTES ||
        (otrl_get_u32_le(bytes + 20U) & OTRL_PREFIX_FLAG_PARTIAL) == 0U ||
        (otrl_get_u32_le(bytes + 20U) & ~OTRL_PREFIX_KNOWN_FLAGS) != 0U ||
        otrl_get_u64_le(bytes + 56U) != 0U ||
        otrl_get_u32_le(bytes + 16U) == 0U ||
        otrl_get_u32_le(bytes + 16U) > OTRL_MAX_HEADER_BYTES ||
        64U + (size_t)otrl_get_u32_le(bytes + 16U) > length) {
        status = OTRL_E_STRUCTURE;
        goto done;
    }
    memset(&options, 0, sizeof(options));
    options.size = (uint32_t)sizeof(options);
    options.version = OTRL_ABI_VERSION;
    options.flags = otrl_get_u32_le(bytes + 20U) & ~OTRL_PREFIX_FLAG_PARTIAL;
    options.header_json = bytes + 64U;
    options.header_bytes = otrl_get_u32_le(bytes + 16U);
    status = otrl_writer_create(context, &options, &writer, error);
    if (status != OTRL_OK) goto done;
    offset = 64U + options.header_bytes;
    while (offset < length) {
        otrl_record_view record;
        size_t framed;
        if (length - offset < 40U) { status = OTRL_E_TRUNCATED; goto done; }
        memset(&record, 0, sizeof(record));
        record.size = (uint32_t)sizeof(record);
        record.version = OTRL_ABI_VERSION;
        record.type = otrl_get_u16_le(bytes + offset);
        record.record_version = otrl_get_u16_le(bytes + offset + 2U);
        record.flags = otrl_get_u32_le(bytes + offset + 4U);
        if (otrl_get_u64_le(bytes + offset + 8U) != sequence ||
            otrl_get_u32_le(bytes + offset + 36U) != 0U) {
            status = OTRL_E_SEQUENCE; goto done;
        }
        record.sequence = sequence;
        record.public_step = otrl_get_u64_le(bytes + offset + 16U);
        record.native_tick = otrl_get_u64_le(bytes + offset + 24U);
        record.payload_bytes = otrl_get_u32_le(bytes + offset + 32U);
        if (!otrl_checked_add_size(40U, record.payload_bytes, &framed) ||
            !otrl_checked_align8_size(framed, &framed) ||
            framed > length - offset) { status = OTRL_E_TRUNCATED; goto done; }
        for (size_t pad = 40U + record.payload_bytes; pad < framed; ++pad) {
            if (bytes[offset + pad] != 0U) { status = OTRL_E_CANONICAL; goto done; }
        }
        record.payload = bytes + offset + 40U;
        status = otrl_writer_add_record(writer, &record, error);
        if (status != OTRL_OK) goto done;
        ++sequence;
        offset += framed;
    }
    status = otrl_writer_finalize_file(writer, output, error);
done:
    otrl_writer_destroy(writer);
    otrl_dealloc(context, bytes);
    return status;
}

int main(int argc, char **argv)
{
    otrl_context_options options;
    otrl_context *context = NULL;
    otrl_error error;
    otrl_status status;
    memset(&options, 0, sizeof(options));
    options.size = (uint32_t)sizeof(options);
    options.version = OTRL_ABI_VERSION;
    otrl_error_init(&error);
    status = otrl_context_create(&options, &context, &error);
    if (status != OTRL_OK) return cli_exit(status);
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        usage(stdout);
        otrl_context_destroy(context);
        return 0;
    }
    if (argc < 2) {
        usage(stderr);
        otrl_context_destroy(context);
        return 64;
    }
    if ((strcmp(argv[1], "validate") == 0 ||
         strcmp(argv[1], "schema-check") == 0) && argc == 3) {
        status = command_validate(context, argv[2], 0, 0, &error);
    } else if (strcmp(argv[1], "inspect") == 0 && argc == 3) {
        status = command_validate(context, argv[2], 1, 0, &error);
    } else if (strcmp(argv[1], "hash") == 0 && argc == 3) {
        status = command_validate(context, argv[2], 0, 1, &error);
    } else if (strcmp(argv[1], "compare") == 0 && argc == 4) {
        status = command_compare(context, argv[0], argv[2], argv[3], &error);
    } else if (strcmp(argv[1], "minimize") == 0 && argc == 5) {
        status = command_minimize(context, argv[2], argv[3], argv[4], &error);
    } else if (strcmp(argv[1], "fault-inject") == 0 && argc == 5) {
        status = command_fault(context, argv[2], argv[3], argv[4], &error);
    } else if (strcmp(argv[1], "finalize") == 0 && argc == 4) {
        status = command_finalize(context, argv[2], argv[3], &error);
    } else if (strcmp(argv[1], "dump") == 0 && argc == 9 &&
               strcmp(argv[3], "--from-tick") == 0 &&
               strcmp(argv[5], "--to-tick") == 0 &&
               strcmp(argv[7], "--fields") == 0) {
        char *end_from = NULL;
        char *end_to = NULL;
        char *end_filter = NULL;
        const unsigned long long from = strtoull(argv[4], &end_from, 10);
        const unsigned long long to = strtoull(argv[6], &end_to, 10);
        unsigned long filter = 0U;
        const int all_fields = strcmp(argv[8], "all") == 0;
        int invalid_filter = 0;
        if (!all_fields) {
            filter = strtoul(argv[8], &end_filter, 10);
            invalid_filter = end_filter == NULL || end_filter == argv[8] ||
                             *end_filter != '\0' || filter == 0U ||
                             filter > UINT32_MAX ||
                             otrl_field_lookup((uint32_t)filter) == NULL;
        }
        if (end_from == NULL || end_from == argv[4] || *end_from != '\0' ||
            end_to == NULL || end_to == argv[6] || *end_to != '\0' ||
            from > to || invalid_filter) {
            status = OTRL_E_USAGE;
        } else {
            status = command_dump(context, argv[2], (uint64_t)from,
                                  (uint64_t)to, (uint32_t)filter, &error);
        }
    } else {
        usage(stderr);
        status = OTRL_E_USAGE;
    }
    if (status != OTRL_OK && status != OTRL_E_DIVERGENCE) {
        print_error(status, &error);
    }
    otrl_context_destroy(context);
    return cli_exit(status);
}
