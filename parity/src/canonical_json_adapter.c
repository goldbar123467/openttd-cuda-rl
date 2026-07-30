/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"
#include "openttd_rl_parity/field_schema.h"

#include <ctype.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

typedef struct json_cursor {
    const uint8_t *bytes;
    size_t length;
    size_t offset;
    uint32_t depth;
} json_cursor;

static int is_continuation(uint8_t byte)
{
    return (byte & UINT8_C(0xc0)) == UINT8_C(0x80);
}

int otrl_utf8_valid(const uint8_t *bytes, size_t length)
{
    size_t i = 0U;
    while (i < length) {
        const uint8_t first = bytes[i];
        uint32_t codepoint;
        size_t count;
        if (first <= UINT8_C(0x7f)) {
            ++i;
            continue;
        }
        if (first >= UINT8_C(0xc2) && first <= UINT8_C(0xdf)) {
            count = 2U;
            codepoint = (uint32_t)(first & UINT8_C(0x1f));
        } else if (first >= UINT8_C(0xe0) && first <= UINT8_C(0xef)) {
            count = 3U;
            codepoint = (uint32_t)(first & UINT8_C(0x0f));
        } else if (first >= UINT8_C(0xf0) && first <= UINT8_C(0xf4)) {
            count = 4U;
            codepoint = (uint32_t)(first & UINT8_C(0x07));
        } else {
            return 0;
        }
        if (count > length - i) {
            return 0;
        }
        for (size_t j = 1U; j < count; ++j) {
            if (!is_continuation(bytes[i + j])) {
                return 0;
            }
            codepoint = (codepoint << 6U) |
                        (uint32_t)(bytes[i + j] & UINT8_C(0x3f));
        }
        if ((count == 3U && codepoint < UINT32_C(0x800)) ||
            (count == 4U && codepoint < UINT32_C(0x10000)) ||
            codepoint > UINT32_C(0x10ffff) ||
            (codepoint >= UINT32_C(0xd800) && codepoint <= UINT32_C(0xdfff))) {
            return 0;
        }
        i += count;
    }
    return 1;
}

static int hex_digit(uint8_t byte)
{
    return (byte >= (uint8_t)'0' && byte <= (uint8_t)'9') ||
           (byte >= (uint8_t)'a' && byte <= (uint8_t)'f');
}

static otrl_status parse_string(json_cursor *cursor, size_t *start, size_t *end,
                                otrl_error *error)
{
    if (cursor->offset >= cursor->length || cursor->bytes[cursor->offset] != '"') {
        otrl_set_error(error, OTRL_E_CANONICAL, cursor->offset, UINT64_MAX, 0U,
                       0U, 0U, "expected JSON string");
        return OTRL_E_CANONICAL;
    }
    ++cursor->offset;
    *start = cursor->offset;
    while (cursor->offset < cursor->length) {
        const uint8_t byte = cursor->bytes[cursor->offset++];
        if (byte == '"') {
            *end = cursor->offset - 1U;
            return OTRL_OK;
        }
        if (byte < UINT8_C(0x20)) {
            otrl_set_error(error, OTRL_E_CANONICAL, cursor->offset - 1U,
                           UINT64_MAX, 0U, 0U, 0U,
                           "unescaped control byte in JSON string");
            return OTRL_E_CANONICAL;
        }
        if (byte == '\\') {
            uint8_t escaped;
            if (cursor->offset >= cursor->length) {
                return OTRL_E_TRUNCATED;
            }
            escaped = cursor->bytes[cursor->offset++];
            if (escaped == '"' || escaped == '\\' || escaped == 'b' ||
                escaped == 'f' || escaped == 'n' || escaped == 'r' ||
                escaped == 't') {
                continue;
            }
            if (escaped == 'u') {
                size_t j;
                unsigned int code_unit = 0U;
                if (cursor->length - cursor->offset < 4U) {
                    return OTRL_E_TRUNCATED;
                }
                for (j = 0U; j < 4U; ++j) {
                    if (!hex_digit(cursor->bytes[cursor->offset + j])) {
                        otrl_set_error(error, OTRL_E_CANONICAL,
                                       cursor->offset + j, UINT64_MAX, 0U, 0U,
                                       0U, "noncanonical unicode escape");
                        return OTRL_E_CANONICAL;
                    }
                    code_unit = code_unit * 16U +
                        (unsigned int)(cursor->bytes[cursor->offset + j] <= '9' ?
                        cursor->bytes[cursor->offset + j] - '0' :
                        cursor->bytes[cursor->offset + j] - 'a' + 10);
                }
                cursor->offset += 4U;
                if (code_unit >= 0x20U || code_unit == 0x08U ||
                    code_unit == 0x09U || code_unit == 0x0aU ||
                    code_unit == 0x0cU || code_unit == 0x0dU) {
                    otrl_set_error(error, OTRL_E_CANONICAL,
                                   cursor->offset - 4U, UINT64_MAX, 0U, 0U,
                                   0U, "unicode escape is not shortest JCS form");
                    return OTRL_E_CANONICAL;
                }
                continue;
            }
            otrl_set_error(error, OTRL_E_CANONICAL, cursor->offset - 1U,
                           UINT64_MAX, 0U, 0U, 0U,
                           "noncanonical JSON escape");
            return OTRL_E_CANONICAL;
        }
    }
    return OTRL_E_TRUNCATED;
}

