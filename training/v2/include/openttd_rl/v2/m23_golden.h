#ifndef OPENTTD_RL_V2_M23_GOLDEN_H
#define OPENTTD_RL_V2_M23_GOLDEN_H

#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace openttd_rl::v2 {

enum class M23GoldenArchitecture : std::uint8_t {
    Monolithic = 0,
    Specialist = 1,
};

enum class M23GoldenClass : std::uint8_t {
    PublicProjection = 0,
    RecurrentSequence = 1,
    AdversarialBoundary = 2,
};

enum class M23HiddenMode : std::uint8_t {
    Zero = 0,
    Carry = 1,
    Seeded = 2,
};

struct M23GoldenCase {
    std::string case_id;
    M23GoldenArchitecture architecture{M23GoldenArchitecture::Monolithic};
    M23GoldenClass case_class{M23GoldenClass::PublicProjection};
    std::uint8_t sequence{255};
    std::uint8_t step{};
    std::uint8_t mask_pattern{};
    M23HiddenMode hidden_mode{M23HiddenMode::Zero};
    std::uint32_t seed{};
    std::uint32_t batch{};
    std::vector<float> public_features;
    std::vector<std::uint8_t> program_mask;
    std::vector<float> initial_hidden;
    std::vector<std::uint8_t> recurrent_reset;
};

struct M23GoldenRecord {
    M23GoldenCase definition;
    std::vector<float> hidden_input;
    std::vector<float> program_logits;
    std::vector<float> program_value;
    std::vector<float> next_hidden;
    std::vector<std::int64_t> greedy_program;
};

[[nodiscard]] std::string_view m23_golden_architecture_name(M23GoldenArchitecture architecture);
[[nodiscard]] std::vector<M23GoldenCase> generate_m23_golden_cases(M23GoldenArchitecture architecture);
void validate_m23_golden_record(const M23GoldenRecord &record);
void write_m23_golden_file(const std::filesystem::path &path, const std::vector<M23GoldenRecord> &records);
[[nodiscard]] std::vector<M23GoldenRecord> read_m23_golden_file(const std::filesystem::path &path);
[[nodiscard]] std::string m23_sha256_file(const std::filesystem::path &path);
[[nodiscard]] std::string m23_sha256_bytes(std::string_view value);

} // namespace openttd_rl::v2

#endif
