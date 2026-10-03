"""Batch Knowledge extraction from Pattern v4 (invokes the LLM)."""
import subprocess
import sys
from pathlib import Path

from build_knowledge_json import DEFAULT_OUTPUT_DIR, PATTERN_DIR


def main():
    root = Path(PATTERN_DIR)
    if not root.is_dir():
        raise SystemExit(f"Pattern v4 input directory does not exist: {root}")
    script = Path(__file__).with_name("build_knowledge_json.py")
    failed = 0
    for directory in sorted(root.iterdir()):
        if directory.is_dir() and any(directory.glob("*.json")):
            result = subprocess.run([sys.executable, "-B", str(script), "--api", directory.name,
                                     "--output", DEFAULT_OUTPUT_DIR], check=False)
            failed += result.returncode != 0
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
