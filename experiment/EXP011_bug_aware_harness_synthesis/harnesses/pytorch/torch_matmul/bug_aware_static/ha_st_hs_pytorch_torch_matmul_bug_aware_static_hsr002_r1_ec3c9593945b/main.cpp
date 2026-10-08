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
#include <cstdlib>

namespace {

constexpr std::uint32_t kHbfgInstrumentationSiteCount =
    42;

constexpr char kHbfgArtifactId[] =
    "ha_st_hs_pytorch_torch_matmul_bug_aware_static_hsr002_r1_ec3c9593945b";

constexpr char kHbfgGenerationKey[] =
    "ec3c9593945be74c1550bd48ca50a486a664caf727bfbd6042e2dcd2da1d11c0";

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
      std::size_t hbfg_br_default_value_002 = hbfg_offset;
      auto hbfg_br_default_value_001 = torch::full({2, 2}, 0, torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(1);  // HBFG_EVENT:ins_0002
      // HBFG_SEGMENT_END:seg_br_default_001
      // HBFG_SEGMENT_BEGIN:seg_br_default_002
      std::size_t hbfg_br_default_value_004 = hbfg_br_default_value_002;
      auto hbfg_br_default_value_003 = torch::full({2, 2}, 0, torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(2);  // HBFG_EVENT:ins_0003
      // HBFG_SEGMENT_END:seg_br_default_002
      // HBFG_SEGMENT_BEGIN:seg_br_default_003
      hbfg_iteration.record(3);  // HBFG_EVENT:ins_0004
      auto hbfg_br_default_value_005 = at::matmul(hbfg_br_default_value_001, hbfg_br_default_value_003);
      hbfg_iteration.record(4);  // HBFG_EVENT:ins_0005
      // HBFG_SEGMENT_END:seg_br_default_003
      // HBFG_SEGMENT_BEGIN:seg_br_default_004
      const bool hbfg_br_default_value_006 = true;
      hbfg_iteration.record(5);  // HBFG_EVENT:ins_0006
      hbfg_iteration.record_if(6, static_cast<bool>(hbfg_br_default_value_006));  // HBFG_EVENT:ins_0007
      hbfg_iteration.record_if(7, static_cast<bool>(false));  // HBFG_EVENT:ins_0008
      // HBFG_SEGMENT_END:seg_br_default_004
    }
    else {
      hbfg_iteration.record(8);  // HBFG_EVENT:ins_0009
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_001
      std::size_t hbfg_br_knowledge_001_value_002 = hbfg_offset;
      auto hbfg_br_knowledge_001_value_001 = torch::full({2, 0}, 0, torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(9);  // HBFG_EVENT:ins_0010
      // HBFG_SEGMENT_END:seg_br_knowledge_001_001
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_002
      std::size_t hbfg_br_knowledge_001_value_004 = hbfg_br_knowledge_001_value_002;
      auto hbfg_br_knowledge_001_value_003 = torch::full({0, 2}, 0, torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(10);  // HBFG_EVENT:ins_0011
      // HBFG_SEGMENT_END:seg_br_knowledge_001_002
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_003
      const bool hbfg_br_knowledge_001_value_005 = (hbfg_br_knowledge_001_value_001.dim() > 1 && hbfg_br_knowledge_001_value_001.size(1) == 0);
      hbfg_iteration.record(11);  // HBFG_EVENT:ins_0012
      hbfg_iteration.record(12);  // HBFG_EVENT:ins_0013
      hbfg_iteration.record_if(13, static_cast<bool>(hbfg_br_knowledge_001_value_005));  // HBFG_EVENT:ins_0014
      hbfg_iteration.record_if(14, static_cast<bool>(false));  // HBFG_EVENT:ins_0015
      hbfg_iteration.record_if(15, static_cast<bool>(false));  // HBFG_EVENT:ins_0016
      // HBFG_SEGMENT_END:seg_br_knowledge_001_003
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_004
      const bool hbfg_br_knowledge_001_value_006 = (hbfg_br_knowledge_001_value_003.dim() > 0 && hbfg_br_knowledge_001_value_003.size(0) == 0);
      hbfg_iteration.record(16);  // HBFG_EVENT:ins_0017
      hbfg_iteration.record(17);  // HBFG_EVENT:ins_0018
      hbfg_iteration.record_if(18, static_cast<bool>(hbfg_br_knowledge_001_value_006));  // HBFG_EVENT:ins_0019
      hbfg_iteration.record_if(19, static_cast<bool>(false));  // HBFG_EVENT:ins_0020
      hbfg_iteration.record_if(20, static_cast<bool>(false));  // HBFG_EVENT:ins_0021
      // HBFG_SEGMENT_END:seg_br_knowledge_001_004
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_005
      const bool hbfg_br_knowledge_001_value_007 = (hbfg_br_knowledge_001_value_001.scalar_type() == torch::kInt64);
      hbfg_iteration.record(21);  // HBFG_EVENT:ins_0022
      hbfg_iteration.record(22);  // HBFG_EVENT:ins_0023
      hbfg_iteration.record_if(23, static_cast<bool>(hbfg_br_knowledge_001_value_007));  // HBFG_EVENT:ins_0024
      hbfg_iteration.record_if(24, static_cast<bool>(false));  // HBFG_EVENT:ins_0025
      hbfg_iteration.record_if(25, static_cast<bool>(false));  // HBFG_EVENT:ins_0026
      // HBFG_SEGMENT_END:seg_br_knowledge_001_005
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_006
      const bool hbfg_br_knowledge_001_value_008 = (hbfg_br_knowledge_001_value_003.scalar_type() == torch::kInt64);
      hbfg_iteration.record(26);  // HBFG_EVENT:ins_0027
      hbfg_iteration.record(27);  // HBFG_EVENT:ins_0028
      hbfg_iteration.record_if(28, static_cast<bool>(hbfg_br_knowledge_001_value_008));  // HBFG_EVENT:ins_0029
      hbfg_iteration.record_if(29, static_cast<bool>(false));  // HBFG_EVENT:ins_0030
      hbfg_iteration.record_if(30, static_cast<bool>(false));  // HBFG_EVENT:ins_0031
      hbfg_iteration.record(31);  // HBFG_EVENT:ins_0032
      hbfg_iteration.record_if(32, static_cast<bool>((hbfg_br_knowledge_001_value_005 && hbfg_br_knowledge_001_value_006 && hbfg_br_knowledge_001_value_007 && hbfg_br_knowledge_001_value_008)));  // HBFG_EVENT:ins_0033
      hbfg_iteration.record_if(33, static_cast<bool>(false));  // HBFG_EVENT:ins_0034
      hbfg_iteration.record_if(34, static_cast<bool>(false));  // HBFG_EVENT:ins_0035
      // HBFG_SEGMENT_END:seg_br_knowledge_001_006
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_007
      hbfg_iteration.record(35);  // HBFG_EVENT:ins_0036
      auto hbfg_br_knowledge_001_value_009 = at::matmul(hbfg_br_knowledge_001_value_001, hbfg_br_knowledge_001_value_003);
      hbfg_iteration.record(36);  // HBFG_EVENT:ins_0037
      // HBFG_SEGMENT_END:seg_br_knowledge_001_007
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_008
      hbfg_iteration.record(37);  // HBFG_EVENT:ins_0038
      auto hbfg_br_knowledge_001_value_010 = at::matmul(hbfg_br_knowledge_001_value_001, hbfg_br_knowledge_001_value_003);
      hbfg_iteration.record(38);  // HBFG_EVENT:ins_0039
      // HBFG_SEGMENT_END:seg_br_knowledge_001_008
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_009
      const bool hbfg_br_knowledge_001_value_011 = torch::equal(hbfg_br_knowledge_001_value_009, hbfg_br_knowledge_001_value_010);
      hbfg_iteration.record(39);  // HBFG_EVENT:ins_0040
      hbfg_iteration.record_if(40, static_cast<bool>(hbfg_br_knowledge_001_value_011));  // HBFG_EVENT:ins_0041
      hbfg_iteration.record_if(41, static_cast<bool>(!hbfg_br_knowledge_001_value_011));  // HBFG_EVENT:ins_0042
      if (!hbfg_br_knowledge_001_value_011) { std::abort(); }
      // HBFG_SEGMENT_END:seg_br_knowledge_001_009
    }
  }

  /* HBFG_REGION_END:branch_dispatch */

  /* HBFG_REGION_BEGIN:iteration_exit */

  return 0;

  /* HBFG_REGION_END:iteration_exit */
}
