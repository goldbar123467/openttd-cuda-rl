/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"
#include "openttd_rl_parity/field_schema.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

static const uint8_t PREFIX_MAGIC[8] = {'O', 'T', 'R', 'L', 'T', 'A', 'P', 0};
static const uint8_t TRAILER_MAGIC[8] = {'O', 'T', 'R', 'L', 'E', 'N', 'D', 0};

static otrl_status fail(otrl_error *error, otrl_status status, size_t offset,
                        uint64_t sequence, uint64_t step, uint64_t tick,
                        uint32_t field, const char *message)
{
    otrl_set_error(error, status, offset, sequence, step, tick, field, "%s",
                   message);
    return status;
}

static int known_record(uint16_t type)
{
    return type >= (uint16_t)OTRL_RECORD_REPLAY_START &&
           type <= (uint16_t)OTRL_RECORD_TERMINAL;
}

static int is_diagnostic_record(uint16_t type)
{
    return type >= OTRL_RECORD_RNG_DRAW_DIAGNOSTIC &&
           type <= OTRL_RECORD_TRACE_WARNING;
}

static otrl_status validate_command_payload(const otrl_record_internal *record,
                                            uint32_t expected_command,
                                            uint32_t *intent_command,
                                            otrl_error *error)
{
    const uint8_t *payload = record->payload;
    uint32_t declared;
    uint32_t command;
    size_t expected;
    if (record->type == OTRL_RECORD_COMMAND_INTENT) {
        if (record->payload_bytes < 24U) {
            return fail(error, OTRL_E_TRUNCATED,
                        record->record_offset + 40U + record->payload_bytes,
                        record->sequence, record->public_step, record->native_tick,
                        0U, "command intent payload truncated");
        }
        if (otrl_get_u16_le(payload) != 1U) return OTRL_E_VERSION;
        if (otrl_get_u16_le(payload + 2U) != 0U ||
            otrl_get_u32_le(payload + 20U) != 0U) return OTRL_E_RESERVED;
        command = otrl_get_u32_le(payload + 4U);
        declared = otrl_get_u32_le(payload + 16U);
        if (!otrl_checked_add_size(24U, declared, &expected)) return OTRL_E_OVERFLOW;
        if (expected != record->payload_bytes) return OTRL_E_STRUCTURE;
        *intent_command = command;
        return OTRL_OK;
    }
    if (record->payload_bytes < 32U) {
        return fail(error, OTRL_E_TRUNCATED,
                    record->record_offset + 40U + record->payload_bytes,
                    record->sequence, record->public_step, record->native_tick,
                    0U, "command result payload truncated");
    }
    if (otrl_get_u16_le(payload) != 1U) return OTRL_E_VERSION;
    if (payload[3] != 0U || payload[2] > 1U) return OTRL_E_RESERVED;
    command = otrl_get_u32_le(payload + 4U);
    declared = otrl_get_u32_le(payload + 28U);
    if (!otrl_checked_add_size(32U, declared, &expected)) return OTRL_E_OVERFLOW;
    if (expected != record->payload_bytes || command != expected_command) {
        return OTRL_E_STRUCTURE;
    }
    return OTRL_OK;
}

static otrl_status validate_fixed_payload(const otrl_record_internal *record)
{
    const uint8_t *payload = record->payload;
    switch (record->type) {
    case OTRL_RECORD_REPLAY_START:
        if (record->payload_bytes != 12U) return OTRL_E_STRUCTURE;
        if (otrl_get_u16_le(payload) != 1U) return OTRL_E_VERSION;
        if (payload[2] == 0U || payload[3] != 0U) return OTRL_E_RESERVED;
        return OTRL_OK;
    case OTRL_RECORD_NAMED_CHECKPOINT:
        if (record->payload_bytes != 8U) return OTRL_E_STRUCTURE;
        if (otrl_get_u16_le(payload) != 1U) return OTRL_E_VERSION;
        if (otrl_get_u16_le(payload + 2U) == 0U ||
            otrl_get_u16_le(payload + 2U) > 8U) return OTRL_E_SCHEMA;
        if (otrl_get_u32_le(payload + 4U) != 0U) return OTRL_E_RESERVED;
        return OTRL_OK;
    case OTRL_RECORD_TERMINAL:
        if (record->payload_bytes != 8U) return OTRL_E_STRUCTURE;
        if (otrl_get_u16_le(payload) != 1U) return OTRL_E_VERSION;
        if (otrl_get_u32_le(payload + 4U) != 0U) return OTRL_E_RESERVED;
        return OTRL_OK;
    default: return OTRL_OK;
    }
}

static size_t value_width(uint16_t type, uint16_t flags)
{
    switch (type) {
    case OTRL_VALUE_U8:
    case OTRL_VALUE_I8: return 1U;
    case OTRL_VALUE_U16:
    case OTRL_VALUE_I16: return 2U;
    case OTRL_VALUE_U32:
    case OTRL_VALUE_I32: return 4U;
    case OTRL_VALUE_U64:
    case OTRL_VALUE_I64: return 8U;
    case OTRL_VALUE_STABLE_ID:
        return (flags == 1U || flags == 2U || flags == 4U || flags == 8U) ?
                   (size_t)flags : 0U;
    default: return 0U;
    }
}

static int projection_scalar_value(const uint8_t *payload, size_t length,
                                   uint32_t wanted_id, uint64_t *value)
{
    size_t offset = OTRL_PROJECTION_HEADER_BYTES;
    while (offset < length) {
        size_t next;
        if (length - offset < OTRL_FIELD_HEADER_BYTES) return 0;
        const uint32_t field_id = otrl_get_u32_le(payload + offset);
        const uint16_t type = otrl_get_u16_le(payload + offset + 4U);
        const uint16_t flags = otrl_get_u16_le(payload + offset + 6U);
        const uint32_t elements = otrl_get_u32_le(payload + offset + 8U);
        const uint32_t bytes = otrl_get_u32_le(payload + offset + 12U);
        if (!otrl_checked_add_size(offset, OTRL_FIELD_HEADER_BYTES, &next) ||
            !otrl_checked_add_size(next, (size_t)bytes, &next)) return 0;
        if (field_id == wanted_id) {
            const size_t width = value_width(type, flags);
            uint64_t result = 0U;
            if (elements != 1U || width == 0U || width > 8U || bytes != width) {
                return 0;
            }
            for (size_t i = 0U; i < width; ++i) {
                result |= (uint64_t)payload[offset + OTRL_FIELD_HEADER_BYTES + i]
                          << (i * 8U);
            }
            *value = result;
            return 1;
        }
        if (!otrl_checked_align8_size(next, &offset) || offset > length) {
            return 0;
        }
    }
    return 0;
}