static int raw_key_order(const uint8_t *left, size_t left_length,
                         const uint8_t *right, size_t right_length)
{
    const size_t common = left_length < right_length ? left_length : right_length;
    const int result = memcmp(left, right, common);
    if (result != 0) {
        return result;
    }
    return left_length < right_length ? -1 : (left_length > right_length ? 1 : 0);
}

static otrl_status parse_value(json_cursor *cursor, otrl_error *error);

static otrl_status parse_array(json_cursor *cursor, otrl_error *error)
{
    otrl_status status;
    ++cursor->offset;
    if (++cursor->depth > OTRL_MAX_JSON_DEPTH) {
        return OTRL_E_LIMIT;
    }
    if (cursor->offset < cursor->length && cursor->bytes[cursor->offset] == ']') {
        ++cursor->offset;
        --cursor->depth;
        return OTRL_OK;
    }
    for (;;) {
        status = parse_value(cursor, error);
        if (status != OTRL_OK) {
            return status;
        }
        if (cursor->offset >= cursor->length) {
            return OTRL_E_TRUNCATED;
        }
        if (cursor->bytes[cursor->offset] == ']') {
            ++cursor->offset;
            --cursor->depth;
            return OTRL_OK;
        }
        if (cursor->bytes[cursor->offset++] != ',') {
            return OTRL_E_CANONICAL;
        }
    }
}

static otrl_status parse_object(json_cursor *cursor, otrl_error *error)
{
    size_t previous_start = 0U;
    size_t previous_end = 0U;
    int have_previous = 0;
    ++cursor->offset;
    if (++cursor->depth > OTRL_MAX_JSON_DEPTH) {
        return OTRL_E_LIMIT;
    }
    if (cursor->offset < cursor->length && cursor->bytes[cursor->offset] == '}') {
        ++cursor->offset;
        --cursor->depth;
        return OTRL_OK;
    }
    for (;;) {
        size_t start;
        size_t end;
        otrl_status status = parse_string(cursor, &start, &end, error);
        if (status != OTRL_OK) {
            return status;
        }
        if (have_previous &&
            raw_key_order(cursor->bytes + previous_start,
                          previous_end - previous_start,
                          cursor->bytes + start, end - start) >= 0) {
            otrl_set_error(error, OTRL_E_CANONICAL, start, UINT64_MAX, 0U, 0U,
                           0U, "object keys are duplicate or not sorted");
            return OTRL_E_CANONICAL;
        }
        previous_start = start;
        previous_end = end;
        have_previous = 1;
        if (cursor->offset >= cursor->length ||
            cursor->bytes[cursor->offset++] != ':') {
            return OTRL_E_CANONICAL;
        }
        status = parse_value(cursor, error);
        if (status != OTRL_OK) {
            return status;
        }
        if (cursor->offset >= cursor->length) {
            return OTRL_E_TRUNCATED;
        }
        if (cursor->bytes[cursor->offset] == '}') {
            ++cursor->offset;
            --cursor->depth;
            return OTRL_OK;
        }
        if (cursor->bytes[cursor->offset++] != ',') {
            return OTRL_E_CANONICAL;
        }
    }
}

