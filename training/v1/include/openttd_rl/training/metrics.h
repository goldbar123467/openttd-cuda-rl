#ifndef OPENTTD_RL_TRAINING_METRICS_H
#define OPENTTD_RL_TRAINING_METRICS_H

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>

#include "openttd_rl/training/trainer.h"

namespace openttd_rl::training {

inline constexpr const char *kMetricSchemaVersion = "openttd-rl-v1-m07-metric-event-1";
inline constexpr std::size_t kMaximumMetricEventBytes = 16384;

struct RunMetadata {
    std::string run_name;
    std::string repository_commit;
    std::string openttd_version{"15.3"};
    std::string environment_version;
    std::uint64_t run_seed{};
    std::uint64_t environment_count{};
    std::string device{"cpu"};
};

struct EnvironmentMetrics {
    std::optional<double> mean_episode_return;
    std::optional<double> mean_episode_length;
    std::optional<double> company_profit;
    std::optional<double> passenger_deliveries;
    std::optional<double> vehicles;
    std::optional<double> routes;
    std::uint64_t invalid_actions{};
    std::uint64_t mask_violations{};
    std::uint64_t resets{};
};

struct SystemMetrics {
    std::optional<double> cpu_utilization_percent;
    std::optional<std::uint64_t> process_memory_bytes;
    bool gpu_available{false};
    std::optional<double> gpu_utilization_percent;
    std::optional<std::uint64_t> gpu_memory_bytes;
};

struct MetricEvent {
    std::string event{"ppo_update"};
    std::uint64_t sequence{};
    std::uint64_t unix_time_ns{};
    std::uint64_t elapsed_ns{};
    std::optional<double> steps_per_second;
    RunMetadata run;
    TrainerCounters counters;
    UpdateMetrics training;
    EnvironmentMetrics environment;
    SystemMetrics system;
    std::optional<std::string> checkpoint_id;
    std::optional<double> best_development_score;
    std::string warning_state{"OK"};
};

class SystemTelemetrySampler {
public:
    SystemTelemetrySampler();
    [[nodiscard]] SystemMetrics sample();

private:
    std::uint64_t previous_wall_ns_{};
    std::uint64_t previous_process_ns_{};
};

class JsonlMetricSink {
public:
    explicit JsonlMetricSink(std::filesystem::path path, bool durable = false);
    ~JsonlMetricSink();
    JsonlMetricSink(const JsonlMetricSink &) = delete;
    JsonlMetricSink &operator=(const JsonlMetricSink &) = delete;

    [[nodiscard]] std::string write(const MetricEvent &event);
    [[nodiscard]] const std::filesystem::path &path() const noexcept { return path_; }

private:
    std::filesystem::path path_;
    int descriptor_{-1};
    bool durable_{};
};

[[nodiscard]] std::string metric_event_json(const MetricEvent &event);
[[nodiscard]] std::string render_terminal_monitor(const MetricEvent &event, std::size_t width);

} // namespace openttd_rl::training

#endif
