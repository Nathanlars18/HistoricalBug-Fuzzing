"""Machine certificates for reviewed, budget-only feedback transformations.

Certificates are not human review records and never grant a semantic change.
Every parent authorization, request, subject and policy is content-addressed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "experiment/EXP011_bug_aware_harness_synthesis/schemas/budget_derivation_policy__v001.json"


def canonical(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {"relative_path": path.relative_to(ROOT).as_posix(), "content_hash": hashlib.sha256(path.read_bytes()).hexdigest()}


def verify_ref(ref):
    path = (ROOT / ref["relative_path"]).resolve()
    path.relative_to(ROOT)
    if reference(path) != {k: ref[k] for k in ('relative_path', 'content_hash')}:
        raise ValueError(f"Stale derivation evidence: {path}")
    return path


def load_ref(ref):
    path = verify_ref(ref)
    return json.loads(path.read_text()), path


def subject(record, path, kind):
    id_key = "spec_id" if kind == "spec" else "strategy_id"
    return {id_key: record["identity"][id_key], "revision_number": record["revision_information"]["revision_number"],
            "content_hash": canonical(record), "relative_path": str(Path(path).resolve())}


def authorize(path, record_path, kind, seen=None):
    path = Path(path).resolve()
    record_path = Path(record_path).resolve()
    record = json.loads(record_path.read_text())
    approval = json.loads(path.read_text())
    if approval.get("record_type") == "budget_derivation_certificate":
        validate(approval, path, record_path, kind, seen)
    else:
        from jsonschema import Draft202012Validator, FormatChecker
        schema_name = 'harness_spec_review_record.schema.json' if kind == 'spec' else 'strategy_plan_review_record.schema.json'
        schema = json.loads((POLICY.parent / schema_name).read_text())
        try:
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(approval)
        except Exception as exc:
            raise ValueError(f"Invalid {kind} human review record: {exc.message if hasattr(exc, 'message') else exc}") from exc
        if approval.get("decision") != "approved" or approval.get("subject") != subject(record, record_path, kind):
            # Existing reviews commonly store repository-relative subject paths.
            actual = dict(approval.get("subject", {}))
            if "relative_path" in actual:
                actual["relative_path"] = str((ROOT / actual["relative_path"]).resolve())
            if approval.get("decision") != "approved" or actual != subject(record, record_path, kind):
                raise ValueError("Parent has no exact approved human review")
        verify_ref(approval["rules_ref"])
    return approval


def validate(cert, cert_path, record_path, kind, seen=None):
    seen = set() if seen is None else set(seen)
    marker = str(Path(cert_path).resolve())
    if marker in seen: raise ValueError("Cyclic derivation authorization")
    seen.add(marker)
    if cert.get("record_type") != "budget_derivation_certificate" or cert.get("schema_version") != "1.0" or cert.get("subject_kind") != kind:
        raise ValueError("Unsupported derivation certificate")
    from jsonschema import Draft202012Validator, FormatChecker
    cert_schema = json.loads((POLICY.parent / "budget_derivation_certificate.schema.json").read_text())
    try:
        Draft202012Validator(cert_schema, format_checker=FormatChecker()).validate(cert)
    except Exception as exc:
        raise ValueError(f"Invalid budget derivation certificate: {exc.message if hasattr(exc, 'message') else exc}") from exc
    policy, policy_path = load_ref(cert["policy_file_ref"])
    if policy_path != POLICY or policy.get("allowed_change_scopes") != ["budget_allocation"]:
        raise ValueError("Unapproved derivation policy")
    record = json.loads(Path(record_path).read_text())
    if cert["subject"] != subject(record, record_path, kind):
        raise ValueError("Derivation subject does not match")
    parent_spec, parent_spec_path = load_ref(cert["parent_spec_file_ref"])
    parent_plan, parent_plan_path = load_ref(cert["parent_strategy_file_ref"])
    _, spec_auth_path = load_ref(cert["parent_spec_authorization_file_ref"])
    _, plan_auth_path = load_ref(cert["parent_strategy_authorization_file_ref"])
    authorize(spec_auth_path, parent_spec_path, "spec", seen)
    authorize(plan_auth_path, parent_plan_path, "strategy", seen)
    from build_strategy_plan_json import feedback_semantic_projection
    from build_harness_spec_json import validate_feedback_request
    parent_ref = {k: subject(parent_spec, parent_spec_path, "spec")[k] for k in ("spec_id", "revision_number", "content_hash")}
    if parent_plan["source_context"]["harness_spec_ref"] != parent_ref:
        raise ValueError("Parent Strategy implements a different Spec")
    candidate, candidate_path = (record, Path(record_path)) if kind == "spec" else load_ref(cert["candidate_spec_file_ref"])
    revision = candidate["revision_information"]
    request, _ = load_ref(cert["feedback_request_file_ref"])
    directive, proposed = validate_feedback_request(request, parent_spec)
    if (candidate['identity']['spec_id'] != directive['spec_id']
            or candidate['revision_information']['revision_number'] != directive['revision_number']
            or {b['branch_id']: b['budget_share'] for b in candidate['exploration_plan']['branches']} != {k: v / 256 for k, v in proposed.items()}
            or candidate['exploration_plan']['budget_policy_ref'] != request['input_references']['feedback_policy_ref']
            or revision['feedback_request_ref']['content_hash'] != cert['feedback_request_file_ref']['content_hash']):
        raise ValueError('Candidate budgets do not implement the exact validated request')
    if (candidate["identity"]["spec_mode"] != "bug_aware_adaptive" or revision["revision_trigger"] != "execution_feedback"
            or revision["change_scopes"] != ["budget_allocation"]
            or feedback_semantic_projection(candidate) != feedback_semantic_projection(parent_spec)
            or revision.get("parent_revision_ref", revision.get("derived_from_spec_ref")) not in (None, parent_ref)):
        raise ValueError("Certificate cannot authorize a semantic transformation")
    lineage = revision.get("derived_from_spec_ref") if revision["revision_number"] == 1 else revision.get("parent_revision_ref")
    if lineage != parent_ref or request.get("request_id") != revision["feedback_request_ref"]["artifact_id"]:
        raise ValueError("Feedback request/parent lineage differs")
    if kind == "strategy":
        child_ref = {k: subject(candidate, candidate_path, "spec")[k] for k in ("spec_id", "revision_number", "content_hash")}
        if record["implementation_plan"] != parent_plan["implementation_plan"] or record["source_context"]["harness_spec_ref"] != child_ref:
            raise ValueError("Derived Strategy changes the implementation")
        spec_auth = record["source_context"]["harness_spec_review_ref"]
        spec_cert_path = (ROOT / spec_auth["relative_path"]).resolve()
        spec_cert = json.loads(spec_cert_path.read_text())
        if canonical(spec_cert) != spec_auth["content_hash"]:
            raise ValueError("Derived Spec certificate hash mismatch")
        validate(spec_cert, spec_cert_path, candidate_path, "spec", seen)
    return cert


def create(kind, record_path, parent_spec, parent_strategy, spec_authorization, strategy_authorization, request, candidate_spec=None):
    record = json.loads(Path(record_path).read_text())
    cert = {"record_type": "budget_derivation_certificate", "schema_version": "1.0", "subject_kind": kind,
            "review_id": "derivation:" + canonical(record), "review_revision": 1,
            "subject": subject(record, record_path, kind), "policy_file_ref": reference(POLICY),
            "parent_spec_file_ref": reference(parent_spec), "parent_strategy_file_ref": reference(parent_strategy),
            "parent_spec_authorization_file_ref": reference(spec_authorization),
            "parent_strategy_authorization_file_ref": reference(strategy_authorization),
            "feedback_request_file_ref": reference(request)}
    if candidate_spec is not None: cert["candidate_spec_file_ref"] = reference(candidate_spec)
    return cert
