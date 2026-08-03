#include "openttd_rl/v2/m23_golden.h"

#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <openssl/evp.h>
#include <span>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace openttd_rl::v2 {

namespace {

constexpr std::array<std::uint8_t, 8> kMagic = {'M', '2', '3', 'G', 'L', 'D', '0', '1'};
constexpr std::uint32_t kVersion = 1;
constexpr std::uint32_t kCasesPerArchitecture = 24;
constexpr std::uint32_t kFeatureCount = 32;
constexpr std::uint32_t kProgramCount = 17;
constexpr std::uint32_t kHiddenCount = 256;
constexpr std::string_view kSeedDomain = "openttd-rl-v2-m23-golden-v1";
constexpr std::size_t kMaximumGoldenBytes = 64U * 1024U * 1024U;

void require(bool condition, const char *message)
{
    if (!condition) throw std::invalid_argument(message);
}

[[nodiscard]] std::uint32_t derived_seed(std::uint32_t ordinal)
{
    const auto identity = std::string(kSeedDomain) + ':' + std::to_string(ordinal);
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
    unsigned int length = 0;
    auto *context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("cannot allocate M23 seed SHA-256 context");
    const bool success = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, identity.data(), identity.size()) == 1 &&
        EVP_DigestFinal_ex(context, digest.data(), &length) == 1;
    EVP_MD_CTX_free(context);
    if (!success || length != 32) throw std::runtime_error("cannot derive M23 golden seed");
    return ((static_cast<std::uint32_t>(digest[0]) << 24U) |
            (static_cast<std::uint32_t>(digest[1]) << 16U) |
            (static_cast<std::uint32_t>(digest[2]) << 8U) |
            static_cast<std::uint32_t>(digest[3])) & UINT32_C(0x7fffffff);
}

[[nodiscard]] std::uint64_t next_random(std::uint64_t &state) noexcept
{
    state ^= state >> 12U;
    state ^= state << 25U;
    state ^= state >> 27U;
    return state * UINT64_C(2685821657736338717);
}

[[nodiscard]] float unit_random(std::uint64_t &state) noexcept
{
    const auto bits = static_cast<std::uint32_t>(next_random(state) >> 40U);
    return static_cast<float>(bits) / 16777215.0F;
}

[[nodiscard]] std::uint8_t active_program(std::uint8_t mode, std::uint32_t selector)
{
    constexpr std::array<std::array<std::uint8_t, 5>, 7> programs = {{
        {{1, 2, 1, 2, 1}},
        {{3, 4, 3, 4, 3}},
        {{5, 6, 5, 6, 5}},
        {{7, 8, 7, 8, 7}},
        {{9, 10, 9, 10, 9}},
        {{11, 11, 11, 11, 11}},
        {{12, 13, 14, 15, 16}},
    }};
    return programs[mode][selector % programs[mode].size()];
}

