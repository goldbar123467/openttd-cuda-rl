/* SPDX-License-Identifier: GPL-2.0-only */
#include "internal.h"

#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define CHECK(condition) do { if (!(condition)) { \
    (void)fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__, __LINE__, \
                  #condition); return 1; } } while (0)

enum fault_kind {
    FAULT_NONE = 0,
    FAULT_WRITE_EINTR_SHORT,
    FAULT_FSYNC,
    FAULT_CLOSE,
    FAULT_LINK,
    FAULT_UNLINK
};

static enum fault_kind active_fault;
static unsigned int fault_calls;

ssize_t __real_write(int descriptor, const void *bytes, size_t length);
int __real_fsync(int descriptor);
int __real_close(int descriptor);
int __real_link(const char *old_path, const char *new_path);
int __real_unlink(const char *path);
ssize_t __wrap_write(int descriptor, const void *bytes, size_t length);
int __wrap_fsync(int descriptor);
int __wrap_close(int descriptor);
int __wrap_link(const char *old_path, const char *new_path);
int __wrap_unlink(const char *path);

ssize_t __wrap_write(int descriptor, const void *bytes, size_t length)
{
    if (active_fault == FAULT_WRITE_EINTR_SHORT) {
        ++fault_calls;
        if (fault_calls == 1U) {
            errno = EINTR;
            return -1;
        }
        if (length > 2U) {
            length = 2U;
        }
    }
    return __real_write(descriptor, bytes, length);
}

int __wrap_fsync(int descriptor)
{
    if (active_fault == FAULT_FSYNC && fault_calls++ == 0U) {
        errno = EIO;
        return -1;
    }
    return __real_fsync(descriptor);
}

int __wrap_close(int descriptor)
{
    if (active_fault == FAULT_CLOSE && fault_calls++ == 0U) {
        const int result = __real_close(descriptor);
        if (result != 0) {
            return result;
        }
        errno = EIO;
        return -1;
    }
    return __real_close(descriptor);
}

int __wrap_link(const char *old_path, const char *new_path)
{
    if (active_fault == FAULT_LINK && fault_calls++ == 0U) {
        errno = EIO;
        return -1;
    }
    return __real_link(old_path, new_path);
}

int __wrap_unlink(const char *path)
{
    if (active_fault == FAULT_UNLINK && fault_calls++ == 0U) {
        errno = EIO;
        return -1;
    }
    return __real_unlink(path);
}

static int directory_has_partial(const char *directory_path)
{
    DIR *directory = opendir(directory_path);
    struct dirent *entry;
    int found = 0;
    if (directory == NULL) {
        return 1;
    }
    while ((entry = readdir(directory)) != NULL) {
        if (strstr(entry->d_name, ".partial.") != NULL) {
            found = 1;
            break;
        }
    }
    (void)closedir(directory);
    return found;
}

static int read_matches(const char *path, const uint8_t *expected, size_t length)
{
    uint8_t actual[32];
    FILE *stream;
    size_t amount;
    if (length > sizeof(actual)) {
        return 0;
    }
    stream = fopen(path, "rb");
    if (stream == NULL) {
        return 0;
    }
    amount = fread(actual, 1U, sizeof(actual), stream);
    if (fclose(stream) != 0) {
        return 0;
    }
    return amount == length && memcmp(actual, expected, length) == 0;
}

static int run_failure(const char *directory_path, const char *output,
                       enum fault_kind fault, const uint8_t *bytes,
                       size_t length)
{
    otrl_error error;
    active_fault = fault;
    fault_calls = 0U;
    otrl_error_init(&error);
    CHECK(otrl_write_atomic(output, bytes, length, &error) == OTRL_E_IO);
    active_fault = FAULT_NONE;
    CHECK(access(output, F_OK) != 0);
    CHECK(!directory_has_partial(directory_path));
    return 0;
}

int main(void)
{
    char directory_template[] = "/tmp/p004-atomic-XXXXXX";
    char output[256];
    static const uint8_t bytes[] = {0x00U, 0x01U, 0x7fU, 0x80U, 0xffU};
    otrl_error error;
    FILE *existing;
    char *directory_path = mkdtemp(directory_template);
    CHECK(directory_path != NULL);
    CHECK(snprintf(output, sizeof(output), "%s/output.tape", directory_path) > 0);
    otrl_error_init(&error);
    CHECK(otrl_write_atomic(NULL, bytes, sizeof(bytes), &error) == OTRL_E_USAGE);

    active_fault = FAULT_WRITE_EINTR_SHORT;
    fault_calls = 0U;
    CHECK(otrl_write_atomic(output, bytes, sizeof(bytes), &error) == OTRL_OK);
    active_fault = FAULT_NONE;
    CHECK(read_matches(output, bytes, sizeof(bytes)));
    CHECK(!directory_has_partial(directory_path));

    existing = fopen(output, "wb");
    CHECK(existing != NULL);
    CHECK(fwrite("keep", 1U, 4U, existing) == 4U);
    CHECK(fclose(existing) == 0);
    CHECK(otrl_write_atomic(output, bytes, sizeof(bytes), &error) == OTRL_E_IO);
    CHECK(read_matches(output, (const uint8_t *)"keep", 4U));
    CHECK(!directory_has_partial(directory_path));
    CHECK(unlink(output) == 0);

    CHECK(run_failure(directory_path, output, FAULT_FSYNC, bytes,
                      sizeof(bytes)) == 0);
    CHECK(run_failure(directory_path, output, FAULT_CLOSE, bytes,
                      sizeof(bytes)) == 0);
    CHECK(run_failure(directory_path, output, FAULT_LINK, bytes,
                      sizeof(bytes)) == 0);
    CHECK(run_failure(directory_path, output, FAULT_UNLINK, bytes,
                      sizeof(bytes)) == 0);
    CHECK(rmdir(directory_path) == 0);
    return 0;
}
