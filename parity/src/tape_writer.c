/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"

#include <string.h>

otrl_status otrl_writer_create(otrl_context *context,
                               const otrl_writer_options *options,
                               otrl_writer **out_writer,
                               otrl_error *error)
{
    otrl_writer *writer;
    otrl_status status;
    if (context == NULL || options == NULL || out_writer == NULL ||
        !otrl_valid_public_struct(options, options->size,
                                  (uint32_t)sizeof(*options), options->version) ||
        options->reserved != 0U || options->reserved2 != 0U) {
        return OTRL_E_USAGE;
    }
    for (size_t i = 0U; i < 4U; ++i) {
        if (options->reserved3[i] != 0U) {
            return OTRL_E_RESERVED;
        }
    }
    if ((options->flags & OTRL_PREFIX_REQUIRED_FLAG_MASK &
         ~OTRL_PREFIX_KNOWN_FLAGS) != 0U) {
        return OTRL_E_VERSION;
    }
    status = otrl_validate_canonical_header(options->header_json,
                                            options->header_bytes, error);
    if (status != OTRL_OK) {
        return status;
    }
    writer = otrl_alloc(context, sizeof(*writer));
    if (writer == NULL) {
        return OTRL_E_IO;
    }
    memset(writer, 0, sizeof(*writer));
    writer->context = context;
    writer->flags = options->flags & ~OTRL_PREFIX_FLAG_PARTIAL;
    writer->header_bytes = options->header_bytes;
    writer->header = otrl_alloc(context, options->header_bytes);
    if (writer->header == NULL) {
        otrl_dealloc(context, writer);
        return OTRL_E_IO;
    }
    memcpy(writer->header, options->header_json, options->header_bytes);
    *out_writer = writer;
    return OTRL_OK;
}

static otrl_status grow_records(otrl_writer *writer)
{
    uint64_t new_capacity = writer->capacity == 0U ? 8U : writer->capacity * 2U;
    size_t allocation_size;
    otrl_record_internal *records;
    if (new_capacity < writer->capacity ||
        new_capacity > writer->context->local_max_record_count) {
        new_capacity = writer->context->local_max_record_count;
    }
    if (new_capacity <= writer->capacity || new_capacity > SIZE_MAX ||
        !otrl_checked_mul_size((size_t)new_capacity, sizeof(*records),
                               &allocation_size)) {
        return OTRL_E_LIMIT;
    }
    records = otrl_alloc(writer->context, allocation_size);
    if (records == NULL) {
        return OTRL_E_IO;
    }
    memset(records, 0, allocation_size);
    if (writer->records != NULL) {
        size_t old_bytes;
        if (!otrl_checked_mul_size((size_t)writer->count, sizeof(*records),
                                   &old_bytes)) {
            otrl_dealloc(writer->context, records);
            return OTRL_E_OVERFLOW;
        }
        memcpy(records, writer->records, old_bytes);
        otrl_dealloc(writer->context, writer->records);
    }
    writer->records = records;
    writer->capacity = new_capacity;
    return OTRL_OK;
}

otrl_status otrl_writer_add_record(otrl_writer *writer,
                                   const otrl_record_view *record,
                                   otrl_error *error)
{
    otrl_record_internal *target;
    size_t framed;
    otrl_status status;
    if (writer == NULL || record == NULL || writer->finalized ||
        !otrl_valid_public_struct(record, record->size,
                                  (uint32_t)sizeof(*record), record->version) ||
        record->reserved != 0U ||
        (record->payload == NULL && record->payload_bytes != 0U)) {
        return OTRL_E_USAGE;
    }
    if (record->sequence != writer->count) {
        return OTRL_E_SEQUENCE;
    }
    if (record->payload_bytes > OTRL_MAX_RECORD_PAYLOAD_BYTES ||
        !otrl_checked_add_size(OTRL_RECORD_HEADER_BYTES, record->payload_bytes,
                               &framed) ||
        !otrl_checked_align8_size(framed, &framed)) {
        return OTRL_E_LIMIT;
    }
    if (writer->count == writer->capacity) {
        status = grow_records(writer);
        if (status != OTRL_OK) {
            return status;
        }
    }
    target = &writer->records[writer->count];
    target->type = record->type;
    target->version = record->record_version;
    target->flags = record->flags;
    target->sequence = record->sequence;
    target->public_step = record->public_step;
    target->native_tick = record->native_tick;
    target->payload_bytes = record->payload_bytes;
    target->padded_bytes = framed;
    if (record->payload_bytes != 0U) {
        target->payload = otrl_alloc(writer->context, record->payload_bytes);
        if (target->payload == NULL) {
            memset(target, 0, sizeof(*target));
            return OTRL_E_IO;
        }
        memcpy(target->payload, record->payload, record->payload_bytes);
    }
    ++writer->count;
    (void)error;
    return OTRL_OK;
}