void fill_row(M23GoldenCase &item, std::uint32_t row, std::uint32_t local_index)
{
    constexpr std::array<std::array<std::uint32_t, 2>, 4> sizes = {{
        {{64, 64}}, {{128, 128}}, {{512, 128}}, {{1024, 1024}},
    }};
    const auto mode = static_cast<std::uint8_t>((local_index + row) % 7U);
    const auto climate = static_cast<std::uint8_t>((local_index * 3U + row) % 4U);
    const auto program = active_program(mode, local_index + row);
    const auto selected_size = sizes[(local_index + row) % sizes.size()];
    const auto offset = static_cast<std::size_t>(row) * kFeatureCount;
    item.public_features[offset + mode] = 1.0F;
    item.public_features[offset + 7U + climate] = 1.0F;
    item.public_features[offset + 11U] = static_cast<float>(selected_size[0]) / 4096.0F;
    item.public_features[offset + 12U] = static_cast<float>(selected_size[1]) / 4096.0F;
    item.public_features[offset + 13U] =
        static_cast<float>(selected_size[0] * selected_size[1]) / 1048576.0F;
    item.public_features[offset + 13U + program] = 1.0F;
    item.public_features[offset + 30U] = static_cast<float>((local_index + row) % 4U) / 3.0F;
    std::uint64_t random_state = (static_cast<std::uint64_t>(item.seed) << 32U) |
        (static_cast<std::uint64_t>(row) + UINT64_C(0x9e3779b9));
    item.public_features[offset + 31U] = unit_random(random_state);
    if (item.case_class == M23GoldenClass::AdversarialBoundary) {
        if (local_index == 16U) item.public_features[offset + 31U] = 0.0F;
        if (local_index == 17U) item.public_features[offset + 31U] = 1.0F;
        if (local_index == 18U) {
            item.public_features[offset + 11U] = 1.0F;
            item.public_features[offset + 12U] = 1.0F;
            item.public_features[offset + 13U] = 1.0F;
        }
    }
    const auto mask_offset = static_cast<std::size_t>(row) * kProgramCount;
    switch (item.mask_pattern) {
        case 0:
            item.program_mask[mask_offset] = 1;
            break;
        case 1:
            std::fill_n(item.program_mask.begin() + static_cast<std::ptrdiff_t>(mask_offset), kProgramCount, 1);
            break;
        case 2:
            item.program_mask[mask_offset] = 1;
            item.program_mask[mask_offset + program] = 1;
            break;
        case 3:
            item.program_mask[mask_offset] = 1;
            item.program_mask[mask_offset + program] = 1;
            item.program_mask[mask_offset + 1U + ((program + 4U) % 16U)] = 1;
            item.program_mask[mask_offset + 1U + ((program + 9U) % 16U)] = 1;
            break;
        default:
            throw std::invalid_argument("M23 golden mask pattern is invalid");
    }
    if (item.hidden_mode == M23HiddenMode::Seeded) {
        for (std::uint32_t hidden = 0; hidden < kHiddenCount; ++hidden) {
            item.initial_hidden[static_cast<std::size_t>(row) * kHiddenCount + hidden] =
                unit_random(random_state) * 1.5F - 0.75F;
        }
    }
}

void append_u8(std::vector<std::uint8_t> &output, std::uint8_t value)
{
    output.push_back(value);
}

void append_u16(std::vector<std::uint8_t> &output, std::uint16_t value)
{
    output.push_back(static_cast<std::uint8_t>(value));
    output.push_back(static_cast<std::uint8_t>(value >> 8U));
}

