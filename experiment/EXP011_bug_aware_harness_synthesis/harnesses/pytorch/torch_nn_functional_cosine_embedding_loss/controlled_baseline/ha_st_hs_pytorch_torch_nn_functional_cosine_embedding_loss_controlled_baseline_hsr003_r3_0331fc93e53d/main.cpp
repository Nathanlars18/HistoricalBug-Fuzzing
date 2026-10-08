/*
 * HistoricalBug-Fuzzing deterministic LibFuzzer harness template.
 *
 * This file defines only the stable harness structure.
 * Generated code is inserted by generate_harness.py.
 */

#include <cstddef>
#include <cstdint>

#include <torch/torch.h>

#include "fuzzer_utils.h"
#include "harness_instrumentation.h"

#include <c10/util/Exception.h>
#include <cstdint>
#include <cstdio>
#include <optional>
#include <utility>
#include <vector>

namespace {

constexpr std::uint32_t kHbfgInstrumentationSiteCount =
    8;

constexpr char kHbfgArtifactId[] =
    "ha_st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r3_0331fc93e53d";

constexpr char kHbfgGenerationKey[] =
    "0331fc93e53d6785f2498eb024ad9a78d7f9735fee9b0f856ef7d38e7774da63";

}  // namespace



extern "C" int LLVMFuzzerTestOneInput(
    const std::uint8_t* Data,
    std::size_t Size) {
  /* HBFG_REGION_BEGIN:fuzzer_entry */

  static hbfg::InstrumentationRegistry hbfg_registry{
      kHbfgInstrumentationSiteCount,
      hbfg::HarnessIdentity{
          kHbfgArtifactId,
          kHbfgGenerationKey,
      }};

  if (Size < 1) {
    return 0;
  }

  std::size_t hbfg_offset = 1;

  auto hbfg_iteration = hbfg_registry.begin_iteration();

  /* HBFG_REGION_END:fuzzer_entry */

  /* HBFG_REGION_BEGIN:branch_dispatch */

  {
    const std::uint8_t hbfg_selector = Data[0];

    if (hbfg_selector <= 255) {
      hbfg_iteration.record(0);  // HBFG_EVENT:ins_0001
      // HBFG_SEGMENT_BEGIN:seg_br_default_001
      hbfg_iteration.record_if(1, static_cast<bool>((Size < hbfg_offset || Size - hbfg_offset < 3U)));  // HBFG_EVENT:ins_0002
      if ((Size < hbfg_offset || Size - hbfg_offset < 3U)) { return 0; }
      std::size_t hbfg_br_default_value_002 = hbfg_offset;
      const std::int64_t hbfg_br_default_value_001_rows = 0 + static_cast<std::int64_t>(Data[hbfg_br_default_value_002++] % 3U);
      const std::int64_t hbfg_br_default_value_001_cols = 0 + static_cast<std::int64_t>(Data[hbfg_br_default_value_002++] % 3U);
      const std::int64_t hbfg_br_default_value_001_fill = static_cast<std::int64_t>(Data[hbfg_br_default_value_002++] % 17U) - 8;
      auto hbfg_br_default_value_001 = torch::full({hbfg_br_default_value_001_rows, hbfg_br_default_value_001_cols}, hbfg_br_default_value_001_fill, torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(2);  // HBFG_EVENT:ins_0003
      // HBFG_SEGMENT_END:seg_br_default_001
      // HBFG_SEGMENT_BEGIN:seg_br_default_002
      std::size_t hbfg_br_default_value_004 = hbfg_br_default_value_002;
      auto hbfg_br_default_value_003 = torch::full(hbfg_br_default_value_001.sizes().vec(), ((hbfg_br_default_value_004 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_default_value_004++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(3);  // HBFG_EVENT:ins_0004
      // HBFG_SEGMENT_END:seg_br_default_002
      // HBFG_SEGMENT_BEGIN:seg_br_default_003
      std::size_t hbfg_br_default_value_006 = hbfg_br_default_value_004;
      auto hbfg_br_default_value_005 = torch::full(std::vector<std::int64_t>{hbfg_br_default_value_001.dim() > 0 ? hbfg_br_default_value_001.size(0) : 0}, ((hbfg_br_default_value_006 < Size) ? ((Data[hbfg_br_default_value_006++] & 1U) ? 1 : -1) : 1), torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(4);  // HBFG_EVENT:ins_0005
      // HBFG_SEGMENT_END:seg_br_default_003
      // HBFG_SEGMENT_BEGIN:seg_br_default_004
      hbfg_iteration.record(5);  // HBFG_EVENT:ins_0006
      std::optional<decltype(at::cosine_embedding_loss(hbfg_br_default_value_001, hbfg_br_default_value_003, hbfg_br_default_value_005))> hbfg_call_result_step_004;
      try {
      hbfg_call_result_step_004.emplace(at::cosine_embedding_loss(hbfg_br_default_value_001, hbfg_br_default_value_003, hbfg_br_default_value_005));
      } catch (const c10::Error& hbfg_error) {
      hbfg_iteration.record(6);  // HBFG_EVENT:ins_0007
      hbfg_iteration.log_target_api_exception(hbfg_error.what_without_backtrace());
      return 0;
      }
      hbfg_iteration.record(7);  // HBFG_EVENT:ins_0008
      auto hbfg_br_default_value_007 = std::move(*hbfg_call_result_step_004);
      // HBFG_SEGMENT_END:seg_br_default_004
    }
  }

  /* HBFG_REGION_END:branch_dispatch */

  /* HBFG_REGION_BEGIN:iteration_exit */

  return 0;

  /* HBFG_REGION_END:iteration_exit */
}