otrl_status otrl_parse_projection(const otrl_record_internal *record,
                                  otrl_error *error)
{
    const uint8_t *payload = record->payload;
    const size_t length = record->payload_bytes;
    uint32_t field_count;
    uint32_t previous = 0U;
    size_t offset = OTRL_PROJECTION_HEADER_BYTES;
    size_t registry_index = 0U;
    uint32_t index;
    if (length < OTRL_PROJECTION_HEADER_BYTES) {
        return fail(error, OTRL_E_TRUNCATED, record->record_offset + 40U + length,
                    record->sequence, record->public_step, record->native_tick, 0U,
                    "projection header truncated");
    }
    if (otrl_get_u16_le(payload) != 1U) {
        return fail(error, OTRL_E_VERSION, record->record_offset + 40U,
                    record->sequence, record->public_step, record->native_tick, 0U,
                    "unsupported projection version");
    }
    if (payload[3] != 0U) {
        return fail(error, OTRL_E_RESERVED, record->record_offset + 43U,
                    record->sequence, record->public_step, record->native_tick, 0U,
                    "projection reserved byte is nonzero");
    }
    field_count = otrl_get_u32_le(payload + 4U);
    if (field_count == 0U) {
        return fail(error, OTRL_E_SCHEMA, record->record_offset + 44U,
                    record->sequence, record->public_step, record->native_tick, 0U,
                    "required projection has no fields");
    }
    if (field_count > OTRL_MAX_FIELD_COUNT) {
        return fail(error, OTRL_E_LIMIT, record->record_offset + 44U,
                    record->sequence, record->public_step, record->native_tick, 0U,
                    "projection field count exceeds limit");
    }
    if ((size_t)field_count != otrl_field_authoritative_count()) {
        return fail(error, OTRL_E_SCHEMA, record->record_offset + 44U,
                    record->sequence, record->public_step, record->native_tick,
                    0U, "projection is not the complete authoritative registry");
    }
    for (index = 0U; index < field_count; ++index) {
        uint32_t field_id;
        uint16_t type;
        uint16_t flags;
        uint32_t elements;
        uint32_t byte_count;
        const otrl_field_meta *meta;
        size_t expected;
        size_t field_end;
        size_t padded_end;
        if (length - offset < OTRL_FIELD_HEADER_BYTES) {
            return fail(error, OTRL_E_TRUNCATED,
                        record->record_offset + 40U + offset, record->sequence,
                        record->public_step, record->native_tick, 0U,
                        "field header truncated");
        }
        field_id = otrl_get_u32_le(payload + offset);
        type = otrl_get_u16_le(payload + offset + 4U);
        flags = otrl_get_u16_le(payload + offset + 6U);
        elements = otrl_get_u32_le(payload + offset + 8U);
        byte_count = otrl_get_u32_le(payload + offset + 12U);
        if (field_id == 0U || field_id <= previous) {
            return fail(error, OTRL_E_SCHEMA,
                        record->record_offset + 40U + offset, record->sequence,
                        record->public_step, record->native_tick, field_id,
                        "field IDs must be nonzero and strictly increasing");
        }
        previous = field_id;
        do {
            meta = otrl_field_registry_at(registry_index++);
        } while (meta != NULL &&
                 meta->classification != OTRL_FIELD_AUTHORITATIVE_FULL);
        if (meta == NULL || meta->field_id != field_id ||
            meta->value_type != type) {
            return fail(error, OTRL_E_SCHEMA,
                        record->record_offset + 40U + offset,
                        record->sequence, record->public_step,
                        record->native_tick, field_id,
                        "unknown field ID or registry value-type mismatch");
        }
        if ((meta->shape == OTRL_FIELD_SCALAR ||
             meta->shape == OTRL_FIELD_FIXED_ARRAY) &&
            elements != meta->fixed_count) {
            return fail(error, OTRL_E_SCHEMA,
                        record->record_offset + 40U + offset + 8U,
                        record->sequence, record->public_step,
                        record->native_tick, field_id,
                        "field element count differs from registry");
        }
        if ((meta->shape == OTRL_FIELD_DYNAMIC_ARRAY ||
             meta->shape == OTRL_FIELD_BITSET) &&
            elements > meta->maximum_capacity) {
            return fail(error, OTRL_E_SCHEMA,
                        record->record_offset + 40U + offset + 8U,
                        record->sequence, record->public_step,
                        record->native_tick, field_id,
                        "dynamic field exceeds registry capacity");
        }
        if (byte_count > OTRL_MAX_FIELD_BYTES) {
            return fail(error, OTRL_E_LIMIT,
                        record->record_offset + 40U + offset + 12U,
                        record->sequence, record->public_step, record->native_tick,
                        field_id, "field bytes exceed limit");
        }
        offset += OTRL_FIELD_HEADER_BYTES;
        if (!otrl_checked_add_size(offset, (size_t)byte_count, &field_end) ||
            !otrl_checked_align8_size(field_end, &padded_end)) {
            return fail(error, OTRL_E_OVERFLOW, record->record_offset + 40U + offset,
                        record->sequence, record->public_step, record->native_tick,
                        field_id, "field framing overflow");
        }
        if (padded_end > length) {
            return fail(error, OTRL_E_TRUNCATED,
                        record->record_offset + 40U + length, record->sequence,
                        record->public_step, record->native_tick, field_id,
                        "field value or padding truncated");
        }
        expected = value_width(type, flags);
        if ((type != OTRL_VALUE_STABLE_ID && flags != 0U) ||
            (meta->width_bits != 0U && expected != 0U &&
             expected * 8U != meta->width_bits)) {
            return fail(error, OTRL_E_SCHEMA,
                        record->record_offset + 40U + offset,
                        record->sequence, record->public_step,
                        record->native_tick, field_id,
                        "field flags or width differ from registry");
        }
        if (expected != 0U) {
            if (!otrl_checked_mul_size((size_t)elements, expected, &expected)) {
                return fail(error, OTRL_E_OVERFLOW,
                            record->record_offset + 40U + offset,
                            record->sequence, record->public_step,
                            record->native_tick, field_id,
                            "field element multiplication overflow");
            }
            if (expected != byte_count) {
                return fail(error, OTRL_E_SCHEMA,
                            record->record_offset + 40U + offset,
                            record->sequence, record->public_step,
                            record->native_tick, field_id,
                            "numeric field count and width disagree");
            }
        } else if (type == OTRL_VALUE_BYTES) {
            if (flags != 0U || elements != byte_count) {
                return fail(error, OTRL_E_SCHEMA,
                            record->record_offset + 40U + offset,
                            record->sequence, record->public_step,
                            record->native_tick, field_id,
                            "byte field count disagrees");
            }
        } else if (type == OTRL_VALUE_BITSET) {
            const size_t bit_bytes = ((size_t)elements + 7U) / 8U;
            if (flags != 0U || bit_bytes != byte_count) {
                return fail(error, OTRL_E_SCHEMA,
                            record->record_offset + 40U + offset,
                            record->sequence, record->public_step,
                            record->native_tick, field_id, "bitset width disagrees");
            }
            if (elements != 0U && (elements & 7U) != 0U && byte_count != 0U) {
                const uint8_t allowed = (uint8_t)((UINT16_C(1) <<
                    (uint16_t)(elements & 7U)) - UINT16_C(1));
                if ((payload[field_end - 1U] & (uint8_t)~allowed) != 0U) {
                    return fail(error, OTRL_E_CANONICAL,
                                record->record_offset + 40U + field_end - 1U,
                                record->sequence, record->public_step,
                                record->native_tick, field_id,
                                "bitset high padding bits are nonzero");
                }
            }
        } else if (type == OTRL_VALUE_DIAGNOSTIC_UTF8) {
            if (meta->classification != OTRL_FIELD_DIAGNOSTIC || flags != 0U ||
                byte_count > OTRL_MAX_DIAGNOSTIC_STRING_BYTES ||
                elements != byte_count ||
                !otrl_utf8_valid(payload + offset, byte_count)) {
                return fail(error, OTRL_E_SCHEMA,
                            record->record_offset + 40U + offset,
                            record->sequence, record->public_step,
                            record->native_tick, field_id,
                            "invalid diagnostic UTF-8 field");
            }
        } else {
            return fail(error, OTRL_E_SCHEMA,
                        record->record_offset + 40U + offset, record->sequence,
                        record->public_step, record->native_tick, field_id,
                        "unknown or invalid value type");
        }
        for (size_t pad = field_end; pad < padded_end; ++pad) {
            if (payload[pad] != 0U) {
                return fail(error, OTRL_E_CANONICAL,
                            record->record_offset + 40U + pad,
                            record->sequence, record->public_step,
                            record->native_tick, field_id,
                            "field padding is nonzero");
            }
        }
        offset = padded_end;
    }
    if (offset != length) {
        return fail(error, OTRL_E_STRUCTURE, record->record_offset + 40U + offset,
                    record->sequence, record->public_step, record->native_tick,
                    previous, "bytes remain after projection fields");
    }
    offset = OTRL_PROJECTION_HEADER_BYTES;
    registry_index = 0U;
    for (index = 0U; index < field_count; ++index) {
        uint32_t field_id;
        uint16_t type;
        uint32_t elements;
        uint32_t byte_count;
        const otrl_field_meta *meta;
        size_t value_offset;
        size_t next;
        do {
            meta = otrl_field_registry_at(registry_index++);
        } while (meta != NULL &&
                 meta->classification != OTRL_FIELD_AUTHORITATIVE_FULL);
        if (meta == NULL) return OTRL_E_INTERNAL;
        field_id = otrl_get_u32_le(payload + offset);
        type = otrl_get_u16_le(payload + offset + 4U);
        elements = otrl_get_u32_le(payload + offset + 8U);
        byte_count = otrl_get_u32_le(payload + offset + 12U);
        value_offset = offset + OTRL_FIELD_HEADER_BYTES;
        next = value_offset + (size_t)byte_count;
        (void)otrl_checked_align8_size(next, &next);
        if (meta->count_source_field_id != 0U) {
            uint64_t declared_count;
            if (!projection_scalar_value(payload, length,
                                         meta->count_source_field_id,
                                         &declared_count) ||
                declared_count != (uint64_t)elements) {
                return fail(error, OTRL_E_SCHEMA,
                            record->record_offset + 40U + value_offset,
                            record->sequence, record->public_step,
                            record->native_tick, field_id,
                            "dynamic element count differs from count-source field");
            }
        }
        if (meta->offset_target_count_field_id != 0U) {
            uint64_t target_count;
            uint32_t prior_offset = 0U;
            if (type != OTRL_VALUE_U32 || elements == 0U ||
                !projection_scalar_value(payload, length,
                                         meta->offset_target_count_field_id,
                                         &target_count) ||
                otrl_get_u32_le(payload + value_offset) != 0U) {
                return fail(error, OTRL_E_SCHEMA,
                            record->record_offset + 40U + value_offset,
                            record->sequence, record->public_step,
                            record->native_tick, field_id,
                            "offset vector has invalid first or target value");
            }
            for (uint32_t element = 1U; element < elements; ++element) {
                const uint32_t current = otrl_get_u32_le(
                    payload + value_offset + (size_t)element * 4U);
                if (current < prior_offset) {
                    return fail(error, OTRL_E_SCHEMA,
                                record->record_offset + 40U + value_offset +
                                    (size_t)element * 4U,
                                record->sequence, record->public_step,
                                record->native_tick, field_id,
                                "offset vector is decreasing");
                }
                prior_offset = current;
            }
            if ((uint64_t)prior_offset != target_count) {
                return fail(error, OTRL_E_SCHEMA,
                            record->record_offset + 40U + value_offset +
                                (size_t)(elements - 1U) * 4U,
                            record->sequence, record->public_step,
                            record->native_tick, field_id,
                            "offset vector final value differs from target count");
            }
        }
        offset = next;
    }
    return OTRL_OK;
}

