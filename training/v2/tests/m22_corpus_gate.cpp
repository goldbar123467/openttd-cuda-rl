#include "openttd_rl/v2/m22_corpus.h"

#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void run(const std::filesystem::path &path)
{
    using namespace openttd_rl::v2;
    const auto corpus = load_m22_corpus(path);
    require(corpus.entries.size() == 32, "M22 native corpus gate lost entries");
    std::vector<const M22CorpusEntry *> entries;
    for (std::int64_t program = 1; program < kM22ProgramCount; ++program) {
        entries.push_back(&corpus.entry(M22CorpusSplit::Training, program));
    }
    const auto compact = m22_compact_from_entries(
        entries,
        torch::zeros({16, kHiddenSize}, torch::kFloat32),
        torch::ones({16}, torch::kBool));
    const auto heuristic = m22_public_heuristic(compact);
    for (std::int64_t row = 0; row < 16; ++row) {
        require(heuristic.index({row}).item<std::int64_t>() == row + 1,
                "M22 native corpus public heuristic mismatch");
        require(entries[static_cast<std::size_t>(row)]->rewards[static_cast<std::size_t>(row + 1)] > 0.0,
                "M22 native corpus active reward is not positive");
    }
    std::cout << "M22_CORPUS_GATE=PASS entries=" << corpus.entries.size()
              << " contract=" << corpus.learning_contract_sha256
              << " corpus=" << corpus.corpus_sha256 << '\n';
}

} // namespace

int main(int argc, char **argv)
{
    try {
        if (argc != 3 || std::string(argv[1]) != "--corpus") {
            throw std::invalid_argument("usage: m22_corpus_gate --corpus /absolute/path");
        }
        run(argv[2]);
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "M22_CORPUS_GATE=FAIL " << error.what() << '\n';
        return 1;
    }
}
