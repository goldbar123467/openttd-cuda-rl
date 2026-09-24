#include "live_checkpoint.h"

#include <array>
#include <bit>
#include <cerrno>
#include <fcntl.h>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <unistd.h>
#include <ATen/Context.h>
#include <torch/version.h>

namespace openttd_rl::development {
namespace {
using training::MultiModalPpoTrainer;

std::string identity(const MultiModalPpoTrainer &trainer)
{
    const auto &c = trainer.config();
    std::ostringstream out;
    out << "openttd-rl-development-trainer-checkpoint-1\n" << TORCH_VERSION << '\n'
        << training::architecture_name(trainer.architecture()) << '\n' << trainer.device() << '\n'
        << trainer.rng().ledger().run_seed << '\n' << std::hexfloat
        << c.gamma << ' ' << c.gae_lambda << ' ' << c.clip_epsilon << ' ' << c.value_coefficient << ' '
        << c.entropy_coefficient << ' ' << c.learning_rate << ' ' << c.adam_epsilon << ' '
        << c.max_gradient_norm << '\n' << c.rollout_length << ' ' << c.environment_count << ' '
        << c.minibatch_size << ' ' << c.optimization_epochs << '\n'
        << at::globalContext().deterministicCuDNN() << ' ' << at::globalContext().benchmarkCuDNN()
        << ' ' << torch::get_num_threads();
    return out.str();
}

void write_string(torch::serialize::OutputArchive &archive, const std::string &key, const std::string &value)
{
    archive.write(key, torch::from_blob(const_cast<char *>(value.data()),
        {static_cast<std::int64_t>(value.size())}, torch::kUInt8).clone(), true);
}

std::string read_string(torch::serialize::InputArchive &archive, const std::string &key)
{
    torch::Tensor value;
    archive.read(key, value, true);
    if (value.device().is_cuda() || value.scalar_type() != torch::kUInt8 || value.dim() != 1 ||
        value.numel() > 65536) throw std::invalid_argument("checkpoint string shape/type mismatch");
    value = value.contiguous();
    return {static_cast<const char *>(value.const_data_ptr()), static_cast<std::size_t>(value.numel())};
}

void check_model_and_optimizer(MultiModalPpoTrainer &trainer)
{
    for (const auto &parameter : trainer.model()->parameters()) {
        training::require_finite_tensor(parameter, "checkpoint model");
        if (parameter.device() != trainer.device()) throw std::invalid_argument("checkpoint parameter device mismatch");
    }
    for (const auto &entry : trainer.optimizer().state()) {
        const auto *state = dynamic_cast<const torch::optim::AdamParamState *>(entry.second.get());
        if (state == nullptr || state->step() < 0) throw std::invalid_argument("checkpoint Adam state invalid");
        for (const auto &value : {state->exp_avg(), state->exp_avg_sq()}) {
            training::require_finite_tensor(value, "checkpoint Adam moment");
            if (value.device() != trainer.device()) throw std::invalid_argument("checkpoint Adam device mismatch");
        }
    }
}

void sync_directory(const std::filesystem::path &path)
{
    const int fd = ::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (fd < 0) throw std::runtime_error("cannot open checkpoint directory");
    const int result = ::fsync(fd);
    (void)::close(fd);
    if (result != 0) throw std::runtime_error("cannot sync checkpoint directory");
}
} // namespace

void save_live_checkpoint(const std::filesystem::path &path, MultiModalPpoTrainer &trainer)
{
    if (!path.is_absolute() || !std::filesystem::is_directory(path.parent_path())) {
        throw std::invalid_argument("checkpoint requires an absolute path in an existing directory");
    }
    check_model_and_optimizer(trainer);
    torch::serialize::OutputArchive archive, model, optimizer;
    write_string(archive, "identity", identity(trainer));
    trainer.model()->save(model);
    trainer.optimizer().save(optimizer);
    archive.write("model", model);
    archive.write("optimizer", optimizer);
    const auto states = trainer.rng().mutable_states();
    for (std::size_t i = 0; i < states.size(); ++i) write_string(archive, "rng_" + std::to_string(i), states[i]);
    archive.write("torch_cpu_rng", at::globalContext().defaultGenerator(torch::kCPU).get_state(), true);
    if (trainer.device().is_cuda()) {
        archive.write("torch_cuda_rng", at::globalContext().defaultGenerator(trainer.device()).get_state(), true);
    }
    const auto &c = trainer.counters();
    const std::vector<std::int64_t> counters = {std::bit_cast<std::int64_t>(c.completed_updates),
        std::bit_cast<std::int64_t>(c.environment_steps), std::bit_cast<std::int64_t>(c.simulation_ticks),
        std::bit_cast<std::int64_t>(c.completed_episodes), std::bit_cast<std::int64_t>(c.accepted_samples),
        trainer.model()->is_training() ? 1 : 0};
    archive.write("counters", torch::tensor(counters, torch::kInt64), true);
    const auto temporary = path.string() + ".tmp-" + std::to_string(::getpid());
    const int fd = ::open(temporary.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) throw std::runtime_error("cannot exclusively create checkpoint temporary file");
    bool open = true;
    try {
        archive.save_to([fd](const void *data, std::size_t length) {
            std::size_t written = 0;
            while (written < length) {
                const auto result = ::write(fd, static_cast<const char *>(data) + written, length - written);
                if (result < 0 && errno == EINTR) continue;
                if (result <= 0) throw std::runtime_error("checkpoint write failed");
                written += static_cast<std::size_t>(result);
            }
            return written;
        });
        if (::fsync(fd) != 0) throw std::runtime_error("checkpoint sync failed");
        const int closed = ::close(fd);
        open = false;
        if (closed != 0) throw std::runtime_error("checkpoint close failed");
        // A hard link publishes atomically and fails if the target already exists.
        if (::link(temporary.c_str(), path.c_str()) != 0) throw std::runtime_error("checkpoint publication failed; never overwriting");
        (void)::unlink(temporary.c_str());
        sync_directory(path.parent_path());
    } catch (...) {
        if (open) (void)::close(fd);
        (void)::unlink(temporary.c_str());
        throw;
    }
}

void load_live_checkpoint(const std::filesystem::path &path, MultiModalPpoTrainer &trainer)
{
    if (!path.is_absolute() || std::filesystem::file_size(path) > 256U * 1024U * 1024U) {
        throw std::invalid_argument("checkpoint path or size invalid");
    }
    if (trainer.counters().completed_updates != 0 || trainer.counters().accepted_samples != 0) {
        throw std::invalid_argument("checkpoint load requires a fresh trainer");
    }
    torch::serialize::InputArchive archive, model, optimizer;
    archive.load_from(path.string());
    if (read_string(archive, "identity") != identity(trainer)) {
        throw std::invalid_argument("checkpoint configuration, runtime, seed, architecture or device mismatch");
    }
    std::array<std::string, 3> rng_states;
    for (std::size_t i = 0; i < rng_states.size(); ++i) rng_states[i] = read_string(archive, "rng_" + std::to_string(i));
    torch::Tensor counters, cpu_rng, cuda_rng;
    archive.read("counters", counters, true);
    if (counters.device().is_cuda() || counters.scalar_type() != torch::kInt64 || counters.sizes() != torch::IntArrayRef({6})) {
        throw std::invalid_argument("checkpoint counter shape/type mismatch");
    }
    counters = counters.contiguous();
    const auto *c = counters.const_data_ptr<std::int64_t>();
    if (c[5] != 0 && c[5] != 1) throw std::invalid_argument("checkpoint model mode invalid");
    archive.read("torch_cpu_rng", cpu_rng, true);
    if (trainer.device().is_cuda()) archive.read("torch_cuda_rng", cuda_rng, true);
    archive.read("model", model);
    archive.read("optimizer", optimizer);
    trainer.model()->load(model);
    trainer.optimizer().load(optimizer);
    check_model_and_optimizer(trainer);
    trainer.rng().restore_mutable_states(rng_states);
    trainer.counters() = {std::bit_cast<std::uint64_t>(c[0]), std::bit_cast<std::uint64_t>(c[1]),
        std::bit_cast<std::uint64_t>(c[2]), std::bit_cast<std::uint64_t>(c[3]), std::bit_cast<std::uint64_t>(c[4])};
    trainer.model()->train(c[5] != 0);
    auto cpu_generator = at::globalContext().defaultGenerator(torch::kCPU);
    cpu_generator.set_state(cpu_rng);
    if (trainer.device().is_cuda()) {
        auto cuda_generator = at::globalContext().defaultGenerator(trainer.device());
        cuda_generator.set_state(cuda_rng);
    }
}
} // namespace openttd_rl::development