static void destroy_partial(otrl_context *context, otrl_tape *tape)
{
    if (tape != NULL) {
        if (tape->records != NULL) {
            for (uint64_t i = 0U; i < tape->record_count; ++i) {
                otrl_dealloc(context, tape->records[i].payload);
            }
        }
        otrl_dealloc(context, tape->records);
        otrl_dealloc(context, tape->header);
        if (tape->owns_mapping != 0 && tape->mapped_bytes != NULL) {
            (void)munmap((void *)(uintptr_t)tape->mapped_bytes,
                         tape->mapped_length);
        }
        otrl_dealloc(context, tape);
    }
}

static otrl_status validate_bytes_internal(otrl_context *context,
                                           const uint8_t *bytes,
                                           size_t length,
                                           int retain_records,
                                           int mapped_input,
                                           otrl_tape **out_tape,
                                           otrl_error *error)
{
    uint32_t header_bytes;
    uint64_t record_count;
    uint64_t record_bytes;
    size_t records_offset;
    size_t trailer_offset;
    size_t expected_length;
    otrl_tape *tape = NULL;
    uint64_t previous_step = 0U;
    uint64_t previous_tick = 0U;
    int have_previous = 0;
    int saw_projection = 0;
    int command_phase = 0;
    int command_test_succeeded = 0;
    uint32_t active_command = 0U;
    uint32_t command_count = 0U;
    uint16_t last_record_type = 0U;
    otrl_status status = OTRL_OK;
    if (context == NULL || out_tape == NULL || (bytes == NULL && length != 0U)) {
        return fail(error, OTRL_E_USAGE, 0U, UINT64_MAX, 0U, 0U, 0U,
                    "invalid validate arguments");
    }
    if (length < OTRL_PREFIX_BYTES) {
        return fail(error, OTRL_E_TRUNCATED, length, UINT64_MAX, 0U, 0U, 0U,
                    "file prefix truncated");
    }
    if ((uint64_t)length > OTRL_MAX_TAPE_BYTES ||
        (uint64_t)length > context->local_max_tape_bytes) {
        return fail(error, OTRL_E_LIMIT, 0U, UINT64_MAX, 0U, 0U, 0U,
                    "tape exceeds configured limit");
    }
    for (size_t i = 0U; i < sizeof(PREFIX_MAGIC); ++i) {
        if (bytes[i] != PREFIX_MAGIC[i]) {
            return fail(error, OTRL_E_MAGIC, i, UINT64_MAX, 0U, 0U, 0U,
                        "bad file prefix magic");
        }
    }
    if (otrl_get_u16_le(bytes + 8U) != OTRL_FORMAT_MAJOR ||
        otrl_get_u16_le(bytes + 10U) != OTRL_FORMAT_MINOR) {
        return fail(error, OTRL_E_VERSION, 8U, UINT64_MAX, 0U, 0U, 0U,
                    "unsupported tape version");
    }
    if (bytes[12] != OTRL_BYTE_ORDER_LE) {
        return fail(error, OTRL_E_ENDIAN, 12U, UINT64_MAX, 0U, 0U, 0U,
                    "unsupported byte order");
    }
    if (bytes[13] != OTRL_HASH_SHA256) {
        return fail(error, OTRL_E_HASH_ALGORITHM, 13U, UINT64_MAX, 0U, 0U, 0U,
                    "unsupported hash algorithm");
    }
    if (otrl_get_u16_le(bytes + 14U) != OTRL_PREFIX_BYTES) {
        return fail(error, OTRL_E_STRUCTURE, 14U, UINT64_MAX, 0U, 0U, 0U,
                    "prefix byte count is not 64");
    }
    header_bytes = otrl_get_u32_le(bytes + 16U);
    if (header_bytes == 0U) {
        return fail(error, OTRL_E_SCHEMA, 16U, UINT64_MAX, 0U, 0U, 0U,
                    "header is empty");
    }
    if (header_bytes > OTRL_MAX_HEADER_BYTES) {
        return fail(error, OTRL_E_LIMIT, 16U, UINT64_MAX, 0U, 0U, 0U,
                    "header exceeds format limit");
    }
    {
        const uint32_t flags = otrl_get_u32_le(bytes + 20U);
        if ((flags & OTRL_PREFIX_REQUIRED_FLAG_MASK & ~OTRL_PREFIX_KNOWN_FLAGS) != 0U) {
            return fail(error, OTRL_E_VERSION, 20U, UINT64_MAX, 0U, 0U, 0U,
                        "unknown required prefix feature");
        }
        if ((flags & OTRL_PREFIX_FLAG_PARTIAL) != 0U) {
            return fail(error, OTRL_E_STRUCTURE, 20U, UINT64_MAX, 0U, 0U, 0U,
                        "partial tape requires explicit finalization");
        }
    }
    record_count = otrl_get_u64_le(bytes + 24U);
    record_bytes = otrl_get_u64_le(bytes + 32U);
    if (record_count > OTRL_MAX_RECORD_COUNT ||
        record_count > context->local_max_record_count) {
        return fail(error, OTRL_E_LIMIT, 24U, UINT64_MAX, 0U, 0U, 0U,
                    "record count exceeds configured limit");
    }
    if (otrl_get_u64_le(bytes + 56U) != 0U) {
        return fail(error, OTRL_E_RESERVED, 56U, UINT64_MAX, 0U, 0U, 0U,
                    "prefix reserved field is nonzero");
    }
    if (!otrl_checked_add_size(OTRL_PREFIX_BYTES, header_bytes, &records_offset) ||
        record_bytes > SIZE_MAX ||
        !otrl_checked_add_size(records_offset, (size_t)record_bytes,
                               &trailer_offset) ||
        !otrl_checked_add_size(trailer_offset, OTRL_TRAILER_BYTES,
                               &expected_length)) {
        return fail(error, OTRL_E_OVERFLOW, 16U, UINT64_MAX, 0U, 0U, 0U,
                    "declared tape lengths overflow address space");
    }
    if (expected_length > length) {
        return fail(error, OTRL_E_TRUNCATED, length, UINT64_MAX, 0U, 0U, 0U,
                    "declared tape extends beyond input");
    }
    if (expected_length < length) {
        return fail(error, OTRL_E_STRUCTURE, expected_length, UINT64_MAX, 0U, 0U,
                    0U, "trailing data follows trailer");
    }
    if (record_count == 0U || record_count > record_bytes / OTRL_RECORD_HEADER_BYTES) {
        return fail(error, OTRL_E_STRUCTURE, 24U, UINT64_MAX, 0U, 0U, 0U,
                    "record count is inconsistent with record region");
    }
    for (size_t i = 0U; i < sizeof(TRAILER_MAGIC); ++i) {
        if (bytes[trailer_offset + i] != TRAILER_MAGIC[i]) {
            return fail(error, OTRL_E_MAGIC, trailer_offset + i, UINT64_MAX, 0U,
                        0U, 0U, "bad trailer magic");
        }
    }
    if (otrl_get_u64_le(bytes + trailer_offset + 8U) != record_count ||
        otrl_get_u64_le(bytes + trailer_offset + 16U) != trailer_offset) {
        return fail(error, OTRL_E_STRUCTURE, trailer_offset + 8U, UINT64_MAX, 0U,
                    0U, 0U, "trailer counts disagree with prefix");
    }
    if (otrl_get_u64_le(bytes + trailer_offset + 56U) != 0U) {
        return fail(error, OTRL_E_RESERVED, trailer_offset + 56U, UINT64_MAX, 0U,
                    0U, 0U, "trailer reserved field is nonzero");
    }
    {
        uint8_t digest[32];
        status = mapped_input != 0 ?
            otrl_sha256_mapped(bytes, trailer_offset, digest) :
            otrl_sha256(bytes, trailer_offset, digest);
        if (status != OTRL_OK) {
            return fail(error, status, trailer_offset + 24U, UINT64_MAX, 0U, 0U,
                        0U, "SHA-256 provider failed");
        }
        if (memcmp(digest, bytes + trailer_offset + 24U, 32U) != 0) {
            return fail(error, OTRL_E_CHECKSUM, trailer_offset + 24U, UINT64_MAX,
                        0U, 0U, 0U, "covered-byte SHA-256 mismatch");
        }
    }
    status = otrl_validate_canonical_header(bytes + OTRL_PREFIX_BYTES,
                                            header_bytes, error);
    if (status != OTRL_OK) {
        return status;
    }
    tape = otrl_alloc(context, sizeof(*tape));
    if (tape == NULL) {
        return fail(error, OTRL_E_IO, 0U, UINT64_MAX, 0U, 0U, 0U,
                    "tape allocation failed");
    }
    memset(tape, 0, sizeof(*tape));
    tape->major = OTRL_FORMAT_MAJOR;
    tape->minor = OTRL_FORMAT_MINOR;
    tape->flags = otrl_get_u32_le(bytes + 20U);
    tape->record_count = record_count;
    tape->record_bytes = record_bytes;
    tape->max_step = otrl_get_u64_le(bytes + 40U);
    tape->max_tick = otrl_get_u64_le(bytes + 48U);
    tape->header_bytes = header_bytes;
    memcpy(tape->digest, bytes + trailer_offset + 24U, 32U);
    tape->header = otrl_alloc(context, header_bytes);
    if (tape->header == NULL) {
        status = OTRL_E_IO;
        goto cleanup;
    }
    memcpy(tape->header, bytes + OTRL_PREFIX_BYTES, header_bytes);
    if (retain_records != 0) {
        size_t allocation_size;
        if (!otrl_checked_mul_size((size_t)record_count,
                                   sizeof(*tape->records), &allocation_size)) {
            status = OTRL_E_OVERFLOW;
            goto cleanup;
        }
        tape->records = otrl_alloc(context, allocation_size);
        if (tape->records == NULL) {
            status = OTRL_E_IO;
            goto cleanup;
        }
        memset(tape->records, 0, allocation_size);
    }
    {
        size_t offset = records_offset;
        for (uint64_t sequence = 0U; sequence < record_count; ++sequence) {
            otrl_record_internal temporary_record;
            otrl_record_internal *record = retain_records != 0 ?
                &tape->records[sequence] : &temporary_record;
            size_t unpadded;
            size_t padded;
            size_t record_end;
            if (trailer_offset - offset < OTRL_RECORD_HEADER_BYTES) {
                status = fail(error, OTRL_E_TRUNCATED, offset, sequence, 0U, 0U,
                              0U, "record header truncated");
                goto cleanup;
            }
            memset(record, 0, sizeof(*record));
            record->record_offset = offset;
            record->type = otrl_get_u16_le(bytes + offset);
            record->version = otrl_get_u16_le(bytes + offset + 2U);
            record->flags = otrl_get_u32_le(bytes + offset + 4U);
            record->sequence = otrl_get_u64_le(bytes + offset + 8U);
            record->public_step = otrl_get_u64_le(bytes + offset + 16U);
            record->native_tick = otrl_get_u64_le(bytes + offset + 24U);
            record->payload_bytes = otrl_get_u32_le(bytes + offset + 32U);
            if (otrl_get_u32_le(bytes + offset + 36U) != 0U) {
                status = fail(error, OTRL_E_RESERVED, offset + 36U, sequence,
                              record->public_step, record->native_tick, 0U,
                              "record reserved field is nonzero");
                goto cleanup;
            }
            if (record->payload_bytes > OTRL_MAX_RECORD_PAYLOAD_BYTES) {
                status = fail(error, OTRL_E_LIMIT, offset + 32U, sequence,
                              record->public_step, record->native_tick, 0U,
                              "record payload exceeds limit");
                goto cleanup;
            }
            if (record->sequence != sequence) {
                status = fail(error, OTRL_E_SEQUENCE, offset + 8U, sequence,
                              record->public_step, record->native_tick, 0U,
                              "record sequence is not contiguous from zero");
                goto cleanup;
            }
            if ((record->flags & ~OTRL_RECORD_KNOWN_FLAGS) != 0U) {
                status = fail(error, OTRL_E_RESERVED, offset + 4U, sequence,
                              record->public_step, record->native_tick, 0U,
                              "unknown record flags");
                goto cleanup;
            }
            if (!known_record(record->type)) {
                if ((record->flags & OTRL_RECORD_FLAG_REQUIRED) != 0U) {
                    status = fail(error, OTRL_E_VERSION, offset, sequence,
                                  record->public_step, record->native_tick, 0U,
                                  "unknown required record type");
                    goto cleanup;
                }
            } else if (record->version != 1U) {
                status = fail(error, OTRL_E_VERSION, offset + 2U, sequence,
                              record->public_step, record->native_tick, 0U,
                              "unsupported record version");
                goto cleanup;
            }
            if (known_record(record->type) &&
                !is_diagnostic_record(record->type) &&
                (record->flags & OTRL_RECORD_FLAG_REQUIRED) == 0U) {
                status = fail(error, OTRL_E_STRUCTURE, offset + 4U, sequence,
                              record->public_step, record->native_tick, 0U,
                              "authoritative record is not marked required");
                goto cleanup;
            }
            if (have_previous && (record->public_step < previous_step ||
                                  record->native_tick < previous_tick)) {
                status = fail(error, OTRL_E_SEQUENCE, offset + 16U, sequence,
                              record->public_step, record->native_tick, 0U,
                              "record boundary decreases");
                goto cleanup;
            }
            have_previous = 1;
            previous_step = record->public_step;
            previous_tick = record->native_tick;
            if (!otrl_checked_add_size(OTRL_RECORD_HEADER_BYTES,
                                       record->payload_bytes, &unpadded) ||
                !otrl_checked_align8_size(unpadded, &padded) ||
                !otrl_checked_add_size(offset, padded, &record_end)) {
                status = fail(error, OTRL_E_OVERFLOW, offset + 32U, sequence,
                              record->public_step, record->native_tick, 0U,
                              "record framing overflow");
                goto cleanup;
            }
            if (record_end > trailer_offset) {
                status = fail(error, OTRL_E_TRUNCATED, trailer_offset, sequence,
                              record->public_step, record->native_tick, 0U,
                              "record payload or padding truncated");
                goto cleanup;
            }
            record->padded_bytes = padded;
            if (retain_records != 0 && record->payload_bytes != 0U) {
                record->payload = otrl_alloc(context, record->payload_bytes);
                if (record->payload == NULL) {
                    status = OTRL_E_IO;
                    goto cleanup;
                }
                memcpy(record->payload, bytes + offset + 40U,
                       record->payload_bytes);
            } else if (record->payload_bytes != 0U) {
                record->payload = (uint8_t *)(uintptr_t)(bytes + offset + 40U);
            }
            for (size_t pad = offset + unpadded; pad < record_end; ++pad) {
                if (bytes[pad] != 0U) {
                    status = fail(error, OTRL_E_CANONICAL, pad, sequence,
                                  record->public_step, record->native_tick, 0U,
                                  "record padding is nonzero");
                    goto cleanup;
                }
            }
            if (sequence == 0U && record->type != OTRL_RECORD_REPLAY_START) {
                status = fail(error, OTRL_E_STRUCTURE, offset, sequence,
                              record->public_step, record->native_tick, 0U,
                              "first record is not replay start");
                goto cleanup;
            }
            if (record->type == OTRL_RECORD_TERMINAL) {
                if (sequence + 1U != record_count || command_phase != 0) {
                    status = fail(error, OTRL_E_STRUCTURE, offset, sequence,
                                  record->public_step, record->native_tick, 0U,
                                  "terminal is not last or command is incomplete");
                    goto cleanup;
                }
            } else if (sequence + 1U == record_count) {
                status = fail(error, OTRL_E_STRUCTURE, offset, sequence,
                              record->public_step, record->native_tick, 0U,
                              "terminal record is missing");
                goto cleanup;
            }
            if (record->type == OTRL_RECORD_TRACE_WARNING &&
                (tape->flags & OTRL_PREFIX_FLAG_OPTIONAL_DIAGNOSTICS) == 0U) {
                status = fail(error, OTRL_E_STRUCTURE, offset, sequence,
                              record->public_step, record->native_tick, 0U,
                              "trace warning requires optional-diagnostics mode");
                goto cleanup;
            }
            status = validate_fixed_payload(record);
            if (status != OTRL_OK) goto cleanup;
            switch (record->type) {
            case OTRL_RECORD_COMMAND_INTENT:
                if (command_phase != 0) { status = OTRL_E_STRUCTURE; goto cleanup; }
                if (++command_count > OTRL_MAX_COMMAND_COUNT) {
                    status = OTRL_E_LIMIT; goto cleanup;
                }
                status = validate_command_payload(record, 0U, &active_command, error);
                if (status != OTRL_OK) goto cleanup;
                command_phase = 1;
                break;
            case OTRL_RECORD_COMMAND_TEST_RESULT:
                if (command_phase != 1) { status = OTRL_E_STRUCTURE; goto cleanup; }
                status = validate_command_payload(record, active_command,
                                                  &active_command, error);
                if (status != OTRL_OK) goto cleanup;
                command_test_succeeded = record->payload[2] != 0U;
                command_phase = 2;
                break;
            case OTRL_RECORD_COMMAND_EXEC_RESULT:
                if (command_phase != 2 || !command_test_succeeded) {
                    status = OTRL_E_STRUCTURE; goto cleanup;
                }
                status = validate_command_payload(record, active_command,
                                                  &active_command, error);
                if (status != OTRL_OK) goto cleanup;
                command_phase = 3;
                break;
            case OTRL_RECORD_AUTHORITATIVE_PROJECTION:
                if (command_phase != 0 && command_phase != 3 &&
                    !(command_phase == 2 && !command_test_succeeded)) {
                    status = OTRL_E_STRUCTURE;
                    goto cleanup;
                }
                command_phase = 0;
                saw_projection = 1;
                status = otrl_parse_projection(record, error);
                if (status != OTRL_OK) { goto cleanup; }
                break;
            default: break;
            }
            last_record_type = record->type;
            offset = record_end;
        }
        if (offset != trailer_offset || !saw_projection ||
            last_record_type != OTRL_RECORD_TERMINAL ||
            previous_step != tape->max_step || previous_tick != tape->max_tick) {
            status = fail(error, OTRL_E_STRUCTURE, offset, record_count - 1U,
                          previous_step, previous_tick, 0U,
                          "record region, projection, terminal, or maxima mismatch");
            goto cleanup;
        }
    }
    *out_tape = tape;
    return OTRL_OK;

cleanup:
    if (status == OTRL_E_IO || status == OTRL_E_OVERFLOW ||
        status == OTRL_E_STRUCTURE) {
        otrl_set_error(error, status, 0U, UINT64_MAX, 0U, 0U, 0U,
                       "tape parse failed: %s", otrl_status_string(status));
    }
    destroy_partial(context, tape);
    return status;
}

