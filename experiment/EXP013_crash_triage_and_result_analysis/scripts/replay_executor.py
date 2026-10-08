"""Single-input Docker replay and evidence verification. No synthesis or fuzz campaign."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Mapping

try:
    from case_semantics import diagnostic_signature
except ModuleNotFoundError:
    from experiment.EXP013_crash_triage_and_result_analysis.scripts.case_semantics import diagnostic_signature


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature_text(kind: str | None, text: str) -> str:
    marker = {"oracle_violation": "HBFG_ORACLE_FAILURE=", "target_exception": "HBFG_TARGET_API_EXCEPTION="}.get(kind)
    if marker is None:
        return text
    return "\n".join(line for line in text.splitlines() if marker in line)


def trace_sites(trace_text: str, input_bytes: bytes) -> list[int]:
    """Return instrumentation sites only for trace rows bound to these bytes."""
    selected = input_bytes.hex()
    invocations: dict[int, list[int]] = {}
    for line in trace_text.splitlines():
        row = json.loads(line)
        if row.get("input_hex") != selected:
            continue
        values = row.get("runtime_site_ids")
        if not isinstance(values, list) or any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("Invalid replay runtime-site trace")
        iteration = row.get("iteration")
        if not isinstance(iteration, int) or isinstance(iteration, bool):
            raise ValueError("Replay trace lacks invocation identity")
        invocations[iteration] = values
    return invocations[max(invocations)] if invocations else []


def file_ref(path: Path, root: Path) -> dict[str, str]:
    path = path.resolve()
    return {"relative_path": path.relative_to(root.resolve()).as_posix(), "content_hash": digest(path)}


def resolve(ref: Mapping[str, Any], root: Path) -> Path:
    path = (root / ref["relative_path"]).resolve()
    path.relative_to(root.resolve())
    if not path.is_file() or digest(path) != ref["content_hash"]:
        raise ValueError(f"Missing or stale replay evidence: {path}")
    return path


def execute(case: Mapping[str, Any], artifact: Mapping[str, Any], config: Mapping[str, Any],
            input_path: Path, binary: Path, output: Path, root: Path) -> dict[str, Any]:
    image = config["runtime_image"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Replay requires the pinned source Docker image ID")
    if "limits" not in config:
        raise ValueError("Source execution limits were not recorded; replay needs an explicit reviewed source configuration")
    output.mkdir(parents=True, exist_ok=False)
    (output / "observations").mkdir()
    limits = config["limits"]
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'EXP014_experimental_evaluation/scripts'))
    from execution_semantics import validate_limits
    validate_limits(limits)
    flags = [f"-{name}={limits[name]}" for name in ("timeout", "rss_limit_mb", "max_len") if limits.get(name) is not None]
    container_name = "hbfg-replay-" + uuid.uuid4().hex[:16]
    argv = ["docker", "run", "--rm", "--network", "none", "--name", container_name,
            "-e", f"HOST_UID={__import__('os').getuid()}", "-e", f"HOST_GID={__import__('os').getgid()}",
            "-v", f"{binary.resolve()}:/harness:ro", "-v", f"{input_path.resolve()}:/input:ro",
            "-v", f"{output.resolve()}:/output", "-e", "HBFG_REPLAY_TRACE=/output/trace.jsonl",
            "-e", "HBFG_CANDIDATE_DIR=/output/observations", "-e", f"HBFG_CANDIDATE_SAMPLE_LIMIT={limits.get('candidate_sample_limit',64)}",
            "-e", "LD_LIBRARY_PATH=/root/pytorch/build-fuzz/lib",
            *[part for key, value in config.get('thread_environment', {}).items() if value is not None
              for part in ('-e', f'{key}={value}')],
            *(["--memory", f"{limits['process_memory_mb']}m"] if limits.get("process_memory_mb") else []),
            image, "/harness", "/input", "-runs=1", f"-seed={config['seed']}", *flags]
    timeout = int(config.get('replay_watchdog_seconds', 180))
    infrastructure = "ok"
    try:
        process = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        text, returncode = process.stdout + "\n" + process.stderr, process.returncode
        if returncode in {125, 126, 127}:
            infrastructure = "container_failure"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        text, returncode, infrastructure = stdout + "\n" + stderr + f"\nreplay timeout after {timeout}s", None, "execution_unavailable"
    except OSError as exc:
        text, returncode, infrastructure = f"{type(exc).__name__}: {exc}", None, "execution_unavailable"
    finally:
        try:
            subprocess.run(['docker', 'rm', '-f', container_name], capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        # PyTorch libraries live under /root in the pinned runtime image, so
        # replay runs as root inside the isolated container. Restore host
        # ownership after preserving all diagnostics and traces.
        for path in output.rglob("*"):
            try:
                os.chown(path, os.getuid(), os.getgid())
            except OSError:
                pass
        try:
            os.chown(output, os.getuid(), os.getgid())
        except OSError:
            pass
    diagnostic_path = output / "diagnostic.txt"
    diagnostic_path.write_text(text, encoding="utf-8")
    sites = []
    trace_path = output / "trace.jsonl"
    if trace_path.is_file():
        try:
            sites = trace_sites(trace_path.read_text(), input_path.read_bytes())
        except (ValueError, KeyError):
            infrastructure = "invalid_trace"
    table = {b["runtime_site_id"]: b for b in artifact["instrumentation_map"]}
    reached = any(table.get(i, {}).get("event_kind") == "target_api_reached" for i in sites)
    kind, subtype = None, None
    matching_events = []
    for event_path in sorted((output / "observations").glob("event_*.json")):
        captured_input = event_path.with_suffix(".input")
        if captured_input.is_file() and digest(captured_input) == digest(input_path):
            event = json.loads(event_path.read_text())
            event_kind = {"target_exception": "target_exception", "oracle_failure": "oracle_violation"}.get(event.get("kind"))
            if event_kind is not None:
                matching_events.append((event_kind, "captured_target_exception" if event_kind == "target_exception" else "behavior_check_failure"))
    if re.search(r"AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:", text, re.I):
        kind, subtype = "sanitizer_finding", "sanitizer_finding"
    elif matching_events:
        kind, subtype = sorted(matching_events, key=lambda item: {"oracle_violation": 1, "target_exception": 3}[item[0]])[0]
    elif returncode not in {0, None} and infrastructure == "ok":
        if re.search(r"timeout|out.of.memory|rss limit", text, re.I):
            kind, subtype = "resource_anomaly", "timeout" if "timeout" in text.lower() else "oom"
        else:
            kind, subtype = "process_termination", "native_process_termination"
    observed = diagnostic_signature(kind, subtype, signature_text(kind, text)) if kind else None
    execution = {
        "record_type": "crash_replay_execution", "record_format_version": "1.0",
        "case_id": case["identity"]["case_id"], "source_round_ref": case["origin"]["fuzzing_round_ref"],
        "input_file_ref": file_ref(input_path, root), "binary_file_ref": file_ref(binary, root),
        "harness_artifact_hash": hashlib.sha256(json.dumps(artifact, ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "runtime_image": image, "limits": limits, "command": argv, "return_code": returncode,
        "infrastructure_status": infrastructure, "target_api_reach_status": "reached" if reached else "unknown",
        "diagnostic_file_ref": file_ref(diagnostic_path, root),
        "trace_file_ref": file_ref(trace_path, root) if trace_path.is_file() else None,
        "observed_event_kind": kind, "observed_event_subtype": subtype,
        "observed_signature_hash": None if observed is None else observed["signature_hash"],
    }
    return execution


def verified_attempt(execution: Mapping[str, Any], case: Mapping[str, Any], root: Path,
                     artifact: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    if execution.get("record_type") != "crash_replay_execution" or execution["case_id"] != case["identity"]["case_id"]:
        raise ValueError("Replay execution belongs to another Case")
    if (execution["source_round_ref"] != case["origin"]["fuzzing_round_ref"]
            or execution["input_file_ref"] != case["evidence"]["triggering_input_ref"]["file_ref"]
            or execution["binary_file_ref"] != artifact["validation"]["compile_check"]["binary_artifact"]
            or execution["runtime_image"] != config["runtime_image"] or execution["limits"] != config["limits"]):
        raise ValueError("Replay source input, build, environment or limits differ")
    for name in ("input_file_ref", "binary_file_ref", "diagnostic_file_ref"):
        resolve(execution[name], root)
    if "artifact_file_ref" not in execution or "config_file_ref" not in execution:
        raise ValueError("Replay does not reference its source Harness Artifact and Round config files")
    artifact_file = resolve(execution["artifact_file_ref"], root)
    config_file = resolve(execution["config_file_ref"], root)
    if json.loads(artifact_file.read_text(encoding="utf-8")) != artifact or json.loads(config_file.read_text(encoding="utf-8")) != config:
        raise ValueError("Replay Artifact or config file content differs from the supplied source records")
    artifact_hash = hashlib.sha256(json.dumps(artifact,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if execution["harness_artifact_hash"] != artifact_hash:
        raise ValueError("Replay Harness Artifact hash mismatch")
    capture = case.get("capture_record", {})
    source = capture.get("round_source_context", {})
    if source.get("harness_artifact_ref", {}).get("content_hash") != artifact_hash:
        raise ValueError("Replay build does not match the originally captured Harness")
    source_config = capture.get("candidate", {}).get("source_config_file_ref")
    if source_config is not None:
        if execution["config_file_ref"] != source_config:
            raise ValueError("Replay config reference differs from the captured attempt")
    elif hashlib.sha256(json.dumps(config,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest() != source.get("fuzzing_config_ref",{}).get("content_hash"):
        raise ValueError("Replay config does not match the originating Round")
    if config["harness_binary_ref"] != execution["binary_file_ref"] or config["task_key"] != case["origin"]["fuzzing_round_ref"]["artifact_id"]:
        raise ValueError("Replay source config has a different binary or logical Round")
    command = execution.get("command")
    if (not isinstance(command, list) or len(command) < 8 or command[:5] != ["docker", "run", "--rm", "--network", "none"]
            or config["runtime_image"] not in command or "-runs=1" not in command
            or f"-seed={config['seed']}" not in command
            or not any(str(resolve(execution["binary_file_ref"], root)) + ":/harness:ro" == item for item in command)
            or not any(str(resolve(execution["input_file_ref"], root)) + ":/input:ro" == item for item in command)):
        raise ValueError("Replay command does not execute the pinned image, binary, input and seed once")
    sites = []
    if execution["trace_file_ref"] is not None:
        trace = resolve(execution["trace_file_ref"], root)
        sites = trace_sites(trace.read_text(), resolve(execution["input_file_ref"], root).read_bytes())
    table = {b["runtime_site_id"]: b for b in artifact["instrumentation_map"]}
    if any(i not in table for i in sites): raise ValueError("Replay contains unknown runtime sites")
    reached = any(table[i]["event_kind"] == "target_api_reached" for i in sites)
    if execution["target_api_reach_status"] != ("reached" if reached else "unknown"):
        raise ValueError("Claimed target reach differs from trace")
    valid = execution["infrastructure_status"] == "ok" and reached and execution["return_code"] is not None and execution["return_code"] not in {125,126,127}
    text = resolve(execution["diagnostic_file_ref"],root).read_text()
    kind, subtype = execution["observed_event_kind"], execution["observed_event_subtype"]
    if kind in {"process_termination", "resource_anomaly"} and execution["return_code"] in {None,0}:
        raise ValueError("Process-failure conclusion contradicts execution outcome")
    if kind == "sanitizer_finding" and not re.search(r"Sanitizer|runtime error:",text,re.I):
        raise ValueError("Sanitizer conclusion lacks its original diagnostic")
    if kind == "oracle_violation" and "HBFG_ORACLE_FAILURE=" not in text:
        raise ValueError("Oracle conclusion lacks its original diagnostic")
    if kind == "target_exception" and "HBFG_TARGET_API_EXCEPTION=" not in text:
        raise ValueError("Exception conclusion lacks its original diagnostic")
    signature = diagnostic_signature(kind,subtype,signature_text(kind,text))["signature_hash"] if kind else None
    if signature != execution["observed_signature_hash"]:
        raise ValueError("Replay signature was not derived from the saved diagnostic")
    return {"valid_attempt": valid, "target_api_reach_status": "reached" if reached else "unknown",
            "invalid_reason": None if valid else "infrastructure_or_target_evidence_unavailable",
            "observed_event_kind": kind, "observed_signature_hash": signature}
