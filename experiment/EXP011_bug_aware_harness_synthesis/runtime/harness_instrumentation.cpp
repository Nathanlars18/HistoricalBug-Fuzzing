#include "harness_instrumentation.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <limits>
#include <mutex>
#include <ostream>
#include <string>
#include <utility>
#include <filesystem>
#include <stdexcept>

namespace hbfg {
namespace {

constexpr char kMetricsPathEnv[] = "HBFG_METRICS_PATH";
constexpr char kSnapshotIntervalEnv[] =
    "HBFG_METRICS_SNAPSHOT_INTERVAL";

constexpr char kRecordFormatVersion[] = "1.0";
constexpr char kRuntimeVersion[] = "1.1";

constexpr std::uint64_t kDefaultSnapshotInterval = 65536;
constexpr std::uint64_t kTargetExceptionLogLimit = 16;
constexpr int kTargetExceptionMessageLimit = 1024;

std::string ReadMetricsPath() {
  const char* value = std::getenv(kMetricsPathEnv);
  return value == nullptr ? std::string{} : std::string{value};
}

std::uint64_t ReadCaptureLimit() noexcept {
  const char* value = std::getenv("HBFG_CANDIDATE_SAMPLE_LIMIT");
  if (value == nullptr) return 64U;
  try {
    std::string text(value);
    if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos) return 64U;
    return std::stoull(text);
  } catch (...) { return 64U; }
}

std::uint64_t ReadSnapshotInterval() noexcept {
  const char* value = std::getenv(kSnapshotIntervalEnv);

  if (value == nullptr || *value == '\0') {
    return kDefaultSnapshotInterval;
  }

  std::uint64_t result = 0;

  for (const char* cursor = value; *cursor != '\0'; ++cursor) {
    if (*cursor < '0' || *cursor > '9') {
      return kDefaultSnapshotInterval;
    }

    const std::uint64_t digit =
        static_cast<std::uint64_t>(*cursor - '0');

    if (result >
        (std::numeric_limits<std::uint64_t>::max() - digit) / 10U) {
      return kDefaultSnapshotInterval;
    }

    result = result * 10U + digit;
  }

  return result;
}

void WriteJsonString(
    std::ostream& output,
    const std::string& value) {
  static constexpr char kHex[] = "0123456789abcdef";

  output.put('"');

  for (unsigned char character : value) {
    switch (character) {
      case '"':
        output << "\\\"";
        break;
      case '\\':
        output << "\\\\";
        break;
      case '\b':
        output << "\\b";
        break;
      case '\f':
        output << "\\f";
        break;
      case '\n':
        output << "\\n";
        break;
      case '\r':
        output << "\\r";
        break;
      case '\t':
        output << "\\t";
        break;
      default:
        if (character < 0x20U) {
          output << "\\u00"
                 << kHex[(character >> 4U) & 0x0FU]
                 << kHex[character & 0x0FU];
        } else {
          output.put(static_cast<char>(character));
        }
        break;
    }
  }

  output.put('"');
}

}  // namespace

struct InstrumentationRegistry::State final {
  State(
      RuntimeSiteId requested_site_count,
      HarnessIdentity identity)
      : artifact_id(identity.artifact_id),
        generation_key(identity.generation_key),
        site_count(requested_site_count),
        output_path(ReadMetricsPath()),
        snapshot_interval(ReadSnapshotInterval()) {
    if (site_count > 0U) {
      site_counts =
          std::make_unique<std::atomic<std::uint64_t>[]>(site_count);

      for (RuntimeSiteId site_id = 0U;
           site_id < site_count;
           ++site_id) {
        site_counts[site_id].store(0U, std::memory_order_relaxed);
      }
    }
  }

  void maybe_export_periodic(
      std::uint64_t finished_iteration_count) noexcept {
    if (output_path.empty() ||
        snapshot_interval == 0U ||
        finished_iteration_count % snapshot_interval != 0U) {
      return;
    }

    export_snapshot(false);
  }

  void export_snapshot(bool final_snapshot) noexcept {
    if (output_path.empty()) {
      return;
    }

    try {
      std::lock_guard<std::mutex> lock(export_mutex);

      if (!write_snapshot_unlocked(final_snapshot)) {
        report_export_failure();
      }
    } catch (...) {
      report_export_failure();
    }
  }

