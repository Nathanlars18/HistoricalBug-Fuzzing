#ifndef HBFG_HARNESS_INSTRUMENTATION_H_
#define HBFG_HARNESS_INSTRUMENTATION_H_

#include <cstdint>
#include <memory>

namespace hbfg {

using RuntimeSiteId = std::uint32_t;

struct HarnessIdentity final {
  // Both null-terminated strings need to remain valid only during registry
  // construction because the registry copies them into private state.
  const char* artifact_id;
  const char* generation_key;
};

class InstrumentationRegistry;

class IterationContext final {
 public:
  ~IterationContext() noexcept;

  IterationContext(const IterationContext&) = delete;
  IterationContext& operator=(const IterationContext&) = delete;

  IterationContext(IterationContext&& other) noexcept;
  IterationContext& operator=(IterationContext&& other) = delete;

  void record(RuntimeSiteId site_id) noexcept;
  void record_if(RuntimeSiteId site_id, bool condition) noexcept;

 private:
  friend class InstrumentationRegistry;

  explicit IterationContext(
      InstrumentationRegistry* registry) noexcept;

  InstrumentationRegistry* registry_{nullptr};
  int uncaught_exceptions_on_entry_{0};
};

class InstrumentationRegistry final {
 public:
  // Construction is fail-open. If private runtime state cannot be
  // initialized, the registry remains disabled and all operations become
  // no-ops without changing harness behavior.
  InstrumentationRegistry(
      RuntimeSiteId site_count,
      HarnessIdentity identity) noexcept;
  ~InstrumentationRegistry() noexcept;

  InstrumentationRegistry(const InstrumentationRegistry&) = delete;
  InstrumentationRegistry& operator=(
      const InstrumentationRegistry&) = delete;

  InstrumentationRegistry(InstrumentationRegistry&&) = delete;
  InstrumentationRegistry& operator=(
      InstrumentationRegistry&&) = delete;

  [[nodiscard]]
  IterationContext begin_iteration() noexcept;

 private:
  friend class IterationContext;

  struct State;

  void record(RuntimeSiteId site_id) noexcept;
  void finish_iteration(bool unwinding) noexcept;

  std::unique_ptr<State> state_;
};

}  // namespace hbfg

#endif  // HBFG_HARNESS_INSTRUMENTATION_H_
