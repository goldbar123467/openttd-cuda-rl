#ifndef OPENTTD_RL_V2_M23_ONNX_H
#define OPENTTD_RL_V2_M23_ONNX_H

#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include <onnxruntime_cxx_api.h>

namespace openttd_rl::v2 {

struct M23OnnxOutput {
    std::vector<float> program_logits;
    std::vector<float> program_value;
    std::vector<float> next_hidden;
    std::vector<std::int64_t> greedy_program;
};

class M23OnnxModel {
public:
    M23OnnxModel(std::filesystem::path model_path, std::string architecture_id);

    M23OnnxModel(const M23OnnxModel &) = delete;
    M23OnnxModel &operator=(const M23OnnxModel &) = delete;
    M23OnnxModel(M23OnnxModel &&) = delete;
    M23OnnxModel &operator=(M23OnnxModel &&) = delete;

    [[nodiscard]] M23OnnxOutput run(
        std::uint32_t batch,
        const std::vector<float> &public_features,
        const std::vector<std::uint8_t> &program_mask,
        const std::vector<float> &hidden_state,
        const std::vector<std::uint8_t> &recurrent_reset);

    [[nodiscard]] const std::string &architecture_id() const noexcept { return architecture_id_; }
    [[nodiscard]] const std::filesystem::path &model_path() const noexcept { return model_path_; }

private:
    std::filesystem::path model_path_;
    std::string architecture_id_;
    Ort::Env environment_;
    Ort::SessionOptions options_;
    std::unique_ptr<Ort::Session> session_;
};

} // namespace openttd_rl::v2

#endif
