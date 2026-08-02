#include <cerrno>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

#include <torch/torch.h>

#include "openttd_rl/training/evaluation_model.h"

namespace {

struct Options {
    std::filesystem::path python;
    std::filesystem::path script;
    std::filesystem::path source_package;
    std::filesystem::path output_dir;
    std::filesystem::path contract;
    std::string source_package_id;
    std::string architecture;
    std::string repository_commit;
};

Options parse_options(int argc, char **argv)
{
    Options result;
    for (int index = 1; index < argc; index += 2) {
        if (index + 1 >= argc) throw std::invalid_argument("M10 export option lacks a value");
        const std::string_view option(argv[index]);
        const std::string value(argv[index + 1]);
        if (option == "--python") result.python = value;
        else if (option == "--script") result.script = value;
        else if (option == "--source-package") result.source_package = value;
        else if (option == "--source-package-id") result.source_package_id = value;
        else if (option == "--architecture") result.architecture = value;
        else if (option == "--output-dir") result.output_dir = value;
        else if (option == "--contract") result.contract = value;
        else if (option == "--repository-commit") result.repository_commit = value;
        else throw std::invalid_argument("unknown M10 export option: " + std::string(option));
    }
    for (const auto *path : {&result.python, &result.script, &result.source_package, &result.output_dir, &result.contract}) {
        if (!path->is_absolute()) throw std::invalid_argument("all M10 export paths must be absolute");
    }
    if (!std::filesystem::is_regular_file(result.python) || !std::filesystem::is_regular_file(result.script) ||
        !std::filesystem::is_regular_file(result.contract) || !std::filesystem::is_directory(result.source_package) ||
        std::filesystem::exists(result.output_dir) || result.source_package.filename() != result.source_package_id ||
        result.architecture.empty() || result.repository_commit.size() != 40U) {
        throw std::invalid_argument("M10 export configuration is incomplete or invalid");
    }
    return result;
}

void run_converter(const Options &options)
{
    const std::vector<std::string> arguments = {
        options.python.string(), options.script.string(),
        "--source-package", options.source_package.string(),
        "--source-package-id", options.source_package_id,
        "--architecture", options.architecture,
        "--output-dir", options.output_dir.string(),
        "--contract", options.contract.string(),
        "--repository-commit", options.repository_commit,
    };
    std::vector<char *> pointers;
    pointers.reserve(arguments.size() + 1U);
    for (const auto &argument : arguments) pointers.push_back(const_cast<char *>(argument.c_str()));
    pointers.push_back(nullptr);
    const pid_t child = ::fork();
    if (child < 0) throw std::runtime_error("cannot fork M10 converter: " + std::string(std::strerror(errno)));
    if (child == 0) {
        ::execv(options.python.c_str(), pointers.data());
        std::cerr << "M10_EXPORT_ORCHESTRATOR=FAIL execv: " << std::strerror(errno) << '\n';
        _exit(127);
    }
    int status = 0;
    while (::waitpid(child, &status, 0) < 0) {
        if (errno == EINTR) continue;
        throw std::runtime_error("cannot wait for M10 converter");
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        throw std::runtime_error("pinned M10 converter failed");
    }
}

} // namespace

int main(int argc, char **argv)
{
    try {
        const auto options = parse_options(argc, argv);
        torch::set_num_threads(2);
        openttd_rl::training::ReadOnlyEvaluationPolicy source(options.source_package, 0);
        if (openttd_rl::training::architecture_name(source.architecture()) != options.architecture ||
            source.package_id() != options.source_package_id) {
            throw std::invalid_argument("native source package identity disagrees with export request");
        }
        const auto before = source.state_sha256();
        run_converter(options);
        if (!std::filesystem::is_regular_file(options.output_dir / "model.onnx") ||
            !std::filesystem::is_regular_file(options.output_dir / "export-metadata.json")) {
            throw std::runtime_error("converter did not produce the bounded export inventory");
        }
        if (source.state_sha256() != before) throw std::runtime_error("M10 export mutated native source state");
        std::cout << "M10_EXPORT_ORCHESTRATOR=PASS architecture=" << options.architecture
                  << " package=" << source.package_id() << " source_state=" << before << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "M10_EXPORT_ORCHESTRATOR=FAIL " << error.what() << '\n';
        return 1;
    }
}
