#include "openttd_rl/v2/m22_corpus.h"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace openttd_rl::v2 {

namespace {

constexpr std::array<char, 8> kMagic = {'O', 'T', 'R', 'L', 'M', '2', '2', 'C'};
constexpr std::uint32_t kVersion = 1;
constexpr std::size_t kMaximumBytes = 1024 * 1024;

class Reader {
public:
    explicit Reader(std::vector<std::uint8_t> data) : data_(std::move(data)) {}

    void expect(const void *expected, std::size_t length)
    {
        require_available(length);
        if (std::memcmp(data_.data() + offset_, expected, length) != 0) {
            throw std::invalid_argument("M22 native corpus magic mismatch");
        }
        offset_ += length;
    }

    std::uint8_t u8()
    {
        require_available(1);
        return data_[offset_++];
    }

    std::uint16_t u16()
    {
        std::uint32_t result = 0;
        for (unsigned int shift = 0; shift < 16U; shift += 8U) result |= static_cast<std::uint32_t>(u8()) << shift;
        return static_cast<std::uint16_t>(result);
    }

    std::uint32_t u32()
    {
        std::uint32_t result = 0;
        for (unsigned int shift = 0; shift < 32U; shift += 8U) result |= static_cast<std::uint32_t>(u8()) << shift;
        return result;
    }

    std::uint64_t u64()
    {
        std::uint64_t result = 0;
        for (unsigned int shift = 0; shift < 64U; shift += 8U) result |= static_cast<std::uint64_t>(u8()) << shift;
        return result;
    }

    float f32() { return std::bit_cast<float>(u32()); }
    double f64() { return std::bit_cast<double>(u64()); }

    std::string string(std::size_t length)
    {
        require_available(length);
        std::string result(reinterpret_cast<const char *>(data_.data() + offset_), length);
        offset_ += length;
        return result;
    }

    void finish() const
    {
        if (offset_ != data_.size()) throw std::invalid_argument("M22 native corpus has trailing bytes");
    }

private:
    void require_available(std::size_t length) const
    {
        if (length > data_.size() - offset_) throw std::invalid_argument("M22 native corpus is truncated");
    }

    std::vector<std::uint8_t> data_;
    std::size_t offset_{};
};

std::vector<std::uint8_t> read_corpus(const std::filesystem::path &path)
{
    if (!path.is_absolute() || !std::filesystem::is_regular_file(path) || std::filesystem::is_symlink(path)) {
        throw std::invalid_argument("M22 native corpus path must be an absolute regular non-symlink file");
    }
    const auto size = std::filesystem::file_size(path);
    if (size == 0 || size > kMaximumBytes) throw std::length_error("M22 native corpus size is outside its byte budget");
    std::vector<std::uint8_t> result(static_cast<std::size_t>(size));
    std::ifstream input(path, std::ios::binary);
    input.read(reinterpret_cast<char *>(result.data()), static_cast<std::streamsize>(result.size()));
    if (!input || input.peek() != std::ifstream::traits_type::eof()) {
        throw std::runtime_error("cannot read exact M22 native corpus bytes");
    }
    return result;
}

bool digest(const std::string &value)
{
    return value.size() == 64 && value.find_first_not_of("0123456789abcdef") == std::string::npos;
}

} // namespace

const M22CorpusEntry &M22Corpus::entry(M22CorpusSplit split, std::int64_t program) const
{
    if (program <= 0 || program >= kM22ProgramCount) throw std::out_of_range("M22 corpus program is out of range");
    const auto found = std::find_if(entries.begin(), entries.end(), [&](const auto &item) {
        return item.split == split && item.program == program;
    });
    if (found == entries.end()) throw std::out_of_range("M22 corpus split/program entry is missing");
    return *found;
}