static otrl_status parse_number(json_cursor *cursor)
{
    size_t start = cursor->offset;
    uint64_t value = 0U;
    int negative = 0;
    if (cursor->bytes[cursor->offset] == '-') {
        negative = 1;
        ++cursor->offset;
        if (cursor->offset >= cursor->length) return OTRL_E_TRUNCATED;
    }
    if (cursor->bytes[cursor->offset] == '0') {
        ++cursor->offset;
        if (cursor->offset < cursor->length &&
            isdigit((int)cursor->bytes[cursor->offset]) != 0) {
            return OTRL_E_CANONICAL;
        }
    } else {
        if (cursor->bytes[cursor->offset] < '1' ||
            cursor->bytes[cursor->offset] > '9') {
            return OTRL_E_CANONICAL;
        }
        while (cursor->offset < cursor->length &&
               cursor->bytes[cursor->offset] >= '0' &&
               cursor->bytes[cursor->offset] <= '9') {
            const uint64_t digit = (uint64_t)(cursor->bytes[cursor->offset] - '0');
            if (value > (UINT64_C(9007199254740991) - digit) / UINT64_C(10)) {
                return OTRL_E_SCHEMA;
            }
            value = value * UINT64_C(10) + digit;
            ++cursor->offset;
        }
    }
    if (cursor->offset < cursor->length &&
        (cursor->bytes[cursor->offset] == '.' ||
         cursor->bytes[cursor->offset] == 'e' ||
         cursor->bytes[cursor->offset] == 'E')) {
        return OTRL_E_SCHEMA;
    }
    return cursor->offset > start + (size_t)negative ? OTRL_OK : OTRL_E_CANONICAL;
}

static otrl_status parse_value(json_cursor *cursor, otrl_error *error)
{
    if (cursor->offset >= cursor->length) {
        return OTRL_E_TRUNCATED;
    }
    switch (cursor->bytes[cursor->offset]) {
    case '{': return parse_object(cursor, error);
    case '[': return parse_array(cursor, error);
    case '"': {
        size_t start;
        size_t end;
        return parse_string(cursor, &start, &end, error);
    }
    case 't':
        if (cursor->length - cursor->offset >= 4U &&
            memcmp(cursor->bytes + cursor->offset, "true", 4U) == 0) {
            cursor->offset += 4U;
            return OTRL_OK;
        }
        return OTRL_E_CANONICAL;
    case 'f':
        if (cursor->length - cursor->offset >= 5U &&
            memcmp(cursor->bytes + cursor->offset, "false", 5U) == 0) {
            cursor->offset += 5U;
            return OTRL_OK;
        }
        return OTRL_E_CANONICAL;
    case 'n':
        if (cursor->length - cursor->offset >= 4U &&
            memcmp(cursor->bytes + cursor->offset, "null", 4U) == 0) {
            cursor->offset += 4U;
            return OTRL_OK;
        }
        return OTRL_E_CANONICAL;
    default: return parse_number(cursor);
    }
}

static int contains_literal(const uint8_t *bytes, size_t length,
                            const char *literal)
{
    const size_t literal_length = strlen(literal);
    size_t i;
    if (literal_length > length) {
        return 0;
    }
    for (i = 0U; i <= length - literal_length; ++i) {
        if (memcmp(bytes + i, literal, literal_length) == 0) {
            return 1;
        }
    }
    return 0;
}

static int object_exact_keys(const uint8_t *bytes, size_t length,
                             const char *marker,
                             const char *const *keys, size_t key_count)
{
    const size_t marker_length = strlen(marker);
    size_t object_offset = SIZE_MAX;
    json_cursor cursor;
    size_t i;
    for (i = 0U; i + marker_length < length; ++i) {
        if (memcmp(bytes + i, marker, marker_length) == 0 &&
            bytes[i + marker_length] == '{') {
            object_offset = i + marker_length;
            break;
        }
    }
    if (object_offset == SIZE_MAX) {
        return 0;
    }
    cursor.bytes = bytes;
    cursor.length = length;
    cursor.offset = object_offset + 1U;
    cursor.depth = 1U;
    for (i = 0U; i < key_count; ++i) {
        size_t start;
        size_t end;
        if (parse_string(&cursor, &start, &end, NULL) != OTRL_OK ||
            end - start != strlen(keys[i]) ||
            memcmp(bytes + start, keys[i], end - start) != 0 ||
            cursor.offset >= length || bytes[cursor.offset++] != ':' ||
            parse_value(&cursor, NULL) != OTRL_OK) {
            return 0;
        }
        if (i + 1U < key_count) {
            if (cursor.offset >= length || bytes[cursor.offset++] != ',') {
                return 0;
            }
        }
    }
    return cursor.offset < length && bytes[cursor.offset] == '}';
}

