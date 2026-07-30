/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OTRL_TAPE_FORMAT_H
#define OTRL_TAPE_FORMAT_H

#include <stddef.h>
#include <stdint.h>

#define OTRL_FORMAT_MAJOR UINT16_C(1)
#define OTRL_FORMAT_MINOR UINT16_C(0)
#define OTRL_BYTE_ORDER_LE UINT8_C(1)
#define OTRL_HASH_SHA256 UINT8_C(1)
#define OTRL_PREFIX_BYTES UINT16_C(64)
#define OTRL_RECORD_HEADER_BYTES UINT32_C(40)
#define OTRL_TRAILER_BYTES UINT32_C(64)
#define OTRL_PROJECTION_HEADER_BYTES UINT32_C(24)
#define OTRL_FIELD_HEADER_BYTES UINT32_C(16)
#define OTRL_SHA256_BYTES UINT32_C(32)

#define OTRL_MAX_HEADER_BYTES UINT32_C(1048576)
#define OTRL_MAX_RECORD_PAYLOAD_BYTES UINT32_C(67108864)
#define OTRL_MAX_RECORD_COUNT UINT64_C(50000000)
#define OTRL_MAX_TAPE_BYTES UINT64_C(1099511627776)
#define OTRL_MAX_FIELD_COUNT UINT32_C(10000000)
#define OTRL_MAX_FIELD_BYTES UINT32_C(67108864)
#define OTRL_MAX_DIAGNOSTIC_STRING_BYTES UINT32_C(1048576)
#define OTRL_MAX_JSON_DEPTH UINT32_C(64)
#define OTRL_MAX_COMMAND_COUNT UINT32_C(1000000)


#define OTRL_PREFIX_FLAG_PARTIAL UINT32_C(1)
#define OTRL_PREFIX_FLAG_OPTIONAL_DIAGNOSTICS UINT32_C(2)
#define OTRL_PREFIX_KNOWN_FLAGS UINT32_C(3)
#define OTRL_PREFIX_REQUIRED_FLAG_MASK UINT32_C(0xffff0000)
#define OTRL_RECORD_FLAG_REQUIRED UINT32_C(1)
#define OTRL_RECORD_KNOWN_FLAGS UINT32_C(1)

typedef enum otrl_record_type {
    OTRL_RECORD_REPLAY_START = 1,
    OTRL_RECORD_COMMAND_INTENT = 2,
    OTRL_RECORD_COMMAND_TEST_RESULT = 3,
    OTRL_RECORD_COMMAND_EXEC_RESULT = 4,
    OTRL_RECORD_AUTHORITATIVE_PROJECTION = 5,
    OTRL_RECORD_NAMED_CHECKPOINT = 6,
    OTRL_RECORD_RNG_DRAW_DIAGNOSTIC = 7,
    OTRL_RECORD_ROUTE_DIAGNOSTIC = 8,
    OTRL_RECORD_CARGO_DIAGNOSTIC = 9,
    OTRL_RECORD_TRACE_WARNING = 10,
    OTRL_RECORD_TERMINAL = 11
} otrl_record_type;

typedef enum otrl_value_type {
    OTRL_VALUE_U8 = 1,
    OTRL_VALUE_U16 = 2,
    OTRL_VALUE_U32 = 3,
    OTRL_VALUE_U64 = 4,
    OTRL_VALUE_I8 = 5,
    OTRL_VALUE_I16 = 6,
    OTRL_VALUE_I32 = 7,
    OTRL_VALUE_I64 = 8,
    OTRL_VALUE_BYTES = 9,
    OTRL_VALUE_STABLE_ID = 10,
    OTRL_VALUE_BITSET = 11,
    OTRL_VALUE_DIAGNOSTIC_UTF8 = 12
} otrl_value_type;

static inline uint16_t otrl_get_u16_le(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8U));
}

static inline uint32_t otrl_get_u32_le(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8U) |
           ((uint32_t)p[2] << 16U) | ((uint32_t)p[3] << 24U);
}

static inline uint64_t otrl_get_u64_le(const uint8_t *p)
{
    return (uint64_t)otrl_get_u32_le(p) |
           ((uint64_t)otrl_get_u32_le(p + 4U) << 32U);
}

static inline void otrl_put_u16_le(uint8_t *p, uint16_t value)
{
    p[0] = (uint8_t)(value & UINT16_C(0xff));
    p[1] = (uint8_t)((value >> 8U) & UINT16_C(0xff));
}

static inline void otrl_put_u32_le(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)(value & UINT32_C(0xff));
    p[1] = (uint8_t)((value >> 8U) & UINT32_C(0xff));
    p[2] = (uint8_t)((value >> 16U) & UINT32_C(0xff));
    p[3] = (uint8_t)((value >> 24U) & UINT32_C(0xff));
}

static inline void otrl_put_u64_le(uint8_t *p, uint64_t value)
{
    otrl_put_u32_le(p, (uint32_t)(value & UINT64_C(0xffffffff)));
    otrl_put_u32_le(p + 4U, (uint32_t)(value >> 32U));
}

#endif
