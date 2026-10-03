"""Batch extraction from current structured Reports (invokes the LLM)."""
import subprocess
import sys
from pathlib import Path

from build_pattern_json import DEFAULT_OUTPUT_DIR, latest_report_records


def discover_apis():
    return sorted({
        assertion["api_name"]
        for _, _, report in latest_report_records()
        for assertion in report.get("scope_assertions", {}).get("api_assertions", [])
        if assertion.get("relation") == "affected" and assertion.get("api_name")
    })


def main():
    script = Path(__file__).with_name("build_pattern_json.py")
    failed = 0
    for api in discover_apis():
        result = subprocess.run([sys.executable, "-B", str(script), "--api", api,
                                 "--output", DEFAULT_OUTPUT_DIR], check=False)
        failed += result.returncode != 0
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
