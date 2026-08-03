#ifndef OPENTTD_RL_V2_M22_CORPUS_H
#define OPENTTD_RL_V2_M22_CORPUS_H

#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include <torch/torch.h>

#include "openttd_rl/v2/m22_trainer.h"

namespace openttd_rl::v2 {

inline constexpr const char *kM22NativeCorpusSha256 =
    "0af952bb840bca2a80a577e2a2446845f2db749d7efbaeb06af4b94418ff6725";

enum class M22CorpusSplit : std::uint8_t {
    Training = 0,
    Development = 1,
};

struct M22CorpusEntry {
    M22CorpusSplit split{M22CorpusSplit::Training};
    std::uint8_t program{};
    std::uint32_t sampler_seed{};
    std::string entry_id;
    std::array<float, kM22CompactFeatures> public_features{};
    std::array<bool, kM22ProgramCount> program_mask{};
    std::array<double, kM22ProgramCount> rewards{};
};

struct M22Corpus {
    std::string learning_contract_sha256;
    std::string corpus_sha256;
    std::vector<M22CorpusEntry> entries;

    [[nodiscard]] const M22CorpusEntry &entry(M22CorpusSplit split, std::int64_t program) const;
};

[[nodiscard]] M22Corpus load_m22_corpus(const std::filesystem::path &path);
[[nodiscard]] M22CompactBatch m22_compact_from_entries(
    const std::vector<const M22CorpusEntry *> &entries,
    const torch::Tensor &hidden_state,
    const torch::Tensor &recurrent_reset);

} // namespace openttd_rl::v2

#endif
