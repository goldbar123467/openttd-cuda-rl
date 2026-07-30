/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"

#include <openssl/evp.h>
#include <sys/mman.h>

otrl_status otrl_sha256(const uint8_t *bytes, size_t length, uint8_t digest[32])
{
    EVP_MD_CTX *context;
    unsigned int digest_length = 0U;
    if ((bytes == NULL && length != 0U) || digest == NULL) {
        return OTRL_E_USAGE;
    }
    context = EVP_MD_CTX_new();
    if (context == NULL) {
        return OTRL_E_INTERNAL;
    }
    if (EVP_DigestInit_ex(context, EVP_sha256(), NULL) != 1 ||
        (length != 0U && EVP_DigestUpdate(context, bytes, length) != 1) ||
        EVP_DigestFinal_ex(context, digest, &digest_length) != 1 ||
        digest_length != 32U) {
        EVP_MD_CTX_free(context);
        return OTRL_E_INTERNAL;
    }
    EVP_MD_CTX_free(context);
    return OTRL_OK;
}

otrl_status otrl_sha256_mapped(const uint8_t *bytes, size_t length,
                               uint8_t digest[32])
{
    EVP_MD_CTX *context;
    unsigned int digest_length = 0U;
    size_t offset = 0U;
    const size_t chunk_capacity = 1024U * 1024U;
    if ((bytes == NULL && length != 0U) || digest == NULL) return OTRL_E_USAGE;
    context = EVP_MD_CTX_new();
    if (context == NULL || EVP_DigestInit_ex(context, EVP_sha256(), NULL) != 1) {
        EVP_MD_CTX_free(context);
        return OTRL_E_INTERNAL;
    }
    while (offset < length) {
        const size_t chunk = length - offset < chunk_capacity ?
                             length - offset : chunk_capacity;
        if (EVP_DigestUpdate(context, bytes + offset, chunk) != 1) {
            EVP_MD_CTX_free(context);
            return OTRL_E_INTERNAL;
        }
#ifdef MADV_DONTNEED
        (void)madvise((void *)(uintptr_t)(bytes + offset), chunk, MADV_DONTNEED);
#endif
        offset += chunk;
    }
    if (EVP_DigestFinal_ex(context, digest, &digest_length) != 1 ||
        digest_length != 32U) {
        EVP_MD_CTX_free(context);
        return OTRL_E_INTERNAL;
    }
    EVP_MD_CTX_free(context);
    return OTRL_OK;
}