M22Corpus load_m22_corpus(const std::filesystem::path &path)
{
    Reader reader(read_corpus(path));
    reader.expect(kMagic.data(), kMagic.size());
    if (reader.u32() != kVersion) throw std::invalid_argument("M22 native corpus version mismatch");
    M22Corpus result;
    result.learning_contract_sha256 = reader.string(64);
    result.corpus_sha256 = reader.string(64);
    if (!digest(result.learning_contract_sha256) || !digest(result.corpus_sha256) ||
        result.learning_contract_sha256 != kM22LearningContractSha256 || result.corpus_sha256 != kM22NativeCorpusSha256) {
        throw std::invalid_argument("M22 native corpus compatibility identity mismatch");
    }
    const auto count = reader.u32();
    if (count != 32) throw std::invalid_argument("M22 native corpus entry count drifted");
    result.entries.reserve(count);
    std::set<std::string> ids;
    for (std::uint32_t index = 0; index < count; ++index) {
        M22CorpusEntry entry;
        const auto split = reader.u8();
        entry.program = reader.u8();
        const auto reserved = reader.u16();
        entry.sampler_seed = reader.u32();
        const auto name_length = reader.u16();
        if (split > 1 || entry.program == 0 || entry.program >= kM22ProgramCount || reserved != 0 ||
            entry.sampler_seed == 0 || entry.sampler_seed > INT32_MAX || name_length == 0 || name_length > 128) {
            throw std::invalid_argument("M22 native corpus entry header is invalid");
        }
        entry.split = static_cast<M22CorpusSplit>(split);
        entry.entry_id = reader.string(name_length);
        if (!ids.insert(entry.entry_id).second || entry.entry_id.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789-") != std::string::npos) {
            throw std::invalid_argument("M22 native corpus entry ID is invalid or duplicated");
        }
        for (auto &value : entry.public_features) {
            value = reader.f32();
            if (!std::isfinite(value) || value < 0.0F || value > 1.0F) {
                throw std::invalid_argument("M22 native corpus public feature is invalid");
            }
        }
        for (auto &&value : entry.program_mask) {
            const auto raw = reader.u8();
            if (raw > 1) throw std::invalid_argument("M22 native corpus program mask is nonbinary");
            value = raw != 0;
        }
        for (auto &value : entry.rewards) {
            value = reader.f64();
            if (!std::isfinite(value)) throw std::invalid_argument("M22 native corpus reward is nonfinite");
        }
        if (!entry.program_mask[0] || !entry.program_mask[entry.program] ||
            std::count(entry.program_mask.begin(), entry.program_mask.end(), true) != 2 ||
            entry.rewards[0] != 0.0 || entry.rewards[entry.program] <= 0.0) {
            throw std::invalid_argument("M22 native corpus legality or reward semantics drifted");
        }
        result.entries.push_back(std::move(entry));
    }
    reader.finish();
    for (const auto split : {M22CorpusSplit::Training, M22CorpusSplit::Development}) {
        for (std::int64_t program = 1; program < kM22ProgramCount; ++program) {
            const auto &entry = result.entry(split, program);
            const auto expected_prefix = split == M22CorpusSplit::Training ? "training-" : "development-";
            if (!entry.entry_id.starts_with(expected_prefix)) {
                throw std::invalid_argument("M22 native corpus split order or identity drifted");
            }
        }
    }
    return result;
}

M22CompactBatch m22_compact_from_entries(
    const std::vector<const M22CorpusEntry *> &entries,
    const torch::Tensor &hidden_state,
    const torch::Tensor &recurrent_reset)
{
    if (entries.empty()) throw std::invalid_argument("M22 compact corpus batch is empty");
    const auto batch = static_cast<std::int64_t>(entries.size());
    auto features = torch::empty({batch, kM22CompactFeatures}, torch::kFloat32);
    auto masks = torch::empty({batch, kM22ProgramCount}, torch::kBool);
    auto feature_view = features.accessor<float, 2>();
    auto mask_view = masks.accessor<bool, 2>();
    for (std::int64_t row = 0; row < batch; ++row) {
        if (entries[static_cast<std::size_t>(row)] == nullptr) throw std::invalid_argument("M22 compact corpus entry is null");
        const auto &entry = *entries[static_cast<std::size_t>(row)];
        for (std::int64_t column = 0; column < kM22CompactFeatures; ++column) {
            feature_view[row][column] = entry.public_features[static_cast<std::size_t>(column)];
        }
        for (std::int64_t program = 0; program < kM22ProgramCount; ++program) {
            mask_view[row][program] = entry.program_mask[static_cast<std::size_t>(program)];
        }
    }
    M22CompactBatch result{features, masks, hidden_state.clone(), recurrent_reset.clone()};
    result.validate();
    return result;
}

} // namespace openttd_rl::v2
