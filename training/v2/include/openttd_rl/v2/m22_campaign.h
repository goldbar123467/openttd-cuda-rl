#ifndef OPENTTD_RL_V2_M22_CAMPAIGN_H
#define OPENTTD_RL_V2_M22_CAMPAIGN_H

#include <cstdint>
#include <memory>
#include <string>

#include "openttd_rl/v2/m22_checkpoint.h"

namespace openttd_rl::v2 {

struct M22RetentionResult {
    std::uint64_t update{};
    std::uint32_t stage{};
    std::uint32_t introduced_programs{};
    std::uint32_t passed_programs{};
    std::uint32_t pass_mask{};
    double accuracy{};
    double mean_reward{};
    bool catastrophic_regression{};
    bool checkpoint_allowed{};
    bool selection_eligible{};
};

struct M22CampaignUpdateResult {
    M22UpdateMetrics trainer;
    std::uint32_t stage{};
    double mean_rollout_reward{};
    double correct_program_fraction{};
    std::string case_order_sha256;
    std::string actions_sha256;
    std::string log_probabilities_sha256;
    std::string values_sha256;
    std::string rewards_sha256;
    std::string hidden_state_sha256;
    bool retention_ran{};
    M22RetentionResult retention;
};

class M22Campaign {
public:
    M22Campaign(M22Corpus corpus, std::unique_ptr<M22Trainer> trainer);
    M22Campaign(
        M22Corpus corpus,
        std::unique_ptr<M22Trainer> trainer,
        const M22CampaignCheckpointState &state);

    [[nodiscard]] M22CampaignUpdateResult run_update();
    [[nodiscard]] M22RetentionResult evaluate_development();
    [[nodiscard]] M22CampaignCheckpointState checkpoint_state() const;

    [[nodiscard]] M22Trainer &trainer() noexcept { return *trainer_; }
    [[nodiscard]] const M22Trainer &trainer() const noexcept { return *trainer_; }
    [[nodiscard]] std::uint32_t curriculum_stage() const noexcept { return curriculum_stage_; }
    [[nodiscard]] std::uint64_t episode() const noexcept { return episode_; }
    [[nodiscard]] std::uint64_t transition() const noexcept { return transition_; }
    [[nodiscard]] const M22RetentionResult &last_retention() const noexcept { return last_retention_; }

private:
    [[nodiscard]] std::uint32_t stage_for_next_update() const noexcept;
    [[nodiscard]] const M22CorpusEntry &sample_training_entry();
    void append_retention(const M22RetentionResult &result);

    M22Corpus corpus_;
    std::unique_ptr<M22Trainer> trainer_;
    torch::Tensor hidden_state_;
    std::vector<std::uint32_t> environment_case_cursor_;
    std::uint32_t curriculum_stage_{};
    std::uint32_t retention_pass_mask_{};
    double retention_best_accuracy_{};
    std::uint64_t episode_{};
    std::uint64_t transition_{};
    std::string retention_history_json_{"{\"checks\":[]}"};
    M22RetentionResult last_retention_;
};

[[nodiscard]] std::string m22_campaign_update_json(const M22CampaignUpdateResult &result);

} // namespace openttd_rl::v2

#endif
