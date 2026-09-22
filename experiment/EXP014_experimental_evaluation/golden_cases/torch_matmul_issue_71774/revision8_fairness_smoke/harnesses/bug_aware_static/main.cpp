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
    50;

constexpr char kHbfgArtifactId[] =
    "ha_st_hs_pytorch_torch_matmul_bug_aware_static_hsr001_r1_7ae6170271c9";

constexpr char kHbfgGenerationKey[] =
    "7ae6170271c9aa8b0d61f1cabe0eb757347ad7b10faf72e69749319517d59e3c";

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
    else {
      hbfg_iteration.record(12);  // HBFG_EVENT:ins_0013
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_001
      std::size_t hbfg_br_knowledge_001_value_002 = hbfg_offset;
      const std::int64_t hbfg_br_knowledge_001_value_001_dim_0 = (hbfg_br_knowledge_001_value_002 < Size) ? 1 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 8U) : 1;
      auto hbfg_br_knowledge_001_value_001 = torch::full({hbfg_br_knowledge_001_value_001_dim_0, 0}, ((hbfg_br_knowledge_001_value_002 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_002++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(13);  // HBFG_EVENT:ins_0014
      // HBFG_SEGMENT_END:seg_br_knowledge_001_001
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_002
      std::size_t hbfg_br_knowledge_001_value_004 = hbfg_br_knowledge_001_value_002;
      const std::int64_t hbfg_br_knowledge_001_value_003_dim_1 = (hbfg_br_knowledge_001_value_004 < Size) ? 1 + static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_004++] % 8U) : 1;
      auto hbfg_br_knowledge_001_value_003 = torch::full({0, hbfg_br_knowledge_001_value_003_dim_1}, ((hbfg_br_knowledge_001_value_004 < Size) ? static_cast<std::int64_t>(Data[hbfg_br_knowledge_001_value_004++] % 17U) - 8 : 0), torch::TensorOptions().dtype(torch::kInt64).device(torch::kCPU));
      hbfg_iteration.record(14);  // HBFG_EVENT:ins_0015
      // HBFG_SEGMENT_END:seg_br_knowledge_001_002
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_003
      const bool hbfg_br_knowledge_001_value_005 = (hbfg_br_knowledge_001_value_001.scalar_type() == torch::kInt64);
      hbfg_iteration.record(15);  // HBFG_EVENT:ins_0016
      hbfg_iteration.record(16);  // HBFG_EVENT:ins_0017
      hbfg_iteration.record_if(17, static_cast<bool>(hbfg_br_knowledge_001_value_005));  // HBFG_EVENT:ins_0018
      hbfg_iteration.record_if(18, static_cast<bool>(false));  // HBFG_EVENT:ins_0019
      hbfg_iteration.record_if(19, static_cast<bool>(false));  // HBFG_EVENT:ins_0020
      // HBFG_SEGMENT_END:seg_br_knowledge_001_003
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_004
      const bool hbfg_br_knowledge_001_value_006 = (hbfg_br_knowledge_001_value_003.scalar_type() == torch::kInt64);
      hbfg_iteration.record(20);  // HBFG_EVENT:ins_0021
      hbfg_iteration.record(21);  // HBFG_EVENT:ins_0022
      hbfg_iteration.record_if(22, static_cast<bool>(hbfg_br_knowledge_001_value_006));  // HBFG_EVENT:ins_0023
      hbfg_iteration.record_if(23, static_cast<bool>(false));  // HBFG_EVENT:ins_0024
      hbfg_iteration.record_if(24, static_cast<bool>(false));  // HBFG_EVENT:ins_0025
      // HBFG_SEGMENT_END:seg_br_knowledge_001_004
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_005
      const bool hbfg_br_knowledge_001_value_007 = (hbfg_br_knowledge_001_value_001.dim() > 1 && hbfg_br_knowledge_001_value_001.size(1) == 0);
      hbfg_iteration.record(25);  // HBFG_EVENT:ins_0026
      hbfg_iteration.record(26);  // HBFG_EVENT:ins_0027
      hbfg_iteration.record_if(27, static_cast<bool>(hbfg_br_knowledge_001_value_007));  // HBFG_EVENT:ins_0028
      hbfg_iteration.record_if(28, static_cast<bool>(false));  // HBFG_EVENT:ins_0029
      hbfg_iteration.record_if(29, static_cast<bool>(false));  // HBFG_EVENT:ins_0030
      // HBFG_SEGMENT_END:seg_br_knowledge_001_005
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_006
      const bool hbfg_br_knowledge_001_value_008 = (hbfg_br_knowledge_001_value_003.dim() > 0 && hbfg_br_knowledge_001_value_003.size(0) == 0);
      hbfg_iteration.record(30);  // HBFG_EVENT:ins_0031
      hbfg_iteration.record(31);  // HBFG_EVENT:ins_0032
      hbfg_iteration.record_if(32, static_cast<bool>(hbfg_br_knowledge_001_value_008));  // HBFG_EVENT:ins_0033
      hbfg_iteration.record_if(33, static_cast<bool>(false));  // HBFG_EVENT:ins_0034
      hbfg_iteration.record_if(34, static_cast<bool>(false));  // HBFG_EVENT:ins_0035
      hbfg_iteration.record(35);  // HBFG_EVENT:ins_0036
      hbfg_iteration.record_if(36, static_cast<bool>((hbfg_br_knowledge_001_value_005 && hbfg_br_knowledge_001_value_006 && hbfg_br_knowledge_001_value_007 && hbfg_br_knowledge_001_value_008)));  // HBFG_EVENT:ins_0037
      hbfg_iteration.record_if(37, static_cast<bool>(false));  // HBFG_EVENT:ins_0038
      hbfg_iteration.record_if(38, static_cast<bool>(false));  // HBFG_EVENT:ins_0039
      // HBFG_SEGMENT_END:seg_br_knowledge_001_006
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_007
      const bool hbfg_br_knowledge_001_et_pytorch_torch_matmul_empty_inner_long_pair = (hbfg_br_knowledge_001_value_001.dim() >= 2 && hbfg_br_knowledge_001_value_003.dim() >= 2 && hbfg_br_knowledge_001_value_001.size(hbfg_br_knowledge_001_value_001.dim() - 1) == 0 && hbfg_br_knowledge_001_value_003.size(hbfg_br_knowledge_001_value_003.dim() - 2) == 0 && hbfg_br_knowledge_001_value_001.scalar_type() == torch::kInt64 && hbfg_br_knowledge_001_value_003.scalar_type() == torch::kInt64);
      hbfg_iteration.record(39);  // HBFG_EVENT:ins_0040
      hbfg_iteration.record_if(40, static_cast<bool>(hbfg_br_knowledge_001_et_pytorch_torch_matmul_empty_inner_long_pair));  // HBFG_EVENT:ins_0041
      hbfg_iteration.record_if(41, static_cast<bool>(false));  // HBFG_EVENT:ins_0042
      hbfg_iteration.record_if(42, static_cast<bool>(false));  // HBFG_EVENT:ins_0043
      hbfg_iteration.record(43);  // HBFG_EVENT:ins_0044
      auto hbfg_br_knowledge_001_value_009 = at::matmul(hbfg_br_knowledge_001_value_001, hbfg_br_knowledge_001_value_003);
      hbfg_iteration.record(44);  // HBFG_EVENT:ins_0045
      // HBFG_SEGMENT_END:seg_br_knowledge_001_007
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_008
      hbfg_iteration.record(45);  // HBFG_EVENT:ins_0046
      auto hbfg_br_knowledge_001_value_010 = at::matmul(hbfg_br_knowledge_001_value_001, hbfg_br_knowledge_001_value_003);
      hbfg_iteration.record(46);  // HBFG_EVENT:ins_0047
      // HBFG_SEGMENT_END:seg_br_knowledge_001_008
      // HBFG_SEGMENT_BEGIN:seg_br_knowledge_001_009
      const bool hbfg_br_knowledge_001_value_011 = torch::equal(hbfg_br_knowledge_001_value_009, hbfg_br_knowledge_001_value_010);
      hbfg_iteration.record(47);  // HBFG_EVENT:ins_0048
      hbfg_iteration.record_if(48, static_cast<bool>(hbfg_br_knowledge_001_value_011));  // HBFG_EVENT:ins_0049
      hbfg_iteration.record_if(49, static_cast<bool>(!hbfg_br_knowledge_001_value_011));  // HBFG_EVENT:ins_0050
      if (!hbfg_br_knowledge_001_value_011) { std::abort(); }
      // HBFG_SEGMENT_END:seg_br_knowledge_001_009
    }
  }

  /* HBFG_REGION_END:branch_dispatch */

  /* HBFG_REGION_BEGIN:iteration_exit */

  return 0;

  /* HBFG_REGION_END:iteration_exit */
}
