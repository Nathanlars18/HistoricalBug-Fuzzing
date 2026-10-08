"""Shared execution evidence checks; missing evidence is never manufactured."""
from __future__ import annotations

FORMAT_VERSION = "1.0"
RUNTIME_VERSION = "1.1"


def snapshot_issues(snapshot, artifact=None):
    issues = []
    names = ("site_count", "started_iterations", "finished_iterations", "unwound_iterations", "invalid_site_records", "export_failures")
    if any(not isinstance(snapshot.get(k), int) or isinstance(snapshot.get(k), bool) or snapshot[k] < 0 for k in names):
        return ["runtime_snapshot_invalid"]
    counts = snapshot.get("site_counts")
    if not isinstance(counts, list) or len(counts) != snapshot["site_count"] or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in counts):
        issues.append("runtime_snapshot_invalid")
    if snapshot["finished_iterations"] + snapshot["unwound_iterations"] > snapshot["started_iterations"]:
        issues.append("counter_inconsistent")
    if snapshot["invalid_site_records"]: issues.append("invalid_site_record_observed")
    if snapshot["export_failures"]: issues.append("runtime_export_failure")
    if artifact is not None:
        identity = artifact["identity"]
        if snapshot.get("artifact_id") != identity["harness_artifact_id"] or snapshot.get("generation_key") != identity["generation_key"]:
            issues.append("artifact_identity_mismatch")
        if "instrumentation_map" in artifact and snapshot["site_count"] != len(artifact["instrumentation_map"]):
            issues.append("site_count_mismatch")
    return sorted(set(issues))


def validate_limits(limits):
    # Zero disables the documented libFuzzer timeout/RSS limit; null inherits
    # the pinned runtime's default. Docker memory and input length need > 0.
    for name in ("timeout", "rss_limit_mb", "max_len", "process_memory_mb", "candidate_sample_limit"):
        value = limits.get(name)
        minimum = 0 if name in {"timeout", "rss_limit_mb", "candidate_sample_limit"} else 1
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < minimum):
            raise ValueError(f"Invalid execution limit {name}")


def text_output(value):
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")