otrl_status otrl_validate_bytes(otrl_context *context,
                                const uint8_t *bytes,
                                size_t length,
                                otrl_tape **out_tape,
                                otrl_error *error)
{
    return validate_bytes_internal(context, bytes, length, 1, 0, out_tape, error);
}

otrl_status otrl_validate_file(otrl_context *context, const char *path,
                               otrl_tape **out_tape, otrl_error *error)
{
    struct stat file_status;
    int descriptor;
    void *mapping;
    size_t length;
    otrl_status status;
    if (context == NULL || path == NULL || out_tape == NULL) {
        return OTRL_E_USAGE;
    }
    descriptor = open(path, O_RDONLY | O_CLOEXEC);
    if (descriptor < 0 || fstat(descriptor, &file_status) != 0) {
        if (descriptor >= 0) (void)close(descriptor);
        return fail(error, OTRL_E_IO, 0U, UINT64_MAX, 0U, 0U, 0U,
                    "cannot open or stat input tape");
    }
    if (file_status.st_size < 0 || (uint64_t)file_status.st_size >
        context->local_max_tape_bytes ||
        (uint64_t)file_status.st_size > OTRL_MAX_TAPE_BYTES ||
        (uint64_t)file_status.st_size > SIZE_MAX) {
        (void)close(descriptor);
        return OTRL_E_LIMIT;
    }
    length = (size_t)file_status.st_size;
    if (length == 0U) {
        (void)close(descriptor);
        return fail(error, OTRL_E_TRUNCATED, 0U, UINT64_MAX, 0U, 0U, 0U,
                    "file prefix truncated");
    }
    mapping = mmap(NULL, length, PROT_READ, MAP_PRIVATE, descriptor, 0);
    if (close(descriptor) != 0 || mapping == MAP_FAILED) {
        if (mapping != MAP_FAILED) (void)munmap(mapping, length);
        return OTRL_E_IO;
    }
#ifdef MADV_SEQUENTIAL
    (void)madvise(mapping, length, MADV_SEQUENTIAL);
#endif
    status = validate_bytes_internal(context, mapping, length, 0, 1, out_tape,
                                     error);
    if (status == OTRL_OK) {
        (*out_tape)->mapped_bytes = mapping;
        (*out_tape)->mapped_length = length;
        (*out_tape)->owns_mapping = 1;
    } else {
        (void)munmap(mapping, length);
    }
    return status;
}

