/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { if (!(condition)) { \
    (void)fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__, __LINE__, \
                  #condition); return 1; } } while (0)

static int hex_equal(const uint8_t *bytes, size_t length, const char *hex)
{
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0U; i < length; ++i) {
        if (hex[i * 2U] != digits[bytes[i] >> 4U] ||
            hex[i * 2U + 1U] != digits[bytes[i] & 15U]) return 0;
    }
    return hex[length * 2U] == '\0';
}

int main(void)
{
    uint8_t bytes[8];
    size_t value = 0U;
    uint8_t digest[32];
    uint8_t *million;
    int fallback = 0;
    static const uint8_t monotone[] = {0, 0, 1, 1};
    static const uint8_t nonmonotone[] = {0, 1, 0, 1};
    otrl_context_options options;
    otrl_context *context = NULL;
    otrl_error error;
    for (unsigned int status = 0U; status <= (unsigned int)OTRL_E_INTERNAL; ++status) {
        CHECK(strcmp(otrl_status_string((otrl_status)status), "unknown_status") != 0);
    }
    CHECK(strcmp(otrl_status_string((otrl_status)999), "unknown_status") == 0);
    CHECK(otrl_checked_add_size(1U, 2U, &value) && value == 3U);
    CHECK(!otrl_checked_add_size(SIZE_MAX, 1U, &value));
    CHECK(otrl_checked_mul_size(3U, 7U, &value) && value == 21U);
    CHECK(!otrl_checked_mul_size(SIZE_MAX, 2U, &value));
    for (size_t i = 0U; i < 8U; ++i) {
        CHECK(otrl_checked_align8_size(i, &value) && value == (i == 0U ? 0U : 8U));
    }
    otrl_put_u16_le(bytes, UINT16_C(0x1234));
    CHECK(bytes[0] == UINT8_C(0x34) && bytes[1] == UINT8_C(0x12));
    otrl_put_u32_le(bytes, UINT32_C(0x12345678));
    CHECK(hex_equal(bytes, 4U, "78563412"));
    otrl_put_u64_le(bytes, UINT64_C(0x0123456789abcdef));
    CHECK(hex_equal(bytes, 8U, "efcdab8967452301"));
    CHECK(otrl_sha256((const uint8_t *)"abc", 3U, digest) == OTRL_OK);
    CHECK(hex_equal(digest, 32U,
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
    million = malloc(1000000U);
    CHECK(million != NULL);
    memset(million, 'a', 1000000U);
    CHECK(otrl_sha256(million, 1000000U, digest) == OTRL_OK);
    free(million);
    CHECK(hex_equal(digest, 32U,
        "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"));
    CHECK(otrl_find_first_true(monotone, sizeof(monotone), &fallback) == 2U);
    CHECK(fallback == 0);
    CHECK(otrl_find_first_true(nonmonotone, sizeof(nonmonotone), &fallback) == 1U);
    CHECK(fallback == 1);
    memset(&options, 0, sizeof(options));
    options.size = (uint32_t)sizeof(options);
    options.version = OTRL_ABI_VERSION;
    options.local_max_tape_bytes = OTRL_MAX_TAPE_BYTES + UINT64_C(1);
    otrl_error_init(&error);
    CHECK(otrl_context_create(&options, &context, &error) == OTRL_E_LIMIT);
    CHECK(context == NULL);
    options.local_max_tape_bytes = OTRL_MAX_TAPE_BYTES;
    options.local_max_record_count = OTRL_MAX_RECORD_COUNT + UINT64_C(1);
    CHECK(otrl_context_create(&options, &context, &error) == OTRL_E_LIMIT);
    CHECK(context == NULL);
    options.local_max_record_count = OTRL_MAX_RECORD_COUNT;
    CHECK(otrl_context_create(&options, &context, &error) == OTRL_OK);
    otrl_context_destroy(context);
    return 0;
}
