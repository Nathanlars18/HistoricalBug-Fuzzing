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
    30;

constexpr char kHbfgArtifactId[] =
    "ha_st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_bug_aware_static_hsr004_r2_8119df6e0a44";

constexpr char kHbfgGenerationKey[] =
    "8119df6e0a44b60b39823e1389201a485362fbbfb2e7e0d28e4abd78db6e0f69";

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

    if (hbfg_selector <= 127) {
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
    else {
      hbfg_iteration.record(8);  // HBFG_EVENT:ins_0009
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_001
      std::size_t hbfg_br_knowledge_001_value_002 = hbfg_offset;
      const std::int64_t hbfg_br_knowledge_001_value_001_rank = (hbfg_br_knowledge_001_value_002 < Size) ? 1 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 2U) : 1;
      std::vector<std::int64_t> hbfg_br_knowledge_001_value_001_shape;
      for (std::int64_t axis = 0; axis < hbfg_br_knowledge_001_value_001_rank; ++axis) {
        hbfg_br_knowledge_001_value_001_shape.push_back((hbfg_br_knowledge_001_value_002 < Size) ? 0 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 2U) : 0);
      }
      auto hbfg_br_knowledge_001_value_001 = torch::full(hbfg_br_knowledge_001_value_001_shape, ((hbfg_br_knowledge_001_value_002 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(9);  // HBFG_EVENT:ins_0010
      // HBFG_SEGMENT_END:seg_br_knowledge_001_001
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_002
      std::size_t hbfg_br_knowledge_001_value_004 = hbfg_br_knowledge_001_value_002;
      const std::int64_t hbfg_br_knowledge_001_value_003_rank = (hbfg_br_knowledge_001_value_004 < Size) ? 1 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_004++] % 2U) : 1;
      std::vector<std::int64_t> hbfg_br_knowledge_001_value_003_shape;
      for (std::int64_t axis = 0; axis < hbfg_br_knowledge_001_value_003_rank; ++axis) {
        hbfg_br_knowledge_001_value_003_shape.push_back((hbfg_br_knowledge_001_value_004 < Size) ? 0 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_004++] % 2U) : 0);
      }
      auto hbfg_br_knowledge_001_value_003 = torch::full(hbfg_br_knowledge_001_value_003_shape, ((hbfg_br_knowledge_001_value_004 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_004++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(10);  // HBFG_EVENT:ins_0011
      // HBFG_SEGMENT_END:seg_br_knowledge_001_002
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_003
      std::size_t hbfg_br_knowledge_001_value_006 = hbfg_br_knowledge_001_value_004;
      auto hbfg_br_knowledge_001_value_005_shape = hbfg_br_knowledge_001_value_001.sizes().vec();
      if (!hbfg_br_knowledge_001_value_005_shape.empty()) { hbfg_br_knowledge_001_value_005_shape.pop_back(); }
      auto hbfg_br_knowledge_001_value_005 = torch::full(hbfg_br_knowledge_001_value_005_shape, ((hbfg_br_knowledge_001_value_006 < Size) ? ((Data[hbfg_br_knowledge_001_value_006++] & 1U) ? 1 : -1) : 1), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(11);  // HBFG_EVENT:ins_0012
      // HBFG_SEGMENT_END:seg_br_knowledge_001_003
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_004
      const bool hbfg_br_knowledge_001_value_007 = !(hbfg_br_knowledge_001_value_001.sizes().equals(hbfg_br_knowledge_001_value_003.sizes()));
      hbfg_iteration.record(12);  // HBFG_EVENT:ins_0013
      hbfg_iteration.record(13);  // HBFG_EVENT:ins_0014
      hbfg_iteration.record_if(14, static_cast<bool>(hbfg_br_knowledge_001_value_007));  // HBFG_EVENT:ins_0015
      hbfg_iteration.record_if(15, static_cast<bool>(false));  // HBFG_EVENT:ins_0016
      hbfg_iteration.record_if(16, static_cast<bool>(false));  // HBFG_EVENT:ins_0017
      // HBFG_SEGMENT_END:seg_br_knowledge_001_004
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_005
      const bool hbfg_br_knowledge_001_value_008 = (hbfg_br_knowledge_001_value_001.numel() == 0);
      hbfg_iteration.record(17);  // HBFG_EVENT:ins_0018
      hbfg_iteration.record(18);  // HBFG_EVENT:ins_0019
      hbfg_iteration.record_if(19, static_cast<bool>(hbfg_br_knowledge_001_value_008));  // HBFG_EVENT:ins_0020
      hbfg_iteration.record_if(20, static_cast<bool>(false));  // HBFG_EVENT:ins_0021
      hbfg_iteration.record_if(21, static_cast<bool>(false));  // HBFG_EVENT:ins_0022
      // HBFG_SEGMENT_END:seg_br_knowledge_001_005
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_006
      const bool hbfg_br_knowledge_001_value_009 = (hbfg_br_knowledge_001_value_003.numel() == 0);
      hbfg_iteration.record(22);  // HBFG_EVENT:ins_0023
      hbfg_iteration.record(23);  // HBFG_EVENT:ins_0024
      hbfg_iteration.record_if(24, static_cast<bool>(hbfg_br_knowledge_001_value_009));  // HBFG_EVENT:ins_0025
      hbfg_iteration.record_if(25, static_cast<bool>(false));  // HBFG_EVENT:ins_0026
      hbfg_iteration.record_if(26, static_cast<bool>(false));  // HBFG_EVENT:ins_0027
      // HBFG_SEGMENT_END:seg_br_knowledge_001_006
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_007
      hbfg_iteration.record(27);  // HBFG_EVENT:ins_0028
      std::optional<decltype(at::cosine_embedding_loss(hbfg_br_knowledge_001_value_001, hbfg_br_knowledge_001_value_003, hbfg_br_knowledge_001_value_005))> hbfg_call_result_step_007;
      try {
      hbfg_call_result_step_007.emplace(at::cosine_embedding_loss(hbfg_br_knowledge_001_value_001, hbfg_br_knowledge_001_value_003, hbfg_br_knowledge_001_value_005));
      } catch (const c10::Error& hbfg_error) {
      hbfg_iteration.record(28);  // HBFG_EVENT:ins_0029
      hbfg_iteration.log_target_api_exception(hbfg_error.what_without_backtrace());
      return 0;
      }
      hbfg_iteration.record(29);  // HBFG_EVENT:ins_0030
      auto hbfg_br_knowledge_001_value_010 = std::move(*hbfg_call_result_step_007);
      // HBFG_SEGMENT_END:seg_br_knowledge_001_007
    }
  }

  /* HBFG_REGION_END:branch_dispatch */

  /* HBFG_REGION_BEGIN:iteration_exit */

  return 0;

  /* HBFG_REGION_END:iteration_exit */
}