void otrl_tape_destroy(otrl_context *context, otrl_tape *tape)
{
    destroy_partial(context, tape);
}

otrl_status otrl_tape_get_info(const otrl_tape *tape, otrl_tape_info *out_info,
                               otrl_error *error)
{
    if (tape == NULL || out_info == NULL ||
        !otrl_valid_public_struct(out_info, out_info->size,
                                  (uint32_t)sizeof(*out_info), out_info->version) ||
        out_info->reserved != 0U) {
        return fail(error, OTRL_E_USAGE, 0U, UINT64_MAX, 0U, 0U, 0U,
                    "invalid tape info ABI");
    }
    out_info->format_major = tape->major;
    out_info->format_minor = tape->minor;
    out_info->flags = tape->flags;
    out_info->record_count = tape->record_count;
    out_info->record_bytes = tape->record_bytes;
    out_info->maximum_public_step = tape->max_step;
    out_info->maximum_native_tick = tape->max_tick;
    out_info->header_json = tape->header;
    out_info->header_bytes = tape->header_bytes;
    memcpy(out_info->covered_sha256, tape->digest, 32U);
    return OTRL_OK;
}

void otrl_record_cursor_init(const otrl_tape *tape, otrl_record_cursor *cursor)
{
    memset(cursor, 0, sizeof(*cursor));
    cursor->tape = tape;
    cursor->offset = OTRL_PREFIX_BYTES + tape->header_bytes;
    cursor->released_offset = 0U;
    {
        const long page_size = sysconf(_SC_PAGESIZE);
        cursor->page_size = page_size > 0 ? (size_t)page_size : 4096U;
    }
}

