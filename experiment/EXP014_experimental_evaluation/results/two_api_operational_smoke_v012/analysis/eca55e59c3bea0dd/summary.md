# Experiment Analysis: pytorch_2_10_operational_smoke_v012

- Analysis ID: `analysis:pytorch_2_10_operational_smoke_v012:eca55e59c3bea0dd`
- Analysis cutoff: `2026-10-08T08:48:37.554139Z`
- Analysis window: final
- APIs: 2
- Valid Round records: 18
- Attrited or missing tasks: 0
- Unresolved current-run cases/clusters: 0
- Coverage replay present: 18/18 rounds (diagnostic only)
- Coverage replay with LLVM warnings: 18 rounds
- Coverage replay with partial failures: 0 rounds
- Candidate captures: 768 saved; 58167 suppressed by capture limits
- Candidate records awaiting Case materialization: 768
- Captured candidate yield is not exhaustive bug discovery; first-N sampling can omit later distinct events.

## RQ1

- End-to-end Harness rate: not applicable (approved artifact reuse)
- APIs with computable observation reach: 2/2

## Per-API primary medians

| API | Observation reach | Baseline KTAC | Static KTAC | Baseline anomalies | Static anomalies | Adaptive activation gain | Adaptive anomaly gain |
|---|---:|---:|---:|---:|---:|---:|---:|
| torch.batch_norm_update_stats | 1.0000 | 0.0000 | 1.0000 | 0.0000 | unavailable | 0.0000 | unavailable |
| torch.nn.functional.cosine_embedding_loss | 1.0000 | 0.5000 | 1.0000 | 0.0000 | unavailable | 0.0000 | unavailable |

Machine-readable JSON and CSV files remain the authoritative results.
