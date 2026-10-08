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
    16;

constexpr char kHbfgArtifactId[] =
    "ha_st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_controlled_baseline_hsr003_r3_2a90c4c4502e";

constexpr char kHbfgGenerationKey[] =
    "2a90c4c4502e0e8e3d2e701d90db8a7180b6160dab7e1c0f8a97f1d55afb6ab7";

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

  auto hbfg_iteration = hbfg_registry.begin_iteration(Data, Size);

  if (Size < 1) {
    return 0;
  }

  std::size_t hbfg_offset = 1;

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
      const bool hbfg_br_default_et_pytorch_cosine_embedding_loss_shape_mismatch = (!hbfg_br_default_value_001.sizes().equals(hbfg_br_default_value_003.sizes()));
      hbfg_iteration.record(5);  // HBFG_EVENT:ins_0006
      hbfg_iteration.record_if(6, static_cast<bool>(hbfg_br_default_et_pytorch_cosine_embedding_loss_shape_mismatch));  // HBFG_EVENT:ins_0007
      hbfg_iteration.record_if(7, static_cast<bool>(false));  // HBFG_EVENT:ins_0008
      hbfg_iteration.record_if(8, static_cast<bool>(false));  // HBFG_EVENT:ins_0009
      const bool hbfg_br_default_et_pytorch_cosine_embedding_loss_any_input_empty = (hbfg_br_default_value_001.numel() == 0 || hbfg_br_default_value_003.numel() == 0);
      hbfg_iteration.record(9);  // HBFG_EVENT:ins_0010
      hbfg_iteration.record_if(10, static_cast<bool>(hbfg_br_default_et_pytorch_cosine_embedding_loss_any_input_empty));  // HBFG_EVENT:ins_0011
      hbfg_iteration.record_if(11, static_cast<bool>(false));  // HBFG_EVENT:ins_0012
      hbfg_iteration.record_if(12, static_cast<bool>(false));  // HBFG_EVENT:ins_0013
      hbfg_iteration.record(13);  // HBFG_EVENT:ins_0014
      std::optional<decltype(at::cosine_embedding_loss(hbfg_br_default_value_001, hbfg_br_default_value_003, hbfg_br_default_value_005))> hbfg_call_result_step_004;
      try {
      hbfg_call_result_step_004.emplace(at::cosine_embedding_loss(hbfg_br_default_value_001, hbfg_br_default_value_003, hbfg_br_default_value_005));
      } catch (const c10::Error& hbfg_error) {
      hbfg_iteration.record(14);  // HBFG_EVENT:ins_0015
      hbfg_iteration.log_target_api_exception(hbfg_error.what_without_backtrace());
      return 0;
      }
      hbfg_iteration.record(15);  // HBFG_EVENT:ins_0016
      auto hbfg_br_default_value_007 = std::move(*hbfg_call_result_step_004);
      // HBFG_SEGMENT_END:seg_br_default_004
    }
  }

  /* HBFG_REGION_END:branch_dispatch */

  /* HBFG_REGION_BEGIN:iteration_exit */

  return 0;

  /* HBFG_REGION_END:iteration_exit */
}