void append_u32(std::vector<std::uint8_t> &output, std::uint32_t value)
{
    for (unsigned int shift = 0; shift < 32U; shift += 8U) {
        output.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_u64(std::vector<std::uint8_t> &output, std::uint64_t value)
{
    for (unsigned int shift = 0; shift < 64U; shift += 8U) {
        output.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_float(std::vector<std::uint8_t> &output, float value)
{
    require(std::isfinite(value), "M23 golden file cannot contain nonfinite floats");
    append_u32(output, std::bit_cast<std::uint32_t>(value));
}

void append_string(std::vector<std::uint8_t> &output, std::string_view value)
{
    require(!value.empty() && value.size() <= 96U, "M23 golden case ID length is invalid");
    append_u16(output, static_cast<std::uint16_t>(value.size()));
    output.insert(output.end(), value.begin(), value.end());
}

class Reader {
public:
    explicit Reader(std::vector<std::uint8_t> bytes) : bytes_(std::move(bytes)) {}

    [[nodiscard]] std::uint8_t u8()
    {
        ensure(1);
        return bytes_[offset_++];
    }

    [[nodiscard]] std::uint16_t u16()
    {
        const auto low = static_cast<std::uint16_t>(u8());
        return low | static_cast<std::uint16_t>(static_cast<std::uint16_t>(u8()) << 8U);
    }

    [[nodiscard]] std::uint32_t u32()
    {
        std::uint32_t result = 0;
        for (unsigned int shift = 0; shift < 32U; shift += 8U) {
            result |= static_cast<std::uint32_t>(u8()) << shift;
        }
        return result;
    }

    [[nodiscard]] std::uint64_t u64()
    {
        std::uint64_t result = 0;
        for (unsigned int shift = 0; shift < 64U; shift += 8U) {
            result |= static_cast<std::uint64_t>(u8()) << shift;
        }
        return result;
    }

    [[nodiscard]] float floating()
    {
        const auto result = std::bit_cast<float>(u32());
        require(std::isfinite(result), "M23 golden file contains a nonfinite float");
        return result;
    }

    [[nodiscard]] std::string string()
    {
        const auto length = u16();
        ensure(length);
        std::string result(bytes_.begin() + static_cast<std::ptrdiff_t>(offset_),
            bytes_.begin() + static_cast<std::ptrdiff_t>(offset_ + length));
        offset_ += length;
        return result;
    }

    void exact_end() const
    {
        require(offset_ == bytes_.size(), "M23 golden file has trailing bytes");
    }

private:
    void ensure(std::size_t count) const
    {
        require(count <= bytes_.size() - std::min(offset_, bytes_.size()), "M23 golden file is truncated");
    }

    std::vector<std::uint8_t> bytes_;
    std::size_t offset_{};
};

[[nodiscard]] std::vector<std::uint8_t> read_bounded(const std::filesystem::path &path)
{
    require(path.is_absolute() && std::filesystem::is_regular_file(path) && !std::filesystem::is_symlink(path),
        "M23 golden path must be an absolute regular file");
    const auto size = std::filesystem::file_size(path);
    require(size <= kMaximumGoldenBytes, "M23 golden file exceeds its byte bound");
    std::vector<std::uint8_t> result(static_cast<std::size_t>(size));
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor < 0) throw std::runtime_error("cannot open M23 golden file: " + std::string(std::strerror(errno)));
    std::size_t read = 0;
    while (read < result.size()) {
        const auto count = ::read(descriptor, result.data() + read, result.size() - read);
        if (count <= 0) {
            ::close(descriptor);
            throw std::runtime_error("cannot read exact M23 golden file");
        }
        read += static_cast<std::size_t>(count);
    }
    if (::close(descriptor) != 0) throw std::runtime_error("cannot close M23 golden file");
    return result;
}

void write_new(const std::filesystem::path &path, std::span<const std::uint8_t> bytes)
{
    require(path.is_absolute() && !std::filesystem::exists(path) && !std::filesystem::is_symlink(path) &&
            (!path.has_parent_path() || std::filesystem::is_directory(path.parent_path())),
        "M23 golden output must be a new absolute file below an existing directory");
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, S_IRUSR | S_IWUSR);
    if (descriptor < 0) throw std::runtime_error("cannot create M23 golden file: " + std::string(std::strerror(errno)));
    std::size_t written = 0;
    while (written < bytes.size()) {
        const auto count = ::write(descriptor, bytes.data() + written, bytes.size() - written);
        if (count <= 0) {
            ::close(descriptor);
            throw std::runtime_error("cannot write exact M23 golden file");
        }
        written += static_cast<std::size_t>(count);
    }
    if (::fsync(descriptor) != 0 || ::close(descriptor) != 0) {
        throw std::runtime_error("cannot sync or close M23 golden file");
    }
}

} // namespace

std::string_view m23_golden_architecture_name(M23GoldenArchitecture architecture)
{
    switch (architecture) {
        case M23GoldenArchitecture::Monolithic: return "monolithic-generalist-v1";
        case M23GoldenArchitecture::Specialist: return "specialist-router-v1";
    }
    throw std::invalid_argument("invalid M23 golden architecture");
}

std::vector<M23GoldenCase> generate_m23_golden_cases(M23GoldenArchitecture architecture)
{
    std::vector<M23GoldenCase> result;
    result.reserve(kCasesPerArchitecture);
    const auto architecture_index = static_cast<std::uint32_t>(architecture);
    require(architecture_index <= 1U, "invalid M23 golden architecture index");
    constexpr std::array<std::uint32_t, 8> adversarial_batches = {1, 8, 32, 1, 8, 32, 8, 32};
    constexpr std::array<std::uint8_t, 8> adversarial_masks = {0, 1, 3, 2, 1, 0, 3, 2};
    for (std::uint32_t local = 0; local < kCasesPerArchitecture; ++local) {
        M23GoldenCase item;
        item.architecture = architecture;
        item.seed = derived_seed(architecture_index * kCasesPerArchitecture + local);
        item.case_class = local < 8U ? M23GoldenClass::PublicProjection :
            local < 16U ? M23GoldenClass::RecurrentSequence : M23GoldenClass::AdversarialBoundary;
        if (item.case_class == M23GoldenClass::PublicProjection) {
            item.batch = 1;
            item.mask_pattern = 2;
            item.hidden_mode = M23HiddenMode::Zero;
        } else if (item.case_class == M23GoldenClass::RecurrentSequence) {
            item.sequence = local < 12U ? 0 : 1;
            item.step = static_cast<std::uint8_t>((local - 8U) % 4U);
            item.batch = item.sequence == 0 ? 8 : 32;
            item.mask_pattern = static_cast<std::uint8_t>(2U + item.step % 2U);
            item.hidden_mode = item.step == 0 ? M23HiddenMode::Zero : M23HiddenMode::Carry;
        } else {
            const auto adversarial = local - 16U;
            item.batch = adversarial_batches[adversarial];
            item.mask_pattern = adversarial_masks[adversarial];
            item.hidden_mode = adversarial % 2U == 0 ? M23HiddenMode::Seeded : M23HiddenMode::Zero;
        }
        const auto class_name = item.case_class == M23GoldenClass::PublicProjection ? "public" :
            item.case_class == M23GoldenClass::RecurrentSequence ? "recurrent" : "adversarial";
        item.case_id = std::string(m23_golden_architecture_name(architecture)) + '-' + class_name + '-' +
            (local < 10U ? "0" : "") + std::to_string(local);
        item.public_features.assign(static_cast<std::size_t>(item.batch) * kFeatureCount, 0.0F);
        item.program_mask.assign(static_cast<std::size_t>(item.batch) * kProgramCount, 0);
        item.initial_hidden.assign(static_cast<std::size_t>(item.batch) * kHiddenCount, 0.0F);
        item.recurrent_reset.assign(item.batch, 0);
        if (item.case_class != M23GoldenClass::RecurrentSequence || item.step == 0) {
            std::fill(item.recurrent_reset.begin(), item.recurrent_reset.end(), 1);
        } else if (item.step == 2) {
            for (std::uint32_t row = 0; row < item.batch; ++row) {
                item.recurrent_reset[row] = row % 2U == 0 ? 1 : 0;
            }
        }
        for (std::uint32_t row = 0; row < item.batch; ++row) fill_row(item, row, local);
        result.push_back(std::move(item));
    }
    return result;
}

void validate_m23_golden_record(const M23GoldenRecord &record)
{
    const auto batch = static_cast<std::size_t>(record.definition.batch);
    require(batch >= 1U && batch <= 32U, "M23 golden record batch is outside 1 through 32");
    require(record.definition.public_features.size() == batch * kFeatureCount &&
            record.definition.program_mask.size() == batch * kProgramCount &&
            record.definition.initial_hidden.size() == batch * kHiddenCount &&
            record.definition.recurrent_reset.size() == batch &&
            record.hidden_input.size() == batch * kHiddenCount &&
            record.program_logits.size() == batch * kProgramCount &&
            record.program_value.size() == batch &&
            record.next_hidden.size() == batch * kHiddenCount &&
            record.greedy_program.size() == batch,
        "M23 golden record tensor sizes drifted");
    require(std::all_of(record.definition.program_mask.begin(), record.definition.program_mask.end(),
                [](std::uint8_t value) { return value <= 1; }) &&
            std::all_of(record.definition.recurrent_reset.begin(), record.definition.recurrent_reset.end(),
                [](std::uint8_t value) { return value <= 1; }),
        "M23 golden record contains a non-boolean byte");
    for (std::size_t row = 0; row < batch; ++row) {
        const auto begin = record.definition.program_mask.begin() +
            static_cast<std::ptrdiff_t>(row * kProgramCount);
        require(std::any_of(begin, begin + kProgramCount, [](std::uint8_t value) { return value == 1; }),
            "M23 golden record contains an all-illegal row");
        require(record.greedy_program[row] >= 0 && record.greedy_program[row] < static_cast<std::int64_t>(kProgramCount) &&
                record.definition.program_mask[row * kProgramCount +
                    static_cast<std::size_t>(record.greedy_program[row])] == 1,
            "M23 golden record selected an illegal program");
    }
    for (const auto *values : {&record.definition.public_features, &record.definition.initial_hidden,
             &record.hidden_input, &record.program_logits, &record.program_value, &record.next_hidden}) {
        require(std::all_of(values->begin(), values->end(), [](float value) { return std::isfinite(value); }),
            "M23 golden record contains nonfinite tensor data");
    }
}

void write_m23_golden_file(const std::filesystem::path &path, const std::vector<M23GoldenRecord> &records)
{
    require(records.size() == 2U * kCasesPerArchitecture, "M23 golden file must contain exactly 48 cases");
    std::vector<std::uint8_t> bytes(kMagic.begin(), kMagic.end());
    append_u32(bytes, kVersion);
    append_u32(bytes, static_cast<std::uint32_t>(records.size()));
    for (const auto &record : records) {
        validate_m23_golden_record(record);
        append_u8(bytes, static_cast<std::uint8_t>(record.definition.architecture));
        append_u8(bytes, static_cast<std::uint8_t>(record.definition.case_class));
        append_u8(bytes, record.definition.sequence);
        append_u8(bytes, record.definition.step);
        append_u8(bytes, record.definition.mask_pattern);
        append_u8(bytes, static_cast<std::uint8_t>(record.definition.hidden_mode));
        append_u16(bytes, 0);
        append_u32(bytes, record.definition.seed);
        append_u32(bytes, record.definition.batch);
        append_string(bytes, record.definition.case_id);
        for (const auto value : record.definition.public_features) append_float(bytes, value);
        bytes.insert(bytes.end(), record.definition.program_mask.begin(), record.definition.program_mask.end());
        for (const auto value : record.definition.initial_hidden) append_float(bytes, value);
        bytes.insert(bytes.end(), record.definition.recurrent_reset.begin(), record.definition.recurrent_reset.end());
        for (const auto value : record.hidden_input) append_float(bytes, value);
        for (const auto value : record.program_logits) append_float(bytes, value);
        for (const auto value : record.program_value) append_float(bytes, value);
        for (const auto value : record.next_hidden) append_float(bytes, value);
        for (const auto value : record.greedy_program) append_u64(bytes, static_cast<std::uint64_t>(value));
    }
    require(bytes.size() <= kMaximumGoldenBytes, "M23 golden file exceeds its byte bound");
    write_new(path, bytes);
}

std::vector<M23GoldenRecord> read_m23_golden_file(const std::filesystem::path &path)
{
    Reader reader(read_bounded(path));
    for (const auto expected : kMagic) require(reader.u8() == expected, "M23 golden magic mismatch");
    require(reader.u32() == kVersion, "M23 golden version mismatch");
    const auto count = reader.u32();
    require(count == 2U * kCasesPerArchitecture, "M23 golden case count mismatch");
    std::vector<M23GoldenRecord> records;
    records.reserve(count);
    for (std::uint32_t index = 0; index < count; ++index) {
        M23GoldenRecord record;
        record.definition.architecture = static_cast<M23GoldenArchitecture>(reader.u8());
        record.definition.case_class = static_cast<M23GoldenClass>(reader.u8());
        record.definition.sequence = reader.u8();
        record.definition.step = reader.u8();
        record.definition.mask_pattern = reader.u8();
        record.definition.hidden_mode = static_cast<M23HiddenMode>(reader.u8());
        require(reader.u16() == 0, "M23 golden reserved field is nonzero");
        record.definition.seed = reader.u32();
        record.definition.batch = reader.u32();
        record.definition.case_id = reader.string();
        const auto batch = static_cast<std::size_t>(record.definition.batch);
        auto read_floats = [&](std::size_t size) {
            std::vector<float> values(size);
            std::generate(values.begin(), values.end(), [&] { return reader.floating(); });
            return values;
        };
        auto read_bytes = [&](std::size_t size) {
            std::vector<std::uint8_t> values(size);
            std::generate(values.begin(), values.end(), [&] { return reader.u8(); });
            return values;
        };
        record.definition.public_features = read_floats(batch * kFeatureCount);
        record.definition.program_mask = read_bytes(batch * kProgramCount);
        record.definition.initial_hidden = read_floats(batch * kHiddenCount);
        record.definition.recurrent_reset = read_bytes(batch);
        record.hidden_input = read_floats(batch * kHiddenCount);
        record.program_logits = read_floats(batch * kProgramCount);
        record.program_value = read_floats(batch);
        record.next_hidden = read_floats(batch * kHiddenCount);
        record.greedy_program.resize(batch);
        std::generate(record.greedy_program.begin(), record.greedy_program.end(), [&] {
            return static_cast<std::int64_t>(reader.u64());
        });
        validate_m23_golden_record(record);
        records.push_back(std::move(record));
    }
    reader.exact_end();
    const auto expected_monolithic = generate_m23_golden_cases(M23GoldenArchitecture::Monolithic);
    const auto expected_specialist = generate_m23_golden_cases(M23GoldenArchitecture::Specialist);
    for (std::size_t index = 0; index < records.size(); ++index) {
        const auto &expected = index < kCasesPerArchitecture ? expected_monolithic[index] :
            expected_specialist[index - kCasesPerArchitecture];
        const auto &actual = records[index].definition;
        require(actual.case_id == expected.case_id && actual.architecture == expected.architecture &&
                actual.case_class == expected.case_class && actual.sequence == expected.sequence &&
                actual.step == expected.step && actual.mask_pattern == expected.mask_pattern &&
                actual.hidden_mode == expected.hidden_mode && actual.seed == expected.seed &&
                actual.batch == expected.batch && actual.public_features == expected.public_features &&
                actual.program_mask == expected.program_mask && actual.initial_hidden == expected.initial_hidden &&
                actual.recurrent_reset == expected.recurrent_reset,
            "M23 golden case definition drifted from the frozen generator");
    }
    return records;
}

std::string m23_sha256_file(const std::filesystem::path &path)
{
    const auto bytes = read_bounded(path);
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
    unsigned int length = 0;
    auto *context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("cannot allocate M23 file SHA-256 context");
    const bool success = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, bytes.data(), bytes.size()) == 1 &&
        EVP_DigestFinal_ex(context, digest.data(), &length) == 1;
    EVP_MD_CTX_free(context);
    if (!success || length != 32) throw std::runtime_error("cannot hash M23 file");
    static constexpr char alphabet[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (unsigned int index = 0; index < length; ++index) {
        result.push_back(alphabet[digest[index] >> 4U]);
        result.push_back(alphabet[digest[index] & 0x0FU]);
    }
    return result;
}

std::string m23_sha256_bytes(std::string_view value)
{
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
    unsigned int length = 0;
    auto *context = EVP_MD_CTX_new();
    if (context == nullptr) throw std::runtime_error("cannot allocate M23 byte SHA-256 context");
    const bool success = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
        EVP_DigestUpdate(context, value.data(), value.size()) == 1 &&
        EVP_DigestFinal_ex(context, digest.data(), &length) == 1;
    EVP_MD_CTX_free(context);
    if (!success || length != 32) throw std::runtime_error("cannot hash M23 bytes");
    static constexpr char alphabet[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (unsigned int index = 0; index < length; ++index) {
        result.push_back(alphabet[digest[index] >> 4U]);
        result.push_back(alphabet[digest[index] & 0x0FU]);
    }
    return result;
}

} // namespace openttd_rl::v2