  std::string artifact_id;
  std::string generation_key;
  RuntimeSiteId site_count{0U};
  std::string output_path;
  std::uint64_t snapshot_interval{0U};

  std::unique_ptr<std::atomic<std::uint64_t>[]> site_counts;

  std::atomic<std::uint64_t> started_iterations{0U};
  std::atomic<std::uint64_t> finished_iterations{0U};
  std::atomic<std::uint64_t> unwound_iterations{0U};
  std::atomic<std::uint64_t> invalid_site_records{0U};
  std::atomic<std::uint64_t> export_failures{0U};
  std::atomic<std::uint64_t> target_exception_log_attempts{0U};
  std::atomic<std::uint64_t> capture_attempts{0U};
  std::atomic<std::uint64_t> captured{0U};
  std::atomic<std::uint64_t> capture_failures{0U};
  std::atomic<std::uint64_t> exception_capture_attempts{0U};
  std::atomic<std::uint64_t> oracle_capture_attempts{0U};
  const std::uint64_t capture_limit{ReadCaptureLimit()};
  const std::string capture_dir{std::getenv("HBFG_CANDIDATE_DIR") == nullptr ? "" : std::getenv("HBFG_CANDIDATE_DIR")};
  const std::string trace_path{std::getenv("HBFG_REPLAY_TRACE") == nullptr ? "" : std::getenv("HBFG_REPLAY_TRACE")};

  std::mutex export_mutex;

 private:
  bool write_snapshot_unlocked(bool final_snapshot) {
    const std::uint64_t started =
        started_iterations.load(std::memory_order_relaxed);
    const std::uint64_t finished =
        finished_iterations.load(std::memory_order_relaxed);
    const std::uint64_t unwound =
        unwound_iterations.load(std::memory_order_relaxed);

    const std::string temporary_path = output_path + ".tmp";

    std::ofstream output(
        temporary_path,
        std::ios::out | std::ios::trunc | std::ios::binary);

    if (!output.is_open()) {
      return false;
    }

    output << "{\n";
    output << "  \"record_format_version\": \""
           << kRecordFormatVersion << "\",\n";
    output << "  \"runtime_version\": \""
           << kRuntimeVersion << "\",\n";

    output << "  \"artifact_id\": ";
    WriteJsonString(output, artifact_id);
    output << ",\n";

    output << "  \"generation_key\": ";
    WriteJsonString(output, generation_key);
    output << ",\n";

    output << "  \"snapshot_kind\": \""
           << (final_snapshot ? "final" : "periodic")
           << "\",\n";
    output << "  \"snapshot_interval\": "
           << snapshot_interval << ",\n";
    output << "  \"site_count\": "
           << site_count << ",\n";
    output << "  \"started_iterations\": "
           << started << ",\n";
    output << "  \"finished_iterations\": "
           << finished << ",\n";
    output << "  \"unwound_iterations\": "
           << unwound << ",\n";
    output << "  \"invalid_site_records\": "
           << invalid_site_records.load(std::memory_order_relaxed)
           << ",\n";
    output << "  \"export_failures\": "
           << export_failures.load(std::memory_order_relaxed)
           << ",\n";
    output << "  \"site_counts\": [";

    if (site_count != 0U) {
      output << "\n";

      for (RuntimeSiteId site_id = 0U;
           site_id < site_count;
           ++site_id) {
        output << "    "
               << site_counts[site_id].load(
                      std::memory_order_relaxed);

        if (site_id + 1U != site_count) {
          output << ",";
        }

        output << "\n";
      }

      output << "  ";
    }

    output << "]\n";
    output << "}\n";

    output.flush();

    if (!output.good()) {
      output.close();
      std::remove(temporary_path.c_str());
      return false;
    }

    output.close();

    if (output.fail()) {
      std::remove(temporary_path.c_str());
      return false;
    }

    if (std::rename(
            temporary_path.c_str(),
            output_path.c_str()) != 0) {
      std::remove(temporary_path.c_str());
      return false;
    }

    return true;
  }

  void report_export_failure() noexcept {
    export_failures.fetch_add(1U, std::memory_order_relaxed);
  }
};

