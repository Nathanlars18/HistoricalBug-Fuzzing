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

#include <cstdint>

namespace {

constexpr std::uint32_t kHbfgInstrumentationSiteCount =
    12;

constexpr char kHbfgArtifactId[] =
    "ha_st_hs_pytorch_torch_matmul_controlled_baseline_hsr001_r1_cc7f82d790cd";

constexpr char kHbfgGenerationKey[] =
    "cc7f82d790cd222278dfc57ff01d182076c38beed71c0f06e53bd88479d3e2c9";

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
      std::size_t hbfg_br_default_value_002 = hbfg_offset;
      auto hbfg_br_default_value_001 = torch::full({2, 3}, ((hbfg_br_default_value_002 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_default_value_002++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(1);  // HBFG_EVENT:ins_0002
      // HBFG_SEGMENT_END:seg_br_default_001
      // HBFG_SEGMENT_BEGIN:seg_br_default_002
      std::size_t hbfg_br_default_value_004 = hbfg_br_default_value_002;
      auto hbfg_br_default_value_003 = torch::full({3, 4}, ((hbfg_br_default_value_004 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_default_value_004++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(2);  // HBFG_EVENT:ins_0003
      // HBFG_SEGMENT_END:seg_br_default_002
      // HBFG_SEGMENT_BEGIN:seg_br_default_003
      const bool hbfg_br_default_et_pytorch_torch_matmul_empty_inner_long_pair = (hbfg_br_default_value_001.dim() >= 2 && hbfg_br_default_value_003.dim() >= 2 && hbfg_br_default_value_001.size(hbfg_br_default_value_001.dim() - 1) == 0 && hbfg_br_default_value_003.size(hbfg_br_default_value_003.dim() - 2) == 0 && hbfg_br_default_value_001.scalar_type() == torch::kInt64 && hbfg_br_default_value_003.scalar_type() == torch::kInt64);
      hbfg_iteration.record(3);  // HBFG_EVENT:ins_0004
      hbfg_iteration.record_if(4, static_cast<bool>(hbfg_br_default_et_pytorch_torch_matmul_empty_inner_long_pair));  // HBFG_EVENT:ins_0005
      hbfg_iteration.record_if(5, static_cast<bool>(false));  // HBFG_EVENT:ins_0006
      hbfg_iteration.record_if(6, static_cast<bool>(false));  // HBFG_EVENT:ins_0007
      hbfg_iteration.record(7);  // HBFG_EVENT:ins_0008
      auto hbfg_br_default_value_005 = at::matmul(hbfg_br_default_value_001, hbfg_br_default_value_003);
      hbfg_iteration.record(8);  // HBFG_EVENT:ins_0009
      // HBFG_SEGMENT_END:seg_br_default_003
      // HBFG_SEGMENT_BEGIN:seg_br_default_004
      const bool hbfg_br_default_value_006 = true;
      hbfg_iteration.record(9);  // HBFG_EVENT:ins_0010
      hbfg_iteration.record_if(10, static_cast<bool>(hbfg_br_default_value_006));  // HBFG_EVENT:ins_0011
      hbfg_iteration.record_if(11, static_cast<bool>(false));  // HBFG_EVENT:ins_0012
      // HBFG_SEGMENT_END:seg_br_default_004
    }
  }

  /* HBFG_REGION_END:branch_dispatch */

  /* HBFG_REGION_BEGIN:iteration_exit */

  return 0;

  /* HBFG_REGION_END:iteration_exit */
}