const otrl_record_internal *otrl_record_cursor_next(otrl_record_cursor *cursor)
{
    const otrl_tape *tape;
    size_t framed;
    if (cursor == NULL || cursor->tape == NULL) return NULL;
    tape = cursor->tape;
    if (cursor->index >= tape->record_count) return NULL;
    if (tape->records != NULL) return &tape->records[cursor->index++];
    if (tape->mapped_bytes == NULL || cursor->offset > tape->mapped_length ||
        tape->mapped_length - cursor->offset < OTRL_RECORD_HEADER_BYTES) return NULL;
#ifdef MADV_DONTNEED
    {
        const size_t release_end = cursor->offset -
                                   (cursor->offset % cursor->page_size);
        if (release_end > cursor->released_offset) {
            (void)madvise((void *)(uintptr_t)(tape->mapped_bytes +
                                              cursor->released_offset),
                          release_end - cursor->released_offset,
                          MADV_DONTNEED);
            cursor->released_offset = release_end;
        }
    }
#endif
    memset(&cursor->scratch, 0, sizeof(cursor->scratch));
    cursor->scratch.record_offset = cursor->offset;
    cursor->scratch.type = otrl_get_u16_le(tape->mapped_bytes + cursor->offset);
    cursor->scratch.version =
        otrl_get_u16_le(tape->mapped_bytes + cursor->offset + 2U);
    cursor->scratch.flags =
        otrl_get_u32_le(tape->mapped_bytes + cursor->offset + 4U);
    cursor->scratch.sequence =
        otrl_get_u64_le(tape->mapped_bytes + cursor->offset + 8U);
    cursor->scratch.public_step =
        otrl_get_u64_le(tape->mapped_bytes + cursor->offset + 16U);
    cursor->scratch.native_tick =
        otrl_get_u64_le(tape->mapped_bytes + cursor->offset + 24U);
    cursor->scratch.payload_bytes =
        otrl_get_u32_le(tape->mapped_bytes + cursor->offset + 32U);
    cursor->scratch.payload = (uint8_t *)(uintptr_t)(
        tape->mapped_bytes + cursor->offset + OTRL_RECORD_HEADER_BYTES);
    if (!otrl_checked_add_size(OTRL_RECORD_HEADER_BYTES,
                               cursor->scratch.payload_bytes, &framed) ||
        !otrl_checked_align8_size(framed, &framed)) return NULL;
    cursor->scratch.padded_bytes = framed;
    cursor->offset += framed;
    ++cursor->index;
    return &cursor->scratch;
}