IterationContext::IterationContext(
    InstrumentationRegistry* registry, const std::uint8_t* data,
    std::size_t size, std::uint64_t iteration) noexcept
    : registry_(registry),
      uncaught_exceptions_on_entry_(
          std::uncaught_exceptions()), data_(data), size_(size), iteration_(iteration) {}

IterationContext::~IterationContext() noexcept {
  if (registry_ == nullptr) {
    return;
  }

  const bool unwinding =
      std::uncaught_exceptions() >
      uncaught_exceptions_on_entry_;

  registry_->trace(*this);
  registry_->finish_iteration(unwinding);
}

IterationContext::IterationContext(
    IterationContext&& other) noexcept
    : registry_(std::exchange(other.registry_, nullptr)),
      uncaught_exceptions_on_entry_(
          other.uncaught_exceptions_on_entry_), data_(other.data_), size_(other.size_),
      iteration_(other.iteration_), sites_(other.sites_), sites_used_(other.sites_used_) {
  other.uncaught_exceptions_on_entry_ = 0;
}

void IterationContext::record(
    RuntimeSiteId site_id) noexcept {
  if (registry_ != nullptr) {
    registry_->record(site_id);
    if (sites_used_ < sites_.size()) sites_[sites_used_++] = site_id;
    // Replay-only write-ahead evidence: a fatal target signal may prevent
    // IterationContext destruction. Normal fuzzing has no trace I/O here.
    registry_->trace(*this);
  }
}

void IterationContext::record_if(
    RuntimeSiteId site_id,
    bool condition) noexcept {
  if (condition) record(site_id);
}

InstrumentationRegistry::InstrumentationRegistry(
    RuntimeSiteId site_count,
    HarnessIdentity identity) noexcept {
  if (identity.artifact_id == nullptr ||
      identity.generation_key == nullptr ||
      identity.artifact_id[0] == '\0' ||
      identity.generation_key[0] == '\0') {
    return;
  }

  try {
    state_ = std::make_unique<State>(site_count, identity);
  } catch (...) {
    state_.reset();
  }
}

InstrumentationRegistry::~InstrumentationRegistry() noexcept {
  if (state_ != nullptr) {
    state_->export_snapshot(true);
    if (!state_->capture_dir.empty()) {
      try {
        std::ofstream out(state_->capture_dir + "/capture_summary.json");
        out << "{\"attempts\":" << state_->capture_attempts.load()
            << ",\"saved\":" << state_->captured.load()
            << ",\"failures\":" << state_->capture_failures.load()
            << ",\"exception_attempts\":" << state_->exception_capture_attempts.load()
            << ",\"oracle_attempts\":" << state_->oracle_capture_attempts.load()
            << ",\"limit_per_kind\":" << state_->capture_limit << ",\"complete\":true}";
      } catch (...) {}
    }
  }
}

void IterationContext::log_target_api_exception(
    const char* message) noexcept {
  if (registry_ != nullptr) {
    registry_->log_target_api_exception(message);
    capture_anomaly("target_exception", message);
  }
}

void IterationContext::capture_anomaly(const char* kind, const char* message) noexcept {
  if (registry_ != nullptr) registry_->capture(*this, kind, message);
}

void InstrumentationRegistry::trace(const IterationContext& context) noexcept {
  if (state_ == nullptr || state_->trace_path.empty()) return;
  try {
    std::ofstream out(state_->trace_path, std::ios::app);
    static constexpr char kHex[] = "0123456789abcdef";
    out << "{\"iteration\":" << context.iteration_ << ",\"input_hex\":\"";
    for (std::size_t i = 0; context.data_ != nullptr && i < context.size_; ++i) {
      const auto byte = context.data_[i];
      out.put(kHex[(byte >> 4U) & 0x0fU]);
      out.put(kHex[byte & 0x0fU]);
    }
    out << "\",\"sites_truncated\":"
        << (context.sites_used_ == context.sites_.size() ? "true" : "false")
        << ",\"runtime_site_ids\":[";
    for (std::size_t i = 0; i < context.sites_used_; ++i) {
      if (i != 0) out.put(',');
      out << context.sites_[i];
    }
    out << "]}\n";
    out.flush();
  } catch (...) {}
}

