"""Shared deterministic evidence and reporting rules; no execution or model calls."""
from __future__ import annotations

import hashlib
import json
import re
import copy
from pathlib import Path
from typing import Any, Mapping


def diagnostic_signature(kind: str, subtype: str, text: str, version: str = "2.0") -> dict[str, str]:
    # Progress, coverage, seed and elapsed-time lines are run context, not failure identity.
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if (not stripped or re.match(r"^#\d+\s+(?:INITED|NEW|REDUCE|DONE|pulse|cov:|ft:)", stripped)
                or stripped.startswith(("INFO:", "# docker", "# fuzzer", "Done ", "stat::"))):
            continue
        if re.search(r"ERROR:|SUMMARY:|runtime error:|Sanitizer|deadly signal|HBFG_.*(?:EXCEPTION|FAILURE)|terminate called|what\(\):|^#\d+\s+0x|at::|c10::|torch::|aten::", stripped):
            stripped = re.sub(r"\b0x[0-9a-fA-F]+\b", "<ADDR>", stripped)
            stripped = re.sub(r"==\d+==", "<PID>", stripped)
            stripped = re.sub(r"\b(?:thread|tid)[ =:#-]*\d+\b", "<THREAD>", stripped, flags=re.I)
            stripped = re.sub(r"(?<!\w)/(?:[^\s/]+/)+([^\s/]+)", r"<PATH>/\1", stripped)
            lines.append(" ".join(stripped.split()))
    # An empty extracted diagnostic is explicitly insufficient for automatic equivalence.
    payload = {"kind": kind, "subtype": subtype, "diagnostic": lines[:80]}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"algorithm_version": version, "signature_hash": digest}


def reproduction_status(attempts: list[Mapping[str, Any]], policy: Mapping[str, Any], reviewed: bool = False) -> str:
    replay = policy["replay"]
    valid = [a for a in attempts if a["valid_attempt"]]
    if not attempts:
        return "not_attempted"
    if len(valid) != replay["required_valid_attempts"]:
        return "inconclusive"
    accepted = replay["reviewed_success_equivalence"] if reviewed else replay["automatic_success_equivalence"]
    successes = sum(a["equivalence_status"] in accepted for a in valid)
    return replay["completed_status_by_success_count"][str(successes)]


def reportable(record: Mapping[str, Any]) -> bool:
    capture = record.get("capture_record", {})
    policy = capture.get("policy_snapshot", {})
    review = record["human_review"]
    attempts = record["reproduction"]["attempts"]
    replay = policy.get("replay", {})
    required_attempts = replay.get("required_valid_attempts")
    return (record.get("record_format_version") == "1.2"
            and bool(policy)
            and isinstance(required_attempts, int)
            and sum(bool(a["valid_attempt"]) for a in attempts) == required_attempts
            and record["admission"]["status"] == "admitted"
            and record["deduplication"]["status"] == "completed"
            and record["deduplication"]["case_role"] == "representative"
            and record["workflow_status"] == "closed"
            and record["reproduction"]["status"] == "stable"
            and bool(record["reproduction"]["attempts"])
            and record["fault_attribution"]["status"] == "framework"
            and record["api_behavior_assessment"]["status"] == "unexpected_behavior"
            and review["status"] == "completed" and review["conclusion"] == "accepted"
            and bool(review.get("reviewer_id"))
            and review.get("reviewed_subject_hash") == analysis_subject_hash(record)
            and {"admission", "fault_attribution", "reproduction_equivalence", "final_case"}
                <= set(review["reviewed_aspects"])
            and not any(q["status"] == "open" and q["blocking"] for q in record["unresolved_questions"]))


