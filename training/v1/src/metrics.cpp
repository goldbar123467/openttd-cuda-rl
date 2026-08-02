#include "openttd_rl/training/metrics.h"

#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <sys/stat.h>
#include <sys/times.h>
#include <unistd.h>

namespace openttd_rl::training {

namespace {

std::string json_escape(const std::string &value)
{
    std::ostringstream output;
    output << '"';
    for (const char character : value) {
        const auto byte = static_cast<unsigned char>(character);
        switch (byte) {
            case '"': output << "\\\""; break;
            case '\\': output << "\\\\"; break;
            case '\b': output << "\\b"; break;
            case '\f': output << "\\f"; break;
            case '\n': output << "\\n"; break;
            case '\r': output << "\\r"; break;
            case '\t': output << "\\t"; break;
            default:
                if (byte < 0x20U) {
                    output << "\\u00" << std::hex << std::setw(2) << std::setfill('0')
                           << static_cast<unsigned int>(byte) << std::dec;
                } else {
                    output << static_cast<char>(byte);
                }
        }
    }
    output << '"';
    return output.str();
}

template <typename Value>
std::string json_optional(const std::optional<Value> &value)
{
    if (!value.has_value()) return "null";
    std::ostringstream output;
    output.imbue(std::locale::classic());
    if constexpr (std::is_floating_point_v<Value>) {
        if (!std::isfinite(*value)) throw std::invalid_argument("nonfinite metric value");
        output << std::setprecision(std::numeric_limits<Value>::max_digits10) << *value;
    } else {
        output << *value;
    }
    return output.str();
}

std::string json_double(double value)
{
    if (!std::isfinite(value)) throw std::invalid_argument("nonfinite metric value");
    std::ostringstream output;
    output.imbue(std::locale::classic());
    output << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
    return output.str();
}

std::uint64_t monotonic_ns()
{
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

std::uint64_t process_cpu_ns()
{
    struct tms times_value {};
    if (::times(&times_value) == static_cast<clock_t>(-1)) throw std::runtime_error("times failed");
    const long ticks = ::sysconf(_SC_CLK_TCK);
    if (ticks <= 0) throw std::runtime_error("cannot resolve process clock ticks");
    const auto consumed = static_cast<std::uint64_t>(times_value.tms_utime + times_value.tms_stime);
    return consumed * UINT64_C(1000000000) / static_cast<std::uint64_t>(ticks);
}

std::optional<std::uint64_t> process_memory_bytes()
{
    std::ifstream stream("/proc/self/statm");
    std::uint64_t total_pages = 0;
    std::uint64_t resident_pages = 0;
    if (!(stream >> total_pages >> resident_pages)) return std::nullopt;
    (void)total_pages;
    const long page_size = ::sysconf(_SC_PAGESIZE);
    if (page_size <= 0 || resident_pages > std::numeric_limits<std::uint64_t>::max() / static_cast<std::uint64_t>(page_size)) {
        return std::nullopt;
    }
    return resident_pages * static_cast<std::uint64_t>(page_size);
}

std::string printable_optional(const std::optional<double> &value, int precision = 3)
{
    if (!value.has_value()) return "n/a";
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(precision) << *value;
    return stream.str();
}

} // namespace

SystemTelemetrySampler::SystemTelemetrySampler()
    : previous_wall_ns_(monotonic_ns()), previous_process_ns_(process_cpu_ns())
{
}

SystemMetrics SystemTelemetrySampler::sample()
{
    SystemMetrics result;
    const auto wall = monotonic_ns();
    const auto process = process_cpu_ns();
    if (wall > previous_wall_ns_ && process >= previous_process_ns_) {
        result.cpu_utilization_percent =
            100.0 * static_cast<double>(process - previous_process_ns_) / static_cast<double>(wall - previous_wall_ns_);
    }
    previous_wall_ns_ = wall;
    previous_process_ns_ = process;
    result.process_memory_bytes = process_memory_bytes();
    result.gpu_available = false;
    result.gpu_utilization_percent = std::nullopt;
    result.gpu_memory_bytes = std::nullopt;
    return result;
}

JsonlMetricSink::JsonlMetricSink(std::filesystem::path path, bool durable)
    : path_(std::move(path)), durable_(durable)
{
    if (path_.empty() || !path_.is_absolute()) throw std::invalid_argument("metric path must be absolute");
    std::filesystem::create_directories(path_.parent_path());
    descriptor_ = ::open(path_.c_str(), O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH);
    if (descriptor_ < 0) throw std::runtime_error("cannot open metric sink: " + std::string(std::strerror(errno)));
}

JsonlMetricSink::~JsonlMetricSink()
{
    if (descriptor_ >= 0) (void)::close(descriptor_);
}

std::string JsonlMetricSink::write(const MetricEvent &event)
{
    auto line = metric_event_json(event);
    line.push_back('\n');
    if (line.size() > kMaximumMetricEventBytes) throw std::length_error("metric event exceeds bounded size");
    std::size_t written = 0;
    while (written < line.size()) {
        const auto result = ::write(descriptor_, line.data() + written, line.size() - written);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) throw std::runtime_error("cannot append metric event: " + std::string(std::strerror(errno)));
        written += static_cast<std::size_t>(result);
    }
    if (durable_ && ::fdatasync(descriptor_) != 0) {
        throw std::runtime_error("cannot sync metric event: " + std::string(std::strerror(errno)));
    }
    return line.substr(0, line.size() - 1);
}

std::string metric_event_json(const MetricEvent &event)
{
    std::ostringstream output;
    output.imbue(std::locale::classic());
    output
        << "{\"best_development_score\":" << json_optional(event.best_development_score)
        << ",\"checkpoint_id\":" << (event.checkpoint_id ? json_escape(*event.checkpoint_id) : "null")
        << ",\"counters\":{\"accepted_samples\":" << event.counters.accepted_samples
        << ",\"completed_episodes\":" << event.counters.completed_episodes
        << ",\"completed_updates\":" << event.counters.completed_updates
        << ",\"environment_steps\":" << event.counters.environment_steps
        << ",\"simulation_ticks\":" << event.counters.simulation_ticks
        << "},\"elapsed_ns\":" << event.elapsed_ns
        << ",\"environment\":{\"company_profit\":" << json_optional(event.environment.company_profit)
        << ",\"invalid_actions\":" << event.environment.invalid_actions
        << ",\"mask_violations\":" << event.environment.mask_violations
        << ",\"mean_episode_length\":" << json_optional(event.environment.mean_episode_length)
        << ",\"mean_episode_return\":" << json_optional(event.environment.mean_episode_return)
        << ",\"passenger_deliveries\":" << json_optional(event.environment.passenger_deliveries)
        << ",\"resets\":" << event.environment.resets
        << ",\"routes\":" << json_optional(event.environment.routes)
        << ",\"vehicles\":" << json_optional(event.environment.vehicles)
        << "},\"event\":" << json_escape(event.event)
        << ",\"run\":{\"device\":" << json_escape(event.run.device)
        << ",\"environment_count\":" << event.run.environment_count
        << ",\"environment_version\":" << json_escape(event.run.environment_version)
        << ",\"openttd_version\":" << json_escape(event.run.openttd_version)
        << ",\"repository_commit\":" << json_escape(event.run.repository_commit)
        << ",\"run_name\":" << json_escape(event.run.run_name)
        << ",\"run_seed\":" << event.run.run_seed
        << "},\"schema_version\":\"" << kMetricSchemaVersion << "\""
        << ",\"sequence\":" << event.sequence
        << ",\"steps_per_second\":" << json_optional(event.steps_per_second)
        << ",\"system\":{\"cpu_utilization_percent\":" << json_optional(event.system.cpu_utilization_percent)
        << ",\"gpu_available\":" << (event.system.gpu_available ? "true" : "false")
        << ",\"gpu_memory_bytes\":" << json_optional(event.system.gpu_memory_bytes)
        << ",\"gpu_utilization_percent\":" << json_optional(event.system.gpu_utilization_percent)
        << ",\"process_memory_bytes\":" << json_optional(event.system.process_memory_bytes)
        << "},\"training\":{\"approximate_kl\":" << json_double(event.training.approximate_kl)
        << ",\"clip_fraction\":" << json_double(event.training.clip_fraction)
        << ",\"entropy\":" << json_double(event.training.entropy)
        << ",\"explained_variance\":" << json_double(event.training.explained_variance)
        << ",\"gradient_norm\":" << json_double(event.training.gradient_norm)
        << ",\"learning_rate\":" << json_double(event.training.learning_rate)
        << ",\"policy_loss\":" << json_double(event.training.policy_loss)
        << ",\"samples\":" << event.training.samples
        << ",\"update\":" << event.training.update
        << ",\"value_loss\":" << json_double(event.training.value_loss)
        << "},\"unix_time_ns\":" << event.unix_time_ns
        << ",\"warning_state\":" << json_escape(event.warning_state) << '}';
    return output.str();
}

std::string render_terminal_monitor(const MetricEvent &event, std::size_t width)
{
    const bool compact = width < 100;
    std::ostringstream output;
    if (compact) {
        output << event.run.run_name << " u=" << event.counters.completed_updates
               << " step=" << event.counters.environment_steps
               << " elapsed_ns=" << event.elapsed_ns
               << " sps=" << printable_optional(event.steps_per_second, 1)
               << " ret=" << printable_optional(event.environment.mean_episode_return)
               << " pi=" << std::fixed << std::setprecision(4) << event.training.policy_loss
               << " v=" << event.training.value_loss
               << " warn=" << event.warning_state;
        return output.str();
    }
    output << event.run.run_name << " | commit " << event.run.repository_commit << " | OpenTTD "
           << event.run.openttd_version << " | env " << event.run.environment_version << " | seed "
           << event.run.run_seed << " | nenv " << event.run.environment_count << " | " << event.run.device << '\n';
    output << "update " << event.counters.completed_updates << " | elapsed " << event.elapsed_ns << "ns | steps " << event.counters.environment_steps
           << " | steps/s " << printable_optional(event.steps_per_second, 1)
           << " | ticks " << event.counters.simulation_ticks << " | pi " << event.training.policy_loss
           << " | value " << event.training.value_loss << " | entropy " << event.training.entropy
           << " | kl " << event.training.approximate_kl << " | clip " << event.training.clip_fraction
           << " | ev " << event.training.explained_variance << " | lr " << event.training.learning_rate << '\n';
    output << "return " << printable_optional(event.environment.mean_episode_return)
           << " | length " << printable_optional(event.environment.mean_episode_length)
           << " | profit " << printable_optional(event.environment.company_profit)
           << " | passengers " << printable_optional(event.environment.passenger_deliveries)
           << " | vehicles " << printable_optional(event.environment.vehicles)
           << " | routes " << printable_optional(event.environment.routes)
           << " | invalid " << event.environment.invalid_actions
           << " | mask " << event.environment.mask_violations
           << " | resets " << event.environment.resets << '\n';
    output << "checkpoint " << (event.checkpoint_id ? *event.checkpoint_id : "n/a")
           << " | best " << printable_optional(event.best_development_score)
           << " | CPU " << printable_optional(event.system.cpu_utilization_percent, 1) << "%"
           << " | GPU " << (event.system.gpu_available ? printable_optional(event.system.gpu_utilization_percent, 1) + "%" : "n/a")
           << " | memory " << (event.system.process_memory_bytes ? std::to_string(*event.system.process_memory_bytes) : "n/a")
           << " | warning " << event.warning_state;
    return output.str();
}

} // namespace openttd_rl::training
