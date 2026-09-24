#pragma once

// Development archive I/O using the same no-overwrite publication as V1.
#include <cerrno>
#include <filesystem>
#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <torch/torch.h>

namespace openttd_rl::development {
inline void checkpoint_string(torch::serialize::OutputArchive &archive, const std::string &key, const std::string &value)
{
    archive.write(key, torch::from_blob(const_cast<char *>(value.data()),
        {static_cast<int64_t>(value.size())}, torch::kUInt8).clone(), true);
}

inline std::string checkpoint_string(torch::serialize::InputArchive &archive, const std::string &key)
{
    torch::Tensor value;
    archive.read(key, value, true);
    if (!value.device().is_cpu() || value.scalar_type() != torch::kUInt8 || value.dim() != 1 || value.numel() > 65536)
        throw std::invalid_argument("checkpoint string shape/type invalid");
    value = value.contiguous();
    return {static_cast<const char *>(value.const_data_ptr()), static_cast<size_t>(value.numel())};
}

inline void publish_checkpoint(torch::serialize::OutputArchive &archive, const std::filesystem::path &path)
{
    if (!path.is_absolute() || !std::filesystem::is_directory(path.parent_path()))
        throw std::invalid_argument("checkpoint requires an absolute path in an existing directory");
    const auto temporary = path.string() + ".tmp-" + std::to_string(::getpid());
    const int fd = ::open(temporary.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) throw std::runtime_error("cannot exclusively create checkpoint temporary file");
    bool open = true;
    try {
        archive.save_to([fd](const void *data, size_t length) {
            size_t written = 0;
            while (written < length) {
                const auto result = ::write(fd, static_cast<const char *>(data) + written, length - written);
                if (result < 0 && errno == EINTR) continue;
                if (result <= 0) throw std::runtime_error("checkpoint write failed");
                written += static_cast<size_t>(result);
            }
            return written;
        });
        if (::fsync(fd) != 0) throw std::runtime_error("checkpoint sync failed");
        const int closed = ::close(fd);
        open = false;
        if (closed != 0) throw std::runtime_error("checkpoint close failed");
        if (::link(temporary.c_str(), path.c_str()) != 0)
            throw std::runtime_error("checkpoint publication failed; never overwriting");
        (void)::unlink(temporary.c_str());
        const int directory = ::open(path.parent_path().c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (directory < 0) throw std::runtime_error("cannot open checkpoint directory");
        const int synced = ::fsync(directory);
        (void)::close(directory);
        if (synced != 0) throw std::runtime_error("cannot sync checkpoint directory");
    } catch (...) {
        if (open) (void)::close(fd);
        (void)::unlink(temporary.c_str());
        throw;
    }
}
} // namespace openttd_rl::development