static int required_hex_value(const uint8_t *bytes, size_t length,
                              const char *key, size_t digits)
{
    char pattern[80];
    size_t pattern_length;
    size_t i;
    int written = snprintf(pattern, sizeof(pattern), "\"%s\":\"", key);
    if (written < 0 || (size_t)written >= sizeof(pattern)) {
        return 0;
    }
    pattern_length = (size_t)written;
    for (i = 0U; i + pattern_length + digits < length; ++i) {
        if (memcmp(bytes + i, pattern, pattern_length) == 0) {
            size_t j;
            for (j = 0U; j < digits; ++j) {
                if (!hex_digit(bytes[i + pattern_length + j])) {
                    return 0;
                }
            }
            return bytes[i + pattern_length + digits] == '"';
        }
    }
    return 0;
}

static int marker_offset(const uint8_t *bytes, size_t length,
                         const char *marker, size_t *value_offset)
{
    const size_t marker_length = strlen(marker);
    if (marker_length > length) return 0;
    for (size_t i = 0U; i <= length - marker_length; ++i) {
        if (memcmp(bytes + i, marker, marker_length) == 0) {
            *value_offset = i + marker_length;
            return 1;
        }
    }
    return 0;
}

static size_t canonical_string_characters(const uint8_t *bytes,
                                          size_t start, size_t end)
{
    size_t characters = 0U;
    for (size_t i = start; i < end; ++characters) {
        if (bytes[i] == '\\') {
            i += bytes[i + 1U] == 'u' ? 6U : 2U;
        } else {
            ++i;
            while (i < end && is_continuation(bytes[i])) ++i;
        }
    }
    return characters;
}

static int validate_bounded_string(const uint8_t *bytes, size_t length,
                                   const char *marker, size_t minimum,
                                   size_t maximum)
{
    json_cursor cursor = {bytes, length, 0U, 0U};
    size_t start;
    size_t end;
    size_t count;
    if (!marker_offset(bytes, length, marker, &cursor.offset) ||
        parse_string(&cursor, &start, &end, NULL) != OTRL_OK) return 0;
    count = canonical_string_characters(bytes, start, end);
    return count >= minimum && count <= maximum;
}

static int parse_uint_at(const uint8_t *bytes, size_t length, size_t *offset,
                         uint64_t maximum)
{
    uint64_t value = 0U;
    size_t start = *offset;
    if (start >= length || bytes[start] < '0' || bytes[start] > '9') return 0;
    if (bytes[start] == '0' && start + 1U < length &&
        bytes[start + 1U] >= '0' && bytes[start + 1U] <= '9') return 0;
    while (*offset < length && bytes[*offset] >= '0' && bytes[*offset] <= '9') {
        const uint64_t digit = (uint64_t)(bytes[*offset] - '0');
        if (value > (maximum - digit) / UINT64_C(10)) return 0;
        value = value * UINT64_C(10) + digit;
        ++*offset;
    }
    return *offset > start;
}

static int validate_uint_member(const uint8_t *bytes, size_t length,
                                const char *marker, uint64_t maximum)
{
    size_t offset;
    if (!marker_offset(bytes, length, marker, &offset) ||
        !parse_uint_at(bytes, length, &offset, maximum)) return 0;
    return offset < length && (bytes[offset] == ',' || bytes[offset] == '}');
}