void InstrumentationRegistry::capture(const IterationContext& context, const char* kind, const char* message) noexcept {
  if (state_ == nullptr || state_->capture_dir.empty() || (context.data_ == nullptr && context.size_ != 0U)) return;
  const auto ordinal = state_->capture_attempts.fetch_add(1U);
  // Separate first-N limits prevent ordinary exceptions from consuming Oracle samples.
  const bool is_oracle = kind != nullptr && std::strcmp(kind, "oracle_failure") == 0;
  const auto kind_ordinal = (is_oracle ? state_->oracle_capture_attempts : state_->exception_capture_attempts).fetch_add(1U);
  if (kind_ordinal >= state_->capture_limit) return;
  try {
    const std::string base = state_->capture_dir + "/event_" + std::to_string(ordinal);
    std::ofstream input(base + ".input", std::ios::binary);
    if (context.size_ != 0U) input.write(reinterpret_cast<const char*>(context.data_), context.size_);
    input.close();
    if (!input) throw std::runtime_error("input capture failed");
    std::ofstream out(base + ".json");
    out << "{\"capture_version\":\"1.0\",\"kind\":";
    WriteJsonString(out, kind == nullptr ? "unknown" : kind);
    out << ",\"message\":";
    WriteJsonString(out, std::string(message == nullptr ? "" : message).substr(0, 4096));
    out << ",\"artifact_id\":"; WriteJsonString(out, state_->artifact_id);
    out << ",\"iteration_index\":" << context.iteration_
        << ",\"sites_truncated\":" << (context.sites_used_ == context.sites_.size() ? "true" : "false")
        << ",\"runtime_sites\":[";
    for (std::size_t i = 0; i < context.sites_used_; ++i) {
      if (i) out << ',';
      out << context.sites_[i];
    }
    out << "]}\n"; out.flush();
    if (!out) throw std::runtime_error("event capture failed");
    state_->captured.fetch_add(1U);
    if (is_oracle) {
      std::fprintf(stderr, "HBFG_ORACLE_FAILURE=%.*s\n",
                   kTargetExceptionMessageLimit,
                   message == nullptr ? "" : message);
    }
  } catch (...) {
    state_->capture_failures.fetch_add(1U);
    std::fputs("HBFG_CAPTURE_FAILED\n", stderr);
  }
}

IterationContext InstrumentationRegistry::begin_iteration(const std::uint8_t* data, std::size_t size) noexcept {
  if (state_ == nullptr) {
    return IterationContext(nullptr);
  }

  const auto iteration = state_->started_iterations.fetch_add(
      1U,
      std::memory_order_relaxed);

  return IterationContext(this, data, size, iteration);
}

void InstrumentationRegistry::record(
    RuntimeSiteId site_id) noexcept {
  if (state_ == nullptr) {
    return;
  }

  if (site_id >= state_->site_count) {
    state_->invalid_site_records.fetch_add(
        1U,
        std::memory_order_relaxed);
    return;
  }

  state_->site_counts[site_id].fetch_add(
      1U,
      std::memory_order_relaxed);
}

void InstrumentationRegistry::log_target_api_exception(
    const char* message) noexcept {
  if (state_ == nullptr) {
    return;
  }
  const std::uint64_t attempt =
      state_->target_exception_log_attempts.fetch_add(
          1U, std::memory_order_relaxed);
  if (attempt >= kTargetExceptionLogLimit) {
    return;
  }
  const char* safe_message = message == nullptr ? "" : message;
  std::fprintf(
      stderr,
      "HBFG_TARGET_API_EXCEPTION=%.*s\n",
      kTargetExceptionMessageLimit,
      safe_message);
}

void InstrumentationRegistry::finish_iteration(
    bool unwinding) noexcept {
  if (state_ == nullptr) {
    return;
  }

  if (unwinding) {
    state_->unwound_iterations.fetch_add(
        1U,
        std::memory_order_relaxed);
    return;
  }

  const std::uint64_t finished_iteration_count =
      state_->finished_iterations.fetch_add(
          1U,
          std::memory_order_relaxed) +
      1U;

  state_->maybe_export_periodic(finished_iteration_count);
}

}  // namespace hbfg
