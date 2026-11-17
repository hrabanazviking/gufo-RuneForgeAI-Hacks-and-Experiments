#ifndef GUFO_CLI_MODEL_ENV_HPP_
#define GUFO_CLI_MODEL_ENV_HPP_

#include <cstdlib>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>

namespace gufo::cli {

/// Environment variables that select models the Ollama way: a models
/// directory that holds files by name, and a default model for
/// commands that run without --model. No configuration file is read.
inline constexpr std::string_view kModelsDirEnv = "GUFO_MODELS_DIR";
inline constexpr std::string_view kDefaultModelEnv = "GUFO_DEFAULT_MODEL";

/// The directory named by GUFO_MODELS_DIR, or std::nullopt when the
/// variable is unset or empty.
[[nodiscard]] inline std::optional<std::filesystem::path> ModelsDirFromEnv() {
  const char* value = std::getenv("GUFO_MODELS_DIR");
  if (value == nullptr || *value == '\0') {
    return std::nullopt;
  }
  return std::filesystem::path(value);
}

/// The model named by GUFO_DEFAULT_MODEL, or std::nullopt when the
/// variable is unset or empty. The value is a path or a bare file
/// name; ResolveModelReference gives it a concrete location.
[[nodiscard]] inline std::optional<std::string> DefaultModelFromEnv() {
  const char* value = std::getenv("GUFO_DEFAULT_MODEL");
  if (value == nullptr || *value == '\0') {
    return std::nullopt;
  }
  return std::string(value);
}

/// Resolves a model reference to the path a command loads. Absolute
/// paths and references with a directory component are used as given.
/// A bare file name resolves inside GUFO_MODELS_DIR when the variable
/// is set, and is used as given otherwise.
[[nodiscard]] inline std::filesystem::path ResolveModelReference(
    std::string_view reference) {
  const std::filesystem::path path(reference);
  if (path.is_absolute() || path.has_parent_path()) {
    return path;
  }
  if (const auto models_dir = ModelsDirFromEnv()) {
    return *models_dir / path;
  }
  return path;
}

/// Applies the model environment to a command's --model value, in
/// place. An explicit value always wins and is resolved through
/// ResolveModelReference. An empty value takes GUFO_DEFAULT_MODEL
/// when the variable is set; the default must name an existing
/// regular file, and when it does not, returns false with *error
/// naming the variable, its value, and the resolved path — there is
/// no silent fallback. When neither an explicit value nor a default
/// exists, returns true with the value still empty, and the caller
/// keeps its own missing-model error.
[[nodiscard]] inline bool ResolveEffectiveModelPath(std::string* model_path,
                                                    std::string* error) {
  if (!model_path->empty()) {
    *model_path = ResolveModelReference(*model_path).string();
    return true;
  }
  const auto default_model = DefaultModelFromEnv();
  if (!default_model.has_value()) {
    return true;
  }
  const std::filesystem::path resolved = ResolveModelReference(*default_model);
  std::error_code ec;
  if (!std::filesystem::is_regular_file(resolved, ec)) {
    *error = std::string(kDefaultModelEnv) + " is set to '" + *default_model +
             "' but no model file exists at '" + resolved.string() + "'";
    return false;
  }
  *model_path = resolved.string();
  return true;
}

}  // namespace gufo::cli

#endif  // GUFO_CLI_MODEL_ENV_HPP_