otrl_status otrl_serialize_tape(otrl_writer *writer, uint8_t **out_bytes,
                                size_t *out_length, otrl_error *error)
{
    uint64_t record_bytes = 0U;
    uint64_t max_step = 0U;
    uint64_t max_tick = 0U;
    size_t covered;
    size_t total;
    size_t offset;
    uint8_t *bytes;
    otrl_tape *validated = NULL;
    otrl_status status;
    if (writer == NULL || out_bytes == NULL || out_length == NULL ||
        writer->finalized || writer->count == 0U) {
        return OTRL_E_USAGE;
    }
    for (uint64_t i = 0U; i < writer->count; ++i) {
        if (writer->records[i].padded_bytes > UINT64_MAX - record_bytes) {
            return OTRL_E_OVERFLOW;
        }
        record_bytes += (uint64_t)writer->records[i].padded_bytes;
        max_step = writer->records[i].public_step;
        max_tick = writer->records[i].native_tick;
    }
    if (record_bytes > SIZE_MAX ||
        !otrl_checked_add_size(OTRL_PREFIX_BYTES, writer->header_bytes, &covered) ||
        !otrl_checked_add_size(covered, (size_t)record_bytes, &covered) ||
        !otrl_checked_add_size(covered, OTRL_TRAILER_BYTES, &total) ||
        (uint64_t)total > writer->context->local_max_tape_bytes) {
        return OTRL_E_LIMIT;
    }
    bytes = otrl_alloc(writer->context, total);
    if (bytes == NULL) {
        return OTRL_E_IO;
    }
    memset(bytes, 0, total);
    memcpy(bytes, "OTRLTAP\0", 8U);
    otrl_put_u16_le(bytes + 8U, OTRL_FORMAT_MAJOR);
    otrl_put_u16_le(bytes + 10U, OTRL_FORMAT_MINOR);
    bytes[12] = OTRL_BYTE_ORDER_LE;
    bytes[13] = OTRL_HASH_SHA256;
    otrl_put_u16_le(bytes + 14U, OTRL_PREFIX_BYTES);
    otrl_put_u32_le(bytes + 16U, writer->header_bytes);
    otrl_put_u32_le(bytes + 20U, writer->flags);
    otrl_put_u64_le(bytes + 24U, writer->count);
    otrl_put_u64_le(bytes + 32U, record_bytes);
    otrl_put_u64_le(bytes + 40U, max_step);
    otrl_put_u64_le(bytes + 48U, max_tick);
    memcpy(bytes + OTRL_PREFIX_BYTES, writer->header, writer->header_bytes);
    offset = OTRL_PREFIX_BYTES + writer->header_bytes;
    for (uint64_t i = 0U; i < writer->count; ++i) {
        const otrl_record_internal *record = &writer->records[i];
        otrl_put_u16_le(bytes + offset, record->type);
        otrl_put_u16_le(bytes + offset + 2U, record->version);
        otrl_put_u32_le(bytes + offset + 4U, record->flags);
        otrl_put_u64_le(bytes + offset + 8U, record->sequence);
        otrl_put_u64_le(bytes + offset + 16U, record->public_step);
        otrl_put_u64_le(bytes + offset + 24U, record->native_tick);
        otrl_put_u32_le(bytes + offset + 32U, record->payload_bytes);
        if (record->payload_bytes != 0U) {
            memcpy(bytes + offset + OTRL_RECORD_HEADER_BYTES, record->payload,
                   record->payload_bytes);
        }
        offset += record->padded_bytes;
    }
    memcpy(bytes + covered, "OTRLEND\0", 8U);
    otrl_put_u64_le(bytes + covered + 8U, writer->count);
    otrl_put_u64_le(bytes + covered + 16U, covered);
    status = otrl_sha256(bytes, covered, bytes + covered + 24U);
    if (status != OTRL_OK) {
        otrl_dealloc(writer->context, bytes);
        return status;
    }
    status = otrl_validate_bytes(writer->context, bytes, total, &validated, error);
    if (status != OTRL_OK) {
        otrl_dealloc(writer->context, bytes);
        return status;
    }
    otrl_tape_destroy(writer->context, validated);
    writer->finalized = 1;
    *out_bytes = bytes;
    *out_length = total;
    return OTRL_OK;
}

otrl_status otrl_writer_finalize_bytes(otrl_writer *writer,
                                       uint8_t **out_bytes,
                                       size_t *out_length,
                                       otrl_error *error)
{
    return otrl_serialize_tape(writer, out_bytes, out_length, error);
}

otrl_status otrl_writer_finalize_file(otrl_writer *writer, const char *path,
                                      otrl_error *error)
{
    uint8_t *bytes = NULL;
    size_t length = 0U;
    otrl_status status;
    if (path == NULL) {
        return OTRL_E_USAGE;
    }
    status = otrl_serialize_tape(writer, &bytes, &length, error);
    if (status != OTRL_OK) {
        return status;
    }
    status = otrl_write_atomic(path, bytes, length, error);
    otrl_dealloc(writer->context, bytes);
    return status;
}

void otrl_writer_destroy(otrl_writer *writer)
{
    if (writer != NULL) {
        otrl_context *context = writer->context;
        for (uint64_t i = 0U; i < writer->count; ++i) {
            otrl_dealloc(context, writer->records[i].payload);
        }
        otrl_dealloc(context, writer->records);
        otrl_dealloc(context, writer->header);
        otrl_dealloc(context, writer);
    }
}
