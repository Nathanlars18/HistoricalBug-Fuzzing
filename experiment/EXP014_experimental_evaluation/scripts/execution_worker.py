"""Container-local clock around the fuzzer process (including its initialization)."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def save(value):
    path = Path("/output/fuzzer_process.json")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value) + "\n", encoding="utf-8")
    temp.replace(path)


def main():
    started_wall = time.time()
    started = time.monotonic()
    record = {"state": "running", "started_epoch": started_wall, "initialization_included": True, "argv": sys.argv[1:]}
    save(record)
    try:
        with open("/output/fuzzer_stdout.log", "w") as stdout, open("/output/fuzzer_stderr.log", "w") as stderr:
            process = subprocess.run(sys.argv[1:], stdout=stdout, stderr=stderr, check=False)
        record.update(state="finished", ended_epoch=time.time(), elapsed_seconds=time.monotonic() - started, returncode=process.returncode)
        save(record)
        return process.returncode if process.returncode >= 0 else 128 - process.returncode
    except OSError as exc:
        record.update(state="launch_failed", message=str(exc), elapsed_seconds=0.0)
        save(record)
        return 126
    finally:
        uid, gid = int(os.environ["HOST_UID"]), int(os.environ["HOST_GID"])
        cleanup_errors = []
        for path in Path("/output").rglob("*"):
            try:
                os.chown(path, uid, gid)
            except OSError as exc:
                cleanup_errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
        if cleanup_errors:
            record["ownership_cleanup_errors"] = cleanup_errors
            try:
                save(record)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
