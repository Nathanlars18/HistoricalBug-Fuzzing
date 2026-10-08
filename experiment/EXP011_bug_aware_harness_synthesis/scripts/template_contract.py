"""Verify exact template identity or an explicitly registered runtime-only delta."""
import hashlib
import json
from pathlib import Path

COMPATIBILITY_PATH = Path(__file__).resolve().parents[1] / "runtime/template_compatibility__v001.json"


def verify_template(path: Path, expected_hash: str) -> dict:
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual == expected_hash:
        return {"status": "exact", "template_sha256": actual}
    manifest = json.loads(COMPATIBILITY_PATH.read_text(encoding="utf-8"))
    if (manifest["transformation_id"] != "begin_iteration_input_binding_v1"
            or expected_hash != manifest["parent_sha256"]
            or actual != manifest["result_sha256"]):
        raise ValueError("Catalog template hash does not match the current template or registered runtime delta")
    new = b"  auto hbfg_iteration = hbfg_registry.begin_iteration(Data, Size);\n\n"
    anchor = b"  std::size_t hbfg_offset = 1;\n\n"
    if data.count(new) != 1 or data.count(anchor) != 1:
        raise ValueError("Runtime template delta is not uniquely reconstructible")
    parent = data.replace(new, b"", 1).replace(
        anchor, anchor + b"  auto hbfg_iteration = hbfg_registry.begin_iteration();\n\n", 1)
    if hashlib.sha256(parent).hexdigest() != expected_hash:
        raise ValueError("Runtime template delta alters the pinned parent template")
    return {"status": "runtime_compatible", "template_sha256": actual,
            "parent_sha256": expected_hash, "transformation_id": manifest["transformation_id"],
            "compatibility_manifest_sha256": hashlib.sha256(COMPATIBILITY_PATH.read_bytes()).hexdigest()}
