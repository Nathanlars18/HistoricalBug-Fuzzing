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
    46;

constexpr char kHbfgArtifactId[] =
    "ha_st_hs_pytorch_torch_nn_functional_cosine_embedding_loss_bug_aware_static_hsr004_r2_1db0a08e49f6";

constexpr char kHbfgGenerationKey[] =
    "1db0a08e49f69e4489ece5f762fe5ed1aad0e4e9aed94bea497d5acd0c136c5b";

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
    else {
      hbfg_iteration.record(16);  // HBFG_EVENT:ins_0017
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_001
      std::size_t hbfg_br_knowledge_001_value_002 = hbfg_offset;
      const std::int64_t hbfg_br_knowledge_001_value_001_rank = (hbfg_br_knowledge_001_value_002 < Size) ? 1 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 2U) : 1;
      std::vector<std::int64_t> hbfg_br_knowledge_001_value_001_shape;
      for (std::int64_t axis = 0; axis < hbfg_br_knowledge_001_value_001_rank; ++axis) {
        hbfg_br_knowledge_001_value_001_shape.push_back((hbfg_br_knowledge_001_value_002 < Size) ? 0 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 2U) : 0);
      }
      auto hbfg_br_knowledge_001_value_001 = torch::full(hbfg_br_knowledge_001_value_001_shape, ((hbfg_br_knowledge_001_value_002 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(17);  // HBFG_EVENT:ins_0018
      // HBFG_SEGMENT_END:seg_br_knowledge_001_001
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_002
      std::size_t hbfg_br_knowledge_001_value_004 = hbfg_br_knowledge_001_value_002;
      const std::int64_t hbfg_br_knowledge_001_value_003_rank = (hbfg_br_knowledge_001_value_004 < Size) ? 1 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_004++] % 2U) : 1;
      std::vector<std::int64_t> hbfg_br_knowledge_001_value_003_shape;
      for (std::int64_t axis = 0; axis < hbfg_br_knowledge_001_value_003_rank; ++axis) {
        hbfg_br_knowledge_001_value_003_shape.push_back((hbfg_br_knowledge_001_value_004 < Size) ? 0 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_004++] % 2U) : 0);
      }
      auto hbfg_br_knowledge_001_value_003 = torch::full(hbfg_br_knowledge_001_value_003_shape, ((hbfg_br_knowledge_001_value_004 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_004++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(18);  // HBFG_EVENT:ins_0019
      // HBFG_SEGMENT_END:seg_br_knowledge_001_002
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_003
      std::size_t hbfg_br_knowledge_001_value_006 = hbfg_br_knowledge_001_value_004;
      auto hbfg_br_knowledge_001_value_005_shape = hbfg_br_knowledge_001_value_001.sizes().vec();
      if (!hbfg_br_knowledge_001_value_005_shape.empty()) { hbfg_br_knowledge_001_value_005_shape.pop_back(); }
      auto hbfg_br_knowledge_001_value_005 = torch::full(hbfg_br_knowledge_001_value_005_shape, ((hbfg_br_knowledge_001_value_006 < Size) ? ((Data[hbfg_br_knowledge_001_value_006++] & 1U) ? 1 : -1) : 1), torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));
      hbfg_iteration.record(19);  // HBFG_EVENT:ins_0020
      // HBFG_SEGMENT_END:seg_br_knowledge_001_003
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_004
      const bool hbfg_br_knowledge_001_value_007 = !(hbfg_br_knowledge_001_value_001.sizes().equals(hbfg_br_knowledge_001_value_003.sizes()));
      hbfg_iteration.record(20);  // HBFG_EVENT:ins_0021
      hbfg_iteration.record(21);  // HBFG_EVENT:ins_0022
      hbfg_iteration.record_if(22, static_cast<bool>(hbfg_br_knowledge_001_value_007));  // HBFG_EVENT:ins_0023
      hbfg_iteration.record_if(23, static_cast<bool>(false));  // HBFG_EVENT:ins_0024
      hbfg_iteration.record_if(24, static_cast<bool>(false));  // HBFG_EVENT:ins_0025
      // HBFG_SEGMENT_END:seg_br_knowledge_001_004
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_005
      const bool hbfg_br_knowledge_001_value_008 = (hbfg_br_knowledge_001_value_001.numel() == 0);
      hbfg_iteration.record(25);  // HBFG_EVENT:ins_0026
      hbfg_iteration.record(26);  // HBFG_EVENT:ins_0027
      hbfg_iteration.record_if(27, static_cast<bool>(hbfg_br_knowledge_001_value_008));  // HBFG_EVENT:ins_0028
      hbfg_iteration.record_if(28, static_cast<bool>(false));  // HBFG_EVENT:ins_0029
      hbfg_iteration.record_if(29, static_cast<bool>(false));  // HBFG_EVENT:ins_0030
      // HBFG_SEGMENT_END:seg_br_knowledge_001_005
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_006
      const bool hbfg_br_knowledge_001_value_009 = (hbfg_br_knowledge_001_value_003.numel() == 0);
      hbfg_iteration.record(30);  // HBFG_EVENT:ins_0031
      hbfg_iteration.record(31);  // HBFG_EVENT:ins_0032
      hbfg_iteration.record_if(32, static_cast<bool>(hbfg_br_knowledge_001_value_009));  // HBFG_EVENT:ins_0033
      hbfg_iteration.record_if(33, static_cast<bool>(false));  // HBFG_EVENT:ins_0034
      hbfg_iteration.record_if(34, static_cast<bool>(false));  // HBFG_EVENT:ins_0035
      // HBFG_SEGMENT_END:seg_br_knowledge_001_006
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_007
      const bool hbfg_br_knowledge_001_et_pytorch_cosine_embedding_loss_shape_mismatch = (!hbfg_br_knowledge_001_value_001.sizes().equals(hbfg_br_knowledge_001_value_003.sizes()));
      hbfg_iteration.record(35);  // HBFG_EVENT:ins_0036
      hbfg_iteration.record_if(36, static_cast<bool>(hbfg_br_knowledge_001_et_pytorch_cosine_embedding_loss_shape_mismatch));  // HBFG_EVENT:ins_0037
      hbfg_iteration.record_if(37, static_cast<bool>(false));  // HBFG_EVENT:ins_0038
      hbfg_iteration.record_if(38, static_cast<bool>(false));  // HBFG_EVENT:ins_0039
      const bool hbfg_br_knowledge_001_et_pytorch_cosine_embedding_loss_any_input_empty = (hbfg_br_knowledge_001_value_001.numel() == 0 || hbfg_br_knowledge_001_value_003.numel() == 0);
      hbfg_iteration.record(39);  // HBFG_EVENT:ins_0040
      hbfg_iteration.record_if(40, static_cast<bool>(hbfg_br_knowledge_001_et_pytorch_cosine_embedding_loss_any_input_empty));  // HBFG_EVENT:ins_0041
      hbfg_iteration.record_if(41, static_cast<bool>(false));  // HBFG_EVENT:ins_0042
      hbfg_iteration.record_if(42, static_cast<bool>(false));  // HBFG_EVENT:ins_0043
      hbfg_iteration.record(43);  // HBFG_EVENT:ins_0044
      std::optional<decltype(at::cosine_embedding_loss(hbfg_br_knowledge_001_value_001, hbfg_br_knowledge_001_value_003, hbfg_br_knowledge_001_value_005))> hbfg_call_result_step_007;
      try {
      hbfg_call_result_step_007.emplace(at::cosine_embedding_loss(hbfg_br_knowledge_001_value_001, hbfg_br_knowledge_001_value_003, hbfg_br_knowledge_001_value_005));
      } catch (const c10::Error& hbfg_error) {
      hbfg_iteration.record(44);  // HBFG_EVENT:ins_0045
      hbfg_iteration.log_target_api_exception(hbfg_error.what_without_backtrace());
      return 0;
      }
      hbfg_iteration.record(45);  // HBFG_EVENT:ins_0046
      auto hbfg_br_knowledge_001_value_010 = std::move(*hbfg_call_result_step_007);
      // HBFG_SEGMENT_END:seg_br_knowledge_001_007
    }
  }

  /* HBFG_REGION_END:branch_dispatch */

  /* HBFG_REGION_BEGIN:iteration_exit */

  return 0;

  /* HBFG_REGION_END:iteration_exit */
}
