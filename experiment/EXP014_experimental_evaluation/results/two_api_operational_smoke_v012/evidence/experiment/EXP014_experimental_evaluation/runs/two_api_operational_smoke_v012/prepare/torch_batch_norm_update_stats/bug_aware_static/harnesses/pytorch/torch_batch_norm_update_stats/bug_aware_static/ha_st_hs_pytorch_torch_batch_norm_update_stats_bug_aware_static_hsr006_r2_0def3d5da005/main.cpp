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
    29;

constexpr char kHbfgArtifactId[] =
    "ha_st_hs_pytorch_torch_batch_norm_update_stats_bug_aware_static_hsr006_r2_0def3d5da005";

constexpr char kHbfgGenerationKey[] =
    "0def3d5da005e63c3b7676691e50e2a77bbd5638f8428ae6793364ecdad766b8";

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

    if (hbfg_selector <= 127) {
      hbfg_iteration.record(0);  // HBFG_EVENT:ins_0001
      // HBFG_SEGMENT_BEGIN:seg_br_default_001
      std::size_t hbfg_br_default_value_002 = hbfg_offset;
      const std::int64_t hbfg_br_default_value_001_dim_0 = (hbfg_br_default_value_002 < Size) ? 1 + static_cast<std::int64_t>(Data[hbfg_br_default_value_002++] % 16U) : 1;
      const std::int64_t hbfg_br_default_value_001_dim_1 = (hbfg_br_default_value_002 < Size) ? 1 + static_cast<std::int64_t>(Data[hbfg_br_default_value_002++] % 16U) : 1;
      auto hbfg_br_default_value_001 = torch::full({hbfg_br_default_value_001_dim_0, hbfg_br_default_value_001_dim_1}, ((hbfg_br_default_value_002 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_default_value_002++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(1);  // HBFG_EVENT:ins_0002
      // HBFG_SEGMENT_END:seg_br_default_001
      // HBFG_SEGMENT_BEGIN:seg_br_default_002
      std::size_t hbfg_br_default_value_004 = hbfg_br_default_value_002;
      auto hbfg_br_default_value_003 = torch::full(std::vector<std::int64_t>{hbfg_br_default_value_001.dim() > 1 ? hbfg_br_default_value_001.size(1) : 0}, ((hbfg_br_default_value_004 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_default_value_004++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(2);  // HBFG_EVENT:ins_0003
      // HBFG_SEGMENT_END:seg_br_default_002
      // HBFG_SEGMENT_BEGIN:seg_br_default_003
      std::size_t hbfg_br_default_value_006 = hbfg_br_default_value_004;
      auto hbfg_br_default_value_005 = torch::full(std::vector<std::int64_t>{hbfg_br_default_value_001.dim() > 1 ? hbfg_br_default_value_001.size(1) : 0}, ((hbfg_br_default_value_006 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_default_value_006++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(3);  // HBFG_EVENT:ins_0004
      // HBFG_SEGMENT_END:seg_br_default_003
      // HBFG_SEGMENT_BEGIN:seg_br_default_004
      hbfg_iteration.record_if(4, static_cast<bool>((Size < hbfg_br_default_value_006 || Size - hbfg_br_default_value_006 < 1U)));  // HBFG_EVENT:ins_0005
      if ((Size < hbfg_br_default_value_006 || Size - hbfg_br_default_value_006 < 1U)) { return 0; }
      std::size_t hbfg_br_default_value_008 = hbfg_br_default_value_006;
      const double hbfg_br_default_value_007_position = static_cast<double>(Data[hbfg_br_default_value_008++]) / 255.0;
      const double hbfg_br_default_value_007 = (1.0 - hbfg_br_default_value_007_position) * 0.0 + hbfg_br_default_value_007_position * 1.0;
      hbfg_iteration.record(5);  // HBFG_EVENT:ins_0006
      // HBFG_SEGMENT_END:seg_br_default_004
      // HBFG_SEGMENT_BEGIN:seg_br_default_005
      const bool hbfg_br_default_et_pytorch_batch_norm_update_stats_empty_input = (hbfg_br_default_value_001.numel() == 0);
      hbfg_iteration.record(6);  // HBFG_EVENT:ins_0007
      hbfg_iteration.record_if(7, static_cast<bool>(hbfg_br_default_et_pytorch_batch_norm_update_stats_empty_input));  // HBFG_EVENT:ins_0008
      hbfg_iteration.record_if(8, static_cast<bool>(false));  // HBFG_EVENT:ins_0009
      hbfg_iteration.record_if(9, static_cast<bool>(false));  // HBFG_EVENT:ins_0010
      hbfg_iteration.record(10);  // HBFG_EVENT:ins_0011
      std::optional<decltype(at::batch_norm_update_stats(hbfg_br_default_value_001, hbfg_br_default_value_003, hbfg_br_default_value_005, hbfg_br_default_value_007))> hbfg_call_result_step_005;
      try {
      hbfg_call_result_step_005.emplace(at::batch_norm_update_stats(hbfg_br_default_value_001, hbfg_br_default_value_003, hbfg_br_default_value_005, hbfg_br_default_value_007));
      } catch (const c10::Error& hbfg_error) {
      hbfg_iteration.record(11);  // HBFG_EVENT:ins_0012
      hbfg_iteration.log_target_api_exception(hbfg_error.what_without_backtrace());
      return 0;
      }
      hbfg_iteration.record(12);  // HBFG_EVENT:ins_0013
      auto [hbfg_br_default_value_009, hbfg_br_default_value_010] = std::move(*hbfg_call_result_step_005);
      // HBFG_SEGMENT_END:seg_br_default_005
    }
    else {
      hbfg_iteration.record(13);  // HBFG_EVENT:ins_0014
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_001
      std::size_t hbfg_br_knowledge_001_value_002 = hbfg_offset;
      const std::int64_t hbfg_br_knowledge_001_value_001_dim_0 = (hbfg_br_knowledge_001_value_002 < Size) ? 0 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 17U) : 0;
      const std::int64_t hbfg_br_knowledge_001_value_001_dim_1 = (hbfg_br_knowledge_001_value_002 < Size) ? 0 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 17U) : 0;
      auto hbfg_br_knowledge_001_value_001 = torch::full({hbfg_br_knowledge_001_value_001_dim_0, hbfg_br_knowledge_001_value_001_dim_1}, ((hbfg_br_knowledge_001_value_002 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(14);  // HBFG_EVENT:ins_0015
      // HBFG_SEGMENT_END:seg_br_knowledge_001_001
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_002
      hbfg_iteration.record_if(15, static_cast<bool>((Size < hbfg_br_knowledge_001_value_002 || Size - hbfg_br_knowledge_001_value_002 < 1U)));  // HBFG_EVENT:ins_0016
      if ((Size < hbfg_br_knowledge_001_value_002 || Size - hbfg_br_knowledge_001_value_002 < 1U)) { return 0; }
      std::size_t hbfg_br_knowledge_001_value_004 = hbfg_br_knowledge_001_value_002;
      const double hbfg_br_knowledge_001_value_003_position = static_cast<double>(Data[hbfg_br_knowledge_001_value_004++]) / 255.0;
      const double hbfg_br_knowledge_001_value_003 = (1.0 - hbfg_br_knowledge_001_value_003_position) * 0.0 + hbfg_br_knowledge_001_value_003_position * 1.0;
      hbfg_iteration.record(16);  // HBFG_EVENT:ins_0017
      // HBFG_SEGMENT_END:seg_br_knowledge_001_002
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_003
      const bool hbfg_br_knowledge_001_value_005 = (hbfg_br_knowledge_001_value_001.numel() == 0);
      hbfg_iteration.record(17);  // HBFG_EVENT:ins_0018
      hbfg_iteration.record(18);  // HBFG_EVENT:ins_0019
      hbfg_iteration.record_if(19, static_cast<bool>(hbfg_br_knowledge_001_value_005));  // HBFG_EVENT:ins_0020
      hbfg_iteration.record_if(20, static_cast<bool>(false));  // HBFG_EVENT:ins_0021
      hbfg_iteration.record_if(21, static_cast<bool>(false));  // HBFG_EVENT:ins_0022
      // HBFG_SEGMENT_END:seg_br_knowledge_001_003
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_004
      const bool hbfg_br_knowledge_001_et_pytorch_batch_norm_update_stats_empty_input = (hbfg_br_knowledge_001_value_001.numel() == 0);
      hbfg_iteration.record(22);  // HBFG_EVENT:ins_0023
      hbfg_iteration.record_if(23, static_cast<bool>(hbfg_br_knowledge_001_et_pytorch_batch_norm_update_stats_empty_input));  // HBFG_EVENT:ins_0024
      hbfg_iteration.record_if(24, static_cast<bool>(false));  // HBFG_EVENT:ins_0025
      hbfg_iteration.record_if(25, static_cast<bool>(false));  // HBFG_EVENT:ins_0026
      hbfg_iteration.record(26);  // HBFG_EVENT:ins_0027
      std::optional<decltype(at::batch_norm_update_stats(hbfg_br_knowledge_001_value_001, c10::nullopt, c10::nullopt, hbfg_br_knowledge_001_value_003))> hbfg_call_result_step_004;
      try {
      hbfg_call_result_step_004.emplace(at::batch_norm_update_stats(hbfg_br_knowledge_001_value_001, c10::nullopt, c10::nullopt, hbfg_br_knowledge_001_value_003));
      } catch (const c10::Error& hbfg_error) {
      hbfg_iteration.record(27);  // HBFG_EVENT:ins_0028
      hbfg_iteration.log_target_api_exception(hbfg_error.what_without_backtrace());
      return 0;
      }
      hbfg_iteration.record(28);  // HBFG_EVENT:ins_0029
      auto [hbfg_br_knowledge_001_value_006, hbfg_br_knowledge_001_value_007] = std::move(*hbfg_call_result_step_004);
      // HBFG_SEGMENT_END:seg_br_knowledge_001_004
    }
  }

  /* HBFG_REGION_END:branch_dispatch */

  /* HBFG_REGION_BEGIN:iteration_exit */

  return 0;

  /* HBFG_REGION_END:iteration_exit */
}