static int validate_diagnostic_features(const uint8_t *bytes, size_t length)
{
    size_t offset;
    size_t starts[32];
    size_t ends[32];
    size_t count = 0U;
    json_cursor cursor = {bytes, length, 0U, 0U};
    if (!marker_offset(bytes, length, "\"diagnostic_features\":", &offset) ||
        offset >= length || bytes[offset++] != '[') return 0;
    if (offset < length && bytes[offset] == ']') return 1;
    cursor.offset = offset;
    for (;;) {
        size_t start;
        size_t end;
        if (count == 32U || parse_string(&cursor, &start, &end, NULL) != OTRL_OK ||
            canonical_string_characters(bytes, start, end) == 0U ||
            canonical_string_characters(bytes, start, end) > 128U) return 0;
        for (size_t i = 0U; i < count; ++i) {
            if (ends[i] - starts[i] == end - start &&
                memcmp(bytes + starts[i], bytes + start, end - start) == 0) return 0;
        }
        starts[count] = start;
        ends[count++] = end;
        if (cursor.offset >= length) return 0;
        if (bytes[cursor.offset] == ']') return 1;
        if (bytes[cursor.offset++] != ',') return 0;
    }
}

static int valid_timer_key(const uint8_t *bytes, size_t start, size_t end)
{
    if (end == start || end - start > 64U ||
        bytes[start] < 'a' || bytes[start] > 'z') return 0;
    for (size_t i = start + 1U; i < end; ++i) {
        if (!((bytes[i] >= 'a' && bytes[i] <= 'z') ||
              (bytes[i] >= '0' && bytes[i] <= '9') || bytes[i] == '_')) return 0;
    }
    return 1;
}

static int validate_timers(const uint8_t *bytes, size_t length)
{
    size_t offset;
    size_t count = 0U;
    json_cursor cursor = {bytes, length, 0U, 0U};
    if (!marker_offset(bytes, length, "\"timers\":", &offset) ||
        offset >= length || bytes[offset++] != '{') return 0;
    cursor.offset = offset;
    while (cursor.offset < length && bytes[cursor.offset] != '}') {
        size_t start;
        size_t end;
        if (++count > 64U || parse_string(&cursor, &start, &end, NULL) != OTRL_OK ||
            !valid_timer_key(bytes, start, end) || cursor.offset >= length ||
            bytes[cursor.offset++] != ':' ||
            !parse_uint_at(bytes, length, &cursor.offset,
                           UINT64_C(9007199254740991))) return 0;
        if (cursor.offset >= length) return 0;
        if (bytes[cursor.offset] == '}') break;
        if (bytes[cursor.offset++] != ',') return 0;
    }
    return count != 0U && cursor.offset < length && bytes[cursor.offset] == '}';
}

otrl_status otrl_validate_canonical_json(const uint8_t *bytes, size_t length,
                                         otrl_error *error)
{
    json_cursor cursor;
    otrl_status status;
    if (bytes == NULL || length == 0U) return OTRL_E_SCHEMA;
    if (length > OTRL_MAX_RECORD_PAYLOAD_BYTES) return OTRL_E_LIMIT;
    if (length >= 3U && bytes[0] == UINT8_C(0xef) && bytes[1] == UINT8_C(0xbb) &&
        bytes[2] == UINT8_C(0xbf)) return OTRL_E_CANONICAL;
    if (!otrl_utf8_valid(bytes, length)) return OTRL_E_CANONICAL;
    cursor.bytes = bytes;
    cursor.length = length;
    cursor.offset = 0U;
    cursor.depth = 0U;
    status = parse_value(&cursor, error);
    if (status != OTRL_OK) {
        otrl_set_error(error, status, cursor.offset, UINT64_MAX, 0U, 0U, 0U,
                       "invalid canonical JSON: %s", otrl_status_string(status));
        return status;
    }
    return cursor.offset == length ? OTRL_OK : OTRL_E_CANONICAL;
}