def analysis_subject_hash(record: Mapping[str, Any]) -> str:
    subject = copy.deepcopy(dict(record))
    for name in ("human_review", "validation", "provenance", "revision", "workflow_status"):
        subject.pop(name, None)
    # Reproduction status is policy-derived from the bound attempt records;
    # human review may promote semantic-equivalence decisions without changing
    # the evidence being reviewed.
    subject.get("reproduction", {}).pop("status", None)
    return hashlib.sha256(json.dumps(subject, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def analysis_complete(record: Mapping[str, Any]) -> bool:
    # Legacy Cases lack immutable source and policy snapshots. They remain
    # inspectable, but cannot silently enter versioned aggregate claims.
    if record.get("record_format_version") != "1.2" or not record.get("capture_record", {}).get("policy_snapshot"):
        return False
    dedup = record["deduplication"]
    if dedup["case_role"] == "duplicate_member":
        if dedup["status"] != "completed" or not dedup["cluster_id"] or not dedup["representative_case_ref"]:
            return False
        if dedup["assignment_kind"] == "semantic_duplicate":
            review = record["human_review"]
            return (review["status"] == "completed" and review["conclusion"] == "accepted"
                    and "semantic_deduplication" in review["reviewed_aspects"]
                    and review.get("reviewed_subject_hash") == analysis_subject_hash(record))
        return dedup["assignment_kind"] == "exact_duplicate" and dedup["exact_fingerprint"] is not None
    if record["admission"]["status"] != "rejected" and (
            dedup["status"] != "completed" or dedup["case_role"] != "representative"):
        return False
    review = record["human_review"]
    reviewed = (review.get("reviewed_subject_hash") == analysis_subject_hash(record)
                and {"admission", "fault_attribution", "final_case"} <= set(review["reviewed_aspects"]))
    if not (record["workflow_status"] == "closed" and review["status"] == "completed"
            and review["conclusion"] == "accepted"
            and reviewed and record["admission"]["status"] != "pending"
            and not any(q["status"] == "open" and q["blocking"] for q in record["unresolved_questions"])):
        return False
    if record["admission"]["status"] == "rejected":
        return True
    attribution = record["fault_attribution"]["status"]
    if attribution in {"not_assessed", "unresolved"}:
        return False
    if attribution == "framework":
        return record["reproduction"]["status"] in {"stable", "intermittent", "weak", "not_reproduced", "inconclusive"}
    return True


def consistency_errors(record: Mapping[str, Any], policy: Mapping[str, Any] | None = None) -> list[str]:
    errors = []
    snapshot = record.get("capture_record", {}).get("policy_snapshot")
    if snapshot is not None:
        policy = snapshot
        ref = record["reproduction"]["policy_ref"]
        snapshot_hash = hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        if (ref["content_hash"] != snapshot_hash or ref["artifact_id"] != snapshot["policy_id"] or ref["artifact_version"] != snapshot["policy_version"]):
            errors.append("Replay policy reference differs from the immutable captured policy")
    review = record["human_review"]
    if record.get("record_format_version") == "1.2" and review["status"] == "completed":
        if (not review.get("reviewer_id") or not review.get("evidence_refs")
                or review.get("reviewed_subject_hash") != analysis_subject_hash(record)):
            errors.append("Human review lacks reviewer, evidence, or exact analyzed-subject hash")
    attempts = record["reproduction"]["attempts"]
    reviewed = (review["status"] == "completed" and "reproduction_equivalence" in review["reviewed_aspects"])
    if policy and record["reproduction"]["status"] != reproduction_status(attempts, policy, reviewed):
        errors.append("Reproduction status disagrees with policy-derived replay counts")
    elif not attempts and record["reproduction"]["status"] != "not_attempted":
        errors.append("Reproduction conclusion requires replay attempts")
    ids = {a["attempt_id"]: a for a in attempts}
    if len(ids) != len(attempts):
        errors.append("Replay attempt IDs are duplicated")
    for a in attempts:
        if a["valid_attempt"] and a["target_api_reach_status"] != "reached":
            errors.append("Valid replay lacks target execution evidence")
        if a["equivalence_status"] == "semantically_equivalent" and record["workflow_status"] == "closed" and (
                record["human_review"]["status"] != "completed"
                or "reproduction_equivalence" not in record["human_review"]["reviewed_aspects"]):
            errors.append("Semantic replay equivalence requires human review")
        replacement = a["replaces_attempt_id"]
        if replacement is not None and (replacement not in ids or ids[replacement]["valid_attempt"]
                or ids[replacement]["ordinal"] >= a["ordinal"]):
            errors.append("Invalid replay replacement relation")
    if policy:
        if (len(attempts) > policy["replay"]["required_valid_attempts"] + policy["replay"]["maximum_replacement_attempts"]
                or sum(a["valid_attempt"] for a in attempts) > policy["replay"]["required_valid_attempts"]):
            errors.append("Replay counts exceed policy limits")
    conditions = record["admission"]["condition_assessments"]
    names = [c["condition_kind"] for c in conditions]
    if len(names) != len(set(names)):
        errors.append("Admission conditions are duplicated")
    if record["admission"]["status"] == "admitted":
        table = {c["condition_kind"]: c for c in conditions}
        required = {"target_api_reached", "evidence_sufficient"}
        primary = next((o for o in record["candidate_event"]["observations"]
                        if o["observation_id"] == record["candidate_event"]["primary_observation_id"]), {})
        if primary.get("kind") == "oracle_violation":
            tier = primary.get("oracle_evidence_tier")
            if tier not in {"tier_1_exact", "tier_2_validated"}:
                errors.append("Diagnostic-only or unevaluable Oracle observations cannot be admitted")
            if policy is not None:
                expected_action = policy["candidate_admission"]["oracle_tier_actions"].get(tier)
                if expected_action not in {"direct", "conditional"} or record["admission"]["kind"] != expected_action:
                    errors.append("Oracle admission kind disagrees with the captured Policy tier action")
            required |= {"oracle_preconditions_satisfied", "oracle_applicable"}
        elif policy is not None:
            expected_action = policy["candidate_admission"]["observation_actions"].get(primary.get("kind"))
            if record["admission"]["kind"] != expected_action:
                errors.append("Candidate admission kind disagrees with the captured Policy observation action")
        if primary.get("kind") in {"target_exception", "resource_anomaly"}:
            required.add("controlled_rejection_excluded")
        if primary.get("kind") == "resource_anomaly":
            required |= {"resource_threshold_reached", "external_pressure_excluded"}
        if any(n not in table or table[n]["status"] != "satisfied" or not table[n]["evidence_refs"] for n in required):
            errors.append("Admitted Case lacks satisfied, evidenced admission conditions")
    novelty = record["novelty_assessment"]["status"]
    if record["workflow_status"] == "closed" and not analysis_complete(record):
        errors.append("Closed Case lacks the evidence, replay, or exact human review required for closure")
    if record["workflow_status"] == "closed" and (review["status"] != "completed" or review["conclusion"] != "accepted"):
        errors.append("Closed Case requires accepted human review")
    if novelty in {"known_bug_rediscovery", "potentially_novel", "externally_confirmed_novel_bug"} and record["workflow_status"] == "closed":
        if not reportable(record):
            errors.append("Bug conclusion requires a reviewed reportable framework anomaly")
        historical = record["historical_matching"]
        if historical["search_status"] != "completed" or historical["scope_status"] != "complete":
            errors.append("Bug conclusion lacks completed recorded historical search scope")
        if "historical_matching" not in record["human_review"]["reviewed_aspects"]:
            errors.append("Historical match requires human review")
    return errors


def cluster_errors(records: list[Mapping[str, Any]], records_root: Path | None = None) -> list[str]:
    errors = []
    clusters: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        cluster = record["deduplication"]["cluster_id"]
        if cluster is not None: clusters.setdefault(cluster, []).append(record)
    for cluster, members in clusters.items():
        representatives = [r for r in members if r["deduplication"]["case_role"] == "representative"]
        if len(representatives) != 1:
            errors.append(f"Cluster {cluster} lacks exactly one representative")
            continue
        representative = representatives[0]
        for member in members:
            dedup = member["deduplication"]
            if dedup["case_role"] == "duplicate_member":
                ref = dedup["representative_case_ref"]
                if ref["artifact_id"] != representative["identity"]["case_id"]:
                    errors.append(f"Cluster {cluster} has a wrong representative reference")
                if records_root is not None:
                    try:
                        revision = int(ref["artifact_version"])
                        path = records_root / ref["artifact_id"] / "records" / f"{ref['artifact_id']}_r{revision:03d}.json"
                        payload = path.read_bytes()
                        if hashlib.sha256(payload).hexdigest() != ref["content_hash"]:
                            raise ValueError("content hash mismatch")
                        linked = json.loads(payload)
                        if (linked["identity"]["case_id"] != representative["identity"]["case_id"]
                                or linked["deduplication"]["case_role"] != "representative"
                                or linked["deduplication"]["cluster_id"] != cluster):
                            raise ValueError("linked revision is not this cluster representative")
                    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                        errors.append(f"Cluster {cluster} representative reference is unavailable or inconsistent: {exc}")
                if dedup["assignment_kind"] == "exact_duplicate" and dedup["exact_fingerprint"] != representative["deduplication"]["exact_fingerprint"]:
                    errors.append(f"Cluster {cluster} contains a false exact duplicate")
    return errors