otrl_status otrl_tape_iterate(const otrl_tape *tape,
                              otrl_record_callback callback, void *user,
                              otrl_error *error)
{
    otrl_record_cursor cursor;
    const otrl_record_internal *record;
    if (tape == NULL || callback == NULL) {
        return OTRL_E_USAGE;
    }
    otrl_record_cursor_init(tape, &cursor);
    while ((record = otrl_record_cursor_next(&cursor)) != NULL) {
        otrl_record_view view;
        otrl_status status;
        memset(&view, 0, sizeof(view));
        view.size = (uint32_t)sizeof(view);
        view.version = OTRL_ABI_VERSION;
        view.type = record->type;
        view.record_version = record->version;
        view.flags = record->flags;
        view.sequence = record->sequence;
        view.public_step = record->public_step;
        view.native_tick = record->native_tick;
        view.payload = record->payload;
        view.payload_bytes = record->payload_bytes;
        status = callback(user, &view, error);
        if (status != OTRL_OK) {
            return status;
        }
    }
    return OTRL_OK;
}

otrl_status otrl_write_atomic(const char *path, const uint8_t *bytes,
                              size_t length, otrl_error *error)
{
    char temporary[4096];
    char parent[4096];
    char *slash;
    int descriptor = -1;
    int directory = -1;
    int saved_errno = 0;
    int promoted = 0;
    size_t written = 0U;
    int result;
    if (path == NULL || path[0] == '\0' || bytes == NULL) {
        otrl_set_error(error, OTRL_E_USAGE, 0U, UINT64_MAX, 0U, 0U, 0U,
                       "atomic output path and bytes are required");
        return OTRL_E_USAGE;
    }
    result = snprintf(temporary, sizeof(temporary), "%s.partial.XXXXXX", path);
    if (result < 0 ||
        (size_t)result >= sizeof(temporary)) {
        otrl_set_error(error, OTRL_E_USAGE, 0U, UINT64_MAX, 0U, 0U, 0U,
                       "atomic output path is too long");
        return OTRL_E_USAGE;
    }
    result = snprintf(parent, sizeof(parent), "%s", path);
    if (result < 0 || (size_t)result >= sizeof(parent)) {
        otrl_set_error(error, OTRL_E_USAGE, 0U, UINT64_MAX, 0U, 0U, 0U,
                       "atomic output parent path is too long");
        return OTRL_E_USAGE;
    }
    slash = strrchr(parent, '/');
    if (slash == NULL) {
        (void)snprintf(parent, sizeof(parent), ".");
    } else if (slash == parent) {
        slash[1] = '\0';
    } else {
        *slash = '\0';
    }
    descriptor = mkstemp(temporary);
    if (descriptor < 0) {
        saved_errno = errno;
        goto failure;
    }
    if (fcntl(descriptor, F_SETFD, FD_CLOEXEC) != 0 ||
        fchmod(descriptor, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH) != 0) {
        saved_errno = errno;
        goto failure;
    }
    while (written < length) {
        ssize_t amount;
        do {
            amount = write(descriptor, bytes + written, length - written);
        } while (amount < 0 && errno == EINTR);
        if (amount <= 0) {
            saved_errno = amount == 0 ? EIO : errno;
            goto failure;
        }
        written += (size_t)amount;
    }
    do {
        result = fsync(descriptor);
    } while (result != 0 && errno == EINTR);
    if (result != 0) {
        saved_errno = errno;
        goto failure;
    }
    if (close(descriptor) != 0) {
        saved_errno = errno;
        descriptor = -1;
        goto failure;
    }
    descriptor = -1;
    if (link(temporary, path) != 0) {
        saved_errno = errno;
        goto failure;
    }
    promoted = 1;
#ifdef O_DIRECTORY
    directory = open(parent, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
#else
    directory = open(parent, O_RDONLY | O_CLOEXEC);
#endif
    if (directory < 0) {
        saved_errno = errno;
        goto failure;
    }
    do {
        result = fsync(directory);
    } while (result != 0 && errno == EINTR);
    if (result != 0) {
        saved_errno = errno;
        goto failure;
    }
    if (unlink(temporary) != 0) {
        saved_errno = errno;
        goto failure;
    }
    temporary[0] = '\0';
    do {
        result = fsync(directory);
    } while (result != 0 && errno == EINTR);
    if (result != 0) {
        saved_errno = errno;
        goto failure;
    }
    if (close(directory) != 0) {
        saved_errno = errno;
        directory = -1;
        goto failure;
    }
    return OTRL_OK;

failure:
    if (descriptor >= 0) {
        (void)close(descriptor);
    }
    if (promoted != 0) {
        (void)unlink(path);
    }
    if (temporary[0] != '\0') {
        (void)unlink(temporary);
    }
    if (directory >= 0) {
        (void)fsync(directory);
        (void)close(directory);
    }
    if (saved_errno == 0) {
        saved_errno = EIO;
    }
    otrl_set_error(error, OTRL_E_IO, 0U, UINT64_MAX, 0U, 0U, 0U,
                   "atomic output transaction failed: %s",
                   strerror(saved_errno));
    return OTRL_E_IO;
}
