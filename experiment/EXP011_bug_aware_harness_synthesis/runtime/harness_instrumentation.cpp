#include "harness_instrumentation.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <limits>
#include <mutex>
#include <ostream>
#include <string>
#include <utility>

namespace hbfg {
namespace {

constexpr char kMetricsPathEnv[] = "HBFG_METRICS_PATH";
constexpr char kSnapshotIntervalEnv[] =
    "HBFG_METRICS_SNAPSHOT_INTERVAL";

constexpr char kRecordFormatVersion[] = "1.0";
constexpr char kRuntimeVersion[] = "1.0";

constexpr std::uint64_t kDefaultSnapshotInterval = 65536;

std::string ReadMetricsPath() {
  const char* value = std::getenv(kMetricsPathEnv);
  return value == nullptr ? std::string{} : std::string{value};
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
    InstrumentationRegistry* registry) noexcept
    : registry_(registry),
      uncaught_exceptions_on_entry_(
          std::uncaught_exceptions()) {}

IterationContext::~IterationContext() noexcept {
  if (registry_ == nullptr) {
    return;
  }

  const bool unwinding =
      std::uncaught_exceptions() >
      uncaught_exceptions_on_entry_;

  registry_->finish_iteration(unwinding);
}

IterationContext::IterationContext(
    IterationContext&& other) noexcept
    : registry_(std::exchange(other.registry_, nullptr)),
      uncaught_exceptions_on_entry_(
          other.uncaught_exceptions_on_entry_) {
  other.uncaught_exceptions_on_entry_ = 0;
}

void IterationContext::record(
    RuntimeSiteId site_id) noexcept {
  if (registry_ != nullptr) {
    registry_->record(site_id);
  }
}

void IterationContext::record_if(
    RuntimeSiteId site_id,
    bool condition) noexcept {
  if (condition && registry_ != nullptr) {
    registry_->record(site_id);
  }
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
  }
}

IterationContext InstrumentationRegistry::begin_iteration() noexcept {
  if (state_ == nullptr) {
    return IterationContext(nullptr);
  }

  state_->started_iterations.fetch_add(
      1U,
      std::memory_order_relaxed);

  return IterationContext(this);
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
