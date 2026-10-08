import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from template_contract import COMPATIBILITY_PATH, verify_template


class TemplateContractTests(unittest.TestCase):
    def test_registered_delta(self):
        manifest = json.loads(COMPATIBILITY_PATH.read_text())
        result = verify_template(ROOT / "templates/libfuzzer_harness_v1.cpp.in", manifest["parent_sha256"])
        self.assertEqual(result["status"], "runtime_compatible")

    def test_unrelated_change_rejected_and_exact_identity_supported(self):
        manifest = json.loads(COMPATIBILITY_PATH.read_text())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "template"
            data = (ROOT / "templates/libfuzzer_harness_v1.cpp.in").read_bytes() + b"// different\n"
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                verify_template(path, manifest["parent_sha256"])
            self.assertEqual(verify_template(path, hashlib.sha256(data).hexdigest())["status"], "exact")

    def test_unregistered_parent_rejected(self):
        with self.assertRaises(ValueError):
            verify_template(ROOT / "templates/libfuzzer_harness_v1.cpp.in", "0" * 64)