otrl_status otrl_validate_canonical_header(const uint8_t *bytes, size_t length,
                                           otrl_error *error)
{
    static const char *const top_keys[] = {
        "backend_label", "diagnostic_features", "format", "identity",
        "initial", "limits", "projection_policy"
    };
    static const char *const identity_keys[] = {
        "build_sha256", "command_input_sha256", "command_schema_sha256",
        "content_sha256", "executable_sha256", "field_schema_sha256",
        "fixture_sha256", "instrumentation_sha256", "newgrfs",
        "settings_sha256", "source_commit"
    };
    static const char *const initial_keys[] = {
        "calendar_date", "calendar_fraction", "economy_date",
        "economy_fraction", "gameplay_rng_state", "interactive_rng_state",
        "native_tick", "public_step", "timers"
    };
    static const char *const digest_keys[] = {
        "build_sha256", "command_input_sha256", "command_schema_sha256",
        "content_sha256", "executable_sha256", "field_schema_sha256",
        "fixture_sha256", "instrumentation_sha256", "settings_sha256"
    };
    size_t i;
    otrl_status status;
    status = otrl_validate_canonical_json(bytes, length, error);
    if (status != OTRL_OK) return status;
    if (bytes[0] != '{') {
        return OTRL_E_CANONICAL;
    }
    if (!object_exact_keys(bytes, length, "", top_keys,
                           sizeof(top_keys) / sizeof(top_keys[0])) ||
        !object_exact_keys(bytes, length, "\"identity\":", identity_keys,
                           sizeof(identity_keys) / sizeof(identity_keys[0])) ||
        !object_exact_keys(bytes, length, "\"initial\":", initial_keys,
                           sizeof(initial_keys) / sizeof(initial_keys[0])) ||
        !contains_literal(bytes, length, "\"format\":{\"major\":1,\"minor\":0}") ||
        !contains_literal(bytes, length,
            "\"limits\":{\"command_count\":1000000,\"field_bytes\":67108864,"
            "\"field_count\":10000000,\"header_bytes\":1048576,"
            "\"record_count\":50000000,\"record_payload_bytes\":67108864,"
            "\"tape_bytes\":1099511627776}") ||
        !contains_literal(bytes, length, "\"projection_policy\":\"complete\"") ||
        !required_hex_value(bytes, length, "source_commit", 40U) ||
        !required_hex_value(bytes, length, "gameplay_rng_state", 16U) ||
        !required_hex_value(bytes, length, "interactive_rng_state", 16U) ||
        !contains_literal(bytes, length, "\"field_schema_sha256\":\""
                          OTRL_FIELD_SCHEMA_SHA256 "\"") ||
        contains_literal(bytes, length, "\"timers\":{}") ||
        !validate_bounded_string(bytes, length, "\"backend_label\":", 1U, 128U) ||
        !validate_diagnostic_features(bytes, length) ||
        !validate_uint_member(bytes, length, "\"calendar_date\":", UINT32_MAX) ||
        !validate_uint_member(bytes, length, "\"calendar_fraction\":", UINT32_MAX) ||
        !validate_uint_member(bytes, length, "\"economy_date\":", UINT32_MAX) ||
        !validate_uint_member(bytes, length, "\"economy_fraction\":", UINT32_MAX) ||
        !validate_uint_member(bytes, length, "\"native_tick\":",
                              UINT64_C(9007199254740991)) ||
        !validate_uint_member(bytes, length, "\"public_step\":",
                              UINT64_C(9007199254740991)) ||
        !validate_timers(bytes, length)) {
        return OTRL_E_SCHEMA;
    }
    for (i = 0U; i < sizeof(digest_keys) / sizeof(digest_keys[0]); ++i) {
        if (!required_hex_value(bytes, length, digest_keys[i], 64U)) {
            return OTRL_E_SCHEMA;
        }
    }
    if ((contains_literal(bytes, length, "\"newgrfs\":[") &&
         !contains_literal(bytes, length, "\"newgrfs\":[]")) ||
        contains_literal(bytes, length, "\"calendar_date\":-") ||
        contains_literal(bytes, length, "\"calendar_fraction\":-") ||
        contains_literal(bytes, length, "\"economy_date\":-") ||
        contains_literal(bytes, length, "\"economy_fraction\":-") ||
        contains_literal(bytes, length, "\"native_tick\":-") ||
        contains_literal(bytes, length, "\"public_step\":-")) {
        return OTRL_E_SCHEMA;
    }
    if (contains_literal(bytes, length, "\"identity\":{\"/") ||
        contains_literal(bytes, length, "_TOKEN") ||
        contains_literal(bytes, length, "SECRET") ||
        contains_literal(bytes, length, "PASSWORD")) {
        return OTRL_E_SCHEMA;
    }
    return OTRL_OK;
}
