#!/usr/bin/env python3
"""Build and validate version-pinned PyTorch API Profile records.

This builder is deterministic and does not call an LLM. It collects facts; it
does not select Knowledge, design a HarnessSpec, or generate fuzzing strategy.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "jsonschema is required; install environment/python-control-requirements.txt"
    ) from exc


BUILDER_VERSION = "api_profile_builder_v0.6"
SCHEMA_VERSION = "1.3"
DEFAULT_RUNTIME_CONFIG = Path("runtime/flashfuzz_2_10/runtime_config.json")
DEFAULT_SCHEMA = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/"
    "schemas/api_profile_record.schema.json"
)
DEFAULT_VALIDATION_CASE_SCHEMA = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/"
    "schemas/api_profile_validation_case.schema.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/api_profiles"
)
DEFAULT_FLASHFUZZ_ROOT = Path("third_party/FlashFuzz")
DEFAULT_FLASHFUZZ_API_LIST = Path(
    "third_party/FlashFuzz/testharness_generation/torch_cpu/api.txt"
)


# Runs inside the pinned PyTorch image. Runtime import and source extraction are
# independent, so a C++-only image still yields versioned signatures/schemas.
SOURCE_PROBE = r"""
import ast
import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import yaml

root = Path("/root/pytorch")
api_name = sys.argv[1]
leaf = api_name.rsplit(".", 1)[-1]

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def node_text(node):
    return ast.unparse(node) if node is not None else None

def signatures(path, name):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    records = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != name:
            continue
        positional = list(node.args.posonlyargs) + list(node.args.args)
        defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
        params = []
        for index, (arg, default) in enumerate(zip(positional, defaults)):
            params.append({
                "name": arg.arg,
                "kind": "positional_only" if index < len(node.args.posonlyargs) else "positional_or_keyword",
                "annotation": node_text(arg.annotation),
                "default": node_text(default),
            })
        if node.args.vararg:
            params.append({"name": node.args.vararg.arg, "kind": "variadic_positional", "annotation": node_text(node.args.vararg.annotation), "default": None})
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            params.append({"name": arg.arg, "kind": "keyword_only", "annotation": node_text(arg.annotation), "default": node_text(default)})
        if node.args.kwarg:
            params.append({"name": node.args.kwarg.arg, "kind": "variadic_keyword", "annotation": node_text(node.args.kwarg.annotation), "default": None})
        rendered = ast.unparse(node)
        declaration = rendered.split(":\n", 1)[0].strip()
        records.append({"declaration": declaration, "parameters": params, "return_annotation": node_text(node.returns)})
    return records

def runtime_api(dotted_name):
    try:
        import torch
        obj = torch
        parts = dotted_name.split(".")
        if parts and parts[0] == "torch":
            parts = parts[1:]
        for part in parts:
            obj = getattr(obj, part)
        try:
            inspected_signature = inspect.signature(obj)
            signature = str(inspected_signature)
            parameters = []
            for parameter in inspected_signature.parameters.values():
                annotation = (
                    None if parameter.annotation is inspect.Parameter.empty
                    else inspect.formatannotation(parameter.annotation)
                )
                default = (
                    None if parameter.default is inspect.Parameter.empty
                    else repr(parameter.default)
                )
                parameters.append({
                    "name": parameter.name,
                    "kind": parameter.kind.name.lower(),
                    "annotation": annotation,
                    "default": default,
                })
            return_annotation = (
                None if inspected_signature.return_annotation is inspect.Signature.empty
                else inspect.formatannotation(inspected_signature.return_annotation)
            )
        except Exception:
            signature = None
            parameters = []
            return_annotation = None
        try:
            docstring = inspect.getdoc(obj)
        except Exception:
            docstring = None
        try:
            source_file = inspect.getsourcefile(obj)
            source_lines, source_line = inspect.getsourcelines(obj)
            source_text = "".join(source_lines)
            source_hash = (
                sha256_file(Path(source_file))
                if source_file and Path(source_file).is_file()
                else None
            )
        except Exception:
            source_file = None
            source_line = None
            source_text = None
            source_hash = None
        return {
            "resolved": True,
            "signature": signature,
            "parameters": parameters,
            "return_annotation": return_annotation,
            "docstring": docstring,
            "source_file": source_file,
            "source_line": source_line,
            "source_text": source_text,
            "source_hash": source_hash,
            "torch_version": getattr(torch, "__version__", None),
            "torch_git_version": getattr(getattr(torch, "version", None), "git_version", None),
            "torch_package_root": str(Path(torch.__file__).resolve().parent),
            "error": None,
        }
    except Exception as exc:
        return {
            "resolved": False,
            "signature": None,
            "parameters": [],
            "return_annotation": None,
            "docstring": None,
            "source_file": None,
            "source_line": None,
            "source_text": None,
            "source_hash": None,
            "torch_version": None,
            "torch_git_version": None,
            "torch_package_root": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

def identity(func):
    head = func.split("(", 1)[0].strip()
    namespace, name = head.split("::", 1) if "::" in head else ("aten", head)
    base, overload = name.split(".", 1) if "." in name else (name, "default")
    return namespace, base, overload

commit = subprocess.run(
    ["git", "-C", str(root), "rev-parse", "HEAD"],
    check=True, text=True, capture_output=True,
).stdout.strip()
runtime = runtime_api(api_name)
source_pyi_path = root / "torch/_C/_VariableFunctions.pyi"
package_root = runtime.get("torch_package_root")
wheel_pyi_path = (
    Path(package_root) / "_C/_VariableFunctions.pyi"
    if package_root
    else None
)
if source_pyi_path.exists():
    pyi_path = source_pyi_path
    pyi_origin = "source_repository"
elif wheel_pyi_path is not None and wheel_pyi_path.exists():
    pyi_path = wheel_pyi_path
    pyi_origin = "installed_wheel"
else:
    pyi_path = source_pyi_path
    pyi_origin = None
yaml_path = root / "aten/src/ATen/native/native_functions.yaml"
operators = []
if yaml_path.exists():
    for item in yaml.safe_load(yaml_path.read_text(encoding="utf-8")):
        func = str(item.get("func", ""))
        namespace, base, overload = identity(func)
        if base != leaf:
            continue
        variants = item.get("variants", "function")
        if isinstance(variants, str):
            variants = [part.strip() for part in variants.split(",") if part.strip()]
        operators.append({
            "operator_name": f"{namespace}::{base}",
            "operator_overload": overload,
            "operator_schema": func,
            "variants": variants,
        })

print(json.dumps({
    "framework_commit": commit,
    "runtime": runtime,
    "pyi": {
        "origin": pyi_origin,
        "path": str(pyi_path) if pyi_origin else None,
        "content_hash": sha256_file(pyi_path) if pyi_path.exists() else None,
        "signatures": signatures(pyi_path, leaf)
        if pyi_path.exists() and api_name.count(".") == 1
        else [],
    },
    "native_yaml": {
        "content_hash": sha256_file(yaml_path) if yaml_path.exists() else None,
        "operators": operators,
    },
}, ensure_ascii=False))
"""


class BuildError(RuntimeError):
    """A requested record cannot be safely materialized."""


class RuntimeProbeError(BuildError):
    """A C++ probe failed after producing preservable diagnostics."""

    def __init__(self, message: str, source: str, log: str) -> None:
        super().__init__(message)
        self.source = source
        self.log = log


@dataclass
class Outcome:
    api: str
    status: str
    paths: list[str] = field(default_factory=list)
    message: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def profile_hash(profile: dict[str, Any]) -> str:
    value = copy.deepcopy(profile)
    value["metadata"].pop("content_hash", None)
    return canonical_hash(value)


def semantic_payload(profile: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(profile)
    value.pop("revision", None)
    value.pop("metadata", None)
    value.pop("review", None)
    for item in value.get("evidence", []):
        item.pop("collected_at", None)
    return value


def safe_component(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    result = re.sub(r"_+", "_", result).strip("._-")
    if not result:
        raise BuildError(f"Cannot derive a path component from {value!r}")
    return result


def normalize_api(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"torch(?:\.[A-Za-z_][A-Za-z0-9_]*)+", value):
        raise BuildError(f"Unsupported PyTorch API name: {value!r}")
    return value


def collect_apis(direct: list[str], files: list[Path]) -> list[str]:
    values = list(direct)
    for path in files:
        if not path.is_file():
            raise BuildError(f"API list does not exist: {path}")
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                values.append(line)
    values = list(dict.fromkeys(value.strip() for value in values if value.strip()))
    if not values:
        raise BuildError("Provide at least one --api or --api-file")
    return values


def run_probe(image: str, api: str, timeout: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "-i", image, "python3", "-", api],
            input=SOURCE_PROBE,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BuildError("docker executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise BuildError(f"Probe timed out after {timeout}s") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise BuildError(f"Probe failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BuildError("Probe returned invalid JSON") from exc


RUNTIME_PROBE_SHELL = r"""
set -u
cat > /tmp/hbfg_api_probe.cpp
TORCH_ROOT="$(python3 -c 'import pathlib, torch; print(pathlib.Path(torch.__file__).resolve().parent)')"
ABI="$(python3 -c 'import torch; print(int(torch._C._GLIBCXX_USE_CXX11_ABI))')"
c++ -std=c++17 -D_GLIBCXX_USE_CXX11_ABI="$ABI" \
  -I"$TORCH_ROOT/include" \
  -I"$TORCH_ROOT/include/torch/csrc/api/include" \
  /tmp/hbfg_api_probe.cpp \
  -L"$TORCH_ROOT/lib" -Wl,-rpath,"$TORCH_ROOT/lib" \
  -ltorch -ltorch_cpu -lc10 -o /tmp/hbfg_api_probe \
  > /tmp/hbfg_compile.log 2>&1
compile_status=$?
cat /tmp/hbfg_compile.log
printf 'HBFG_COMPILE_STATUS=%s\n' "$compile_status"
if [ "$compile_status" -ne 0 ]; then
  exit "$compile_status"
fi
/tmp/hbfg_api_probe > /tmp/hbfg_run.log 2>&1
run_status=$?
cat /tmp/hbfg_run.log
printf 'HBFG_RUN_STATUS=%s\n' "$run_status"
exit "$run_status"
"""


def cpp_value_expression(
    index: int,
    parameter: dict[str, Any],
    value: dict[str, Any] | None,
) -> tuple[str | None, str]:
    schema_type = str(parameter["schema_type"]).strip()
    optional = schema_type.endswith("?")
    base_type = schema_type[:-1].strip() if optional else schema_type
    if re.fullmatch(r"Tensor(?:\([^)]*\))?", base_type):
        base_type = "Tensor"
    variable = f"hbfg_arg_{index}"

    if value is not None:
        kind = value["kind"]
        if kind == "none":
            if not optional:
                raise BuildError(f"Validation case cannot assign none to {parameter['name']}")
            return None, "std::nullopt"
        if kind == "tensor" and base_type == "Tensor":
            dtype = {
                "float32": "torch::kFloat32",
                "float64": "torch::kFloat64",
                "int64": "torch::kInt64",
                "bool": "torch::kBool",
            }[value["dtype"]]
            fill = "ones" if value["fill"] == "ones" else "zeros"
            shape = ", ".join(str(item) for item in value["shape"])
            declaration = (
                f"    auto {variable} = torch::{fill}({{{shape}}}, "
                f"torch::TensorOptions().dtype({dtype}).device(torch::kCPU));"
            )
            return declaration, variable
        if kind == "floating" and base_type == "float":
            return f"    double {variable} = {float(value['value'])!r};", variable
        if kind == "integer" and base_type in {"int", "SymInt"}:
            ctype = "c10::SymInt" if base_type == "SymInt" else "int64_t"
            return f"    {ctype} {variable} = {int(value['value'])};", variable
        if kind == "boolean" and base_type == "bool":
            literal = "true" if value["value"] else "false"
            return f"    bool {variable} = {literal};", variable
        raise BuildError(
            f"Validation case kind {kind!r} is incompatible with "
            f"{parameter['name']}: {schema_type}"
        )

    if optional:
        return None, "std::nullopt"
    if base_type == "Tensor":
        return (
            f"    auto {variable} = torch::ones({{2, 2}}, "
            "torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));",
            variable,
        )
    if base_type == "float":
        return f"    double {variable} = 0.1;", variable
    if base_type == "int":
        return f"    int64_t {variable} = 1;", variable
    if base_type == "SymInt":
        return f"    c10::SymInt {variable} = 1;", variable
    if base_type == "bool":
        return f"    bool {variable} = false;", variable
    raise BuildError(
        "Runtime promotion supports Tensor, float, integer, boolean, "
        "and their optional forms; "
        f"unsupported {parameter['name']}: {schema_type}"
    )


def validate_runtime_case(
    profile: dict[str, Any],
    runtime_case: dict[str, Any],
    case_schema: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    errors = sorted(
        jsonschema.Draft202012Validator(case_schema).iter_errors(runtime_case),
        key=lambda item: list(item.path),
    )
    if errors:
        detail = "; ".join(
            f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
            for error in errors[:10]
        )
        raise BuildError(f"Validation case schema failed: {detail}")
    reference = runtime_case["target"]
    expected = {
        "framework_commit": profile["target"]["framework_commit"],
        "python_api": profile["target"]["python_api"],
        "operator_name": profile["target_binding"]["operator_name"],
        "operator_overload": profile["target_binding"]["operator_overload"],
    }
    if reference != expected:
        raise BuildError("Validation case target does not match the promoted Profile")
    evidence_ids = [item["evidence_id"] for item in runtime_case["evidence"]]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise BuildError("Validation case evidence IDs are not unique")
    unknown_evidence = set(runtime_case["source_evidence_refs"]) - set(evidence_ids)
    if unknown_evidence:
        raise BuildError(
            f"Validation case has unknown source_evidence_refs: {sorted(unknown_evidence)}"
        )
    known_refs = {
        item["binding_parameter_id"]
        for item in profile["target_binding"]["binding_parameters"]
    }
    by_ref: dict[str, dict[str, Any]] = {}
    for argument in runtime_case["arguments"]:
        ref = argument["binding_parameter_ref"]
        if ref not in known_refs:
            raise BuildError(f"Validation case references unknown binding parameter: {ref}")
        if ref in by_ref:
            raise BuildError(f"Validation case repeats binding parameter: {ref}")
        by_ref[ref] = argument["value"]
    return by_ref


def cpp_runtime_probe_source(
    profile: dict[str, Any],
    case_arguments: dict[str, dict[str, Any]] | None = None,
) -> str:
    binding = profile["target_binding"]
    callable_name = binding.get("cpp_callable")
    if not isinstance(callable_name, str) or not re.fullmatch(
        r"at::[A-Za-z_][A-Za-z0-9_]*", callable_name
    ):
        raise BuildError("Runtime promotion requires a resolved at::<callable>")

    declarations: list[str] = []
    arguments: list[str] = []
    omitted_default = False
    for index, parameter in enumerate(
        sorted(binding["binding_parameters"], key=lambda item: item["ordinal"])
    ):
        if parameter["default"] is not None:
            omitted_default = True
            continue
        if omitted_default:
            raise BuildError(
                "Runtime promotion cannot bind a required parameter after an "
                "omitted default"
            )
        value = (
            case_arguments.get(parameter["binding_parameter_id"])
            if case_arguments is not None else None
        )
        declaration, expression = cpp_value_expression(index, parameter, value)
        if declaration is not None:
            declarations.append(declaration)
        arguments.append(expression)

    body = "\n".join(declarations)
    return f"""#include <torch/torch.h>
#include <cstdint>
#include <exception>
#include <iostream>
#include <optional>

int main() {{
  try {{
{body}
    auto hbfg_result = {callable_name}({", ".join(arguments)});
    (void)hbfg_result;
    std::cout << "HBFG_TARGET_REACHED" << std::endl;
    return 0;
  }} catch (const std::exception& error) {{
    std::cerr << "HBFG_TARGET_EXCEPTION: " << error.what() << std::endl;
    return 90;
  }}
}}
"""


def run_cpp_runtime_probe(
    image: str,
    profile: dict[str, Any],
    timeout: int,
    case_arguments: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, str, str]:
    source = cpp_runtime_probe_source(profile, case_arguments)
    try:
        image_result = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        result = subprocess.run(
            ["docker", "run", "--rm", "-i", image, "sh", "-lc", RUNTIME_PROBE_SHELL],
            input=source,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BuildError("docker executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise BuildError(f"C++ runtime probe timed out after {timeout}s") from exc

    image_id = image_result.stdout.strip()
    if image_result.returncode or not image_id:
        detail = (image_result.stderr or image_result.stdout).strip()[-2000:]
        raise BuildError(f"Cannot resolve Docker image ID: {detail}")
    compile_match = re.search(r"HBFG_COMPILE_STATUS=(\d+)", result.stdout)
    run_match = re.search(r"HBFG_RUN_STATUS=(\d+)", result.stdout)
    compile_status = int(compile_match.group(1)) if compile_match else None
    run_status = int(run_match.group(1)) if run_match else None
    log = (
        f"docker_image={image}\n"
        f"docker_image_id={image_id}\n"
        f"source_sha256={hashlib.sha256(source.encode('utf-8')).hexdigest()}\n"
        "--- source ---\n"
        f"{source}"
        "--- stdout ---\n"
        f"{result.stdout}"
        "--- stderr ---\n"
        f"{result.stderr}"
    )
    if compile_status != 0:
        raise RuntimeProbeError(
            "C++ API probe compilation failed: "
            + (result.stdout + result.stderr).strip()[-2000:], source, log
        )
    if result.returncode != 0 or run_status != 0:
        raise RuntimeProbeError(
            "C++ API probe execution failed: "
            + (result.stdout + result.stderr).strip()[-2000:], source, log
        )
    if "HBFG_TARGET_REACHED" not in result.stdout:
        raise RuntimeProbeError(
            "C++ API probe did not emit target-reached evidence", source, log
        )
    return source, log, image_id


def promote_runtime_profile(
    profile_path: Path,
    args: argparse.Namespace,
    runtime_config: dict[str, Any],
    schema: dict[str, Any],
) -> Outcome:
    source_profile = load_json(profile_path)
    expected_commit = runtime_config["source_inputs"]["pytorch"]["commit"]
    validate_profile(source_profile, schema, expected_commit=expected_commit)
    if source_profile["target_binding"]["status"] != "resolved":
        raise BuildError("Runtime promotion requires target_binding.status=resolved")
    if source_profile["target_binding"].get("binding_kind", "aten_operator") != "aten_operator":
        raise BuildError("Runtime promotion currently supports only aten_operator bindings")

    collected_at = utc_now()
    run_id = collected_at.replace("-", "").replace(":", "").replace(".", "")
    log_path = (
        args.output_root
        / "_runs"
        / f"api_profile_runtime_validation__{safe_component(run_id)}"
        / f"{safe_component(source_profile['target']['python_api'])}.log"
    )
    runtime_case = None
    case_arguments = None
    if args.validation_case is not None:
        runtime_case = load_json(args.validation_case)
        case_schema = load_json(args.validation_case_schema)
        case_arguments = validate_runtime_case(source_profile, runtime_case, case_schema)
    try:
        source, log, image_id = run_cpp_runtime_probe(
            args.docker_image,
            source_profile,
            args.probe_timeout,
            case_arguments,
        )
    except RuntimeProbeError as exc:
        failed_path = log_path.with_suffix(".failed.log")
        if not args.dry_run:
            failed_path.parent.mkdir(parents=True, exist_ok=True)
            failed_path.write_text(exc.log, encoding="utf-8")
        raise BuildError(f"{exc} Full diagnostics: {failed_path}") from exc
    if not args.dry_run:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(log, encoding="utf-8")
    log_hash = hashlib.sha256(log.encode("utf-8")).hexdigest()

    profile = copy.deepcopy(source_profile)
    profile["metadata"]["generated_at"] = collected_at
    profile["metadata"]["builder_version"] = BUILDER_VERSION
    profile["evidence"] = [
        item
        for item in profile["evidence"]
        if item["evidence_id"] not in {
            "ev_cpp_compile_validation",
            "ev_cpp_smoke_execution",
        }
    ]
    profile["evidence"].extend(
        [
            evidence(
                "ev_cpp_compile_validation",
                "build_log",
                log_path.as_posix(),
                image_id,
                "HBFG_COMPILE_STATUS=0",
                log_hash,
                source,
                collected_at,
            ),
            evidence(
                "ev_cpp_smoke_execution",
                "runtime_trace",
                log_path.as_posix(),
                image_id,
                "HBFG_RUN_STATUS=0 and HBFG_TARGET_REACHED",
                log_hash,
                "C++ probe invoked the resolved target and terminated normally.",
                collected_at,
            ),
        ]
    )
    if runtime_case is not None:
        case_text = json.dumps(runtime_case, ensure_ascii=False, sort_keys=True)
        profile["evidence"].append(evidence(
            "ev_runtime_validation_case",
            "validation_case",
            args.validation_case.as_posix(),
            runtime_case["schema_version"],
            runtime_case["case_id"],
            file_hash(args.validation_case),
            case_text,
            collected_at,
        ))
    check_updates = {
        "check_cpp_compile": (
            "ev_cpp_compile_validation",
            "Resolved C++ callable compiled in the pinned runtime.",
        ),
        "check_cpp_smoke_execution": (
            "ev_cpp_smoke_execution",
            "Compiled C++ API probe terminated normally.",
        ),
        "check_target_reachability": (
            "ev_cpp_smoke_execution",
            "The resolved target callable was reached by the C++ probe.",
        ),
    }
    for check in profile["validation"]["checks"]:
        update = check_updates.get(check["check_id"])
        if update is not None:
            check["status"] = "passed"
            check["summary"] = update[1]
            check["evidence_refs"] = [update[0]] + (
                ["ev_runtime_validation_case"] if runtime_case is not None else []
            )
    blocking_issues = [
        item for item in profile["validation"]["issues"] if item["blocking"]
    ]
    if blocking_issues:
        issue_ids = ", ".join(item["issue_id"] for item in blocking_issues)
        raise BuildError(
            "Runtime promotion cannot approve a Profile with blocking issues: "
            f"{issue_ids}"
        )
    blocked_checks = [
        check["check_id"]
        for check in profile["validation"]["checks"]
        if check["status"] == "blocked"
    ]
    if blocked_checks:
        raise BuildError(
            "Runtime promotion cannot approve a Profile with blocked checks: "
            + ", ".join(blocked_checks)
        )
    profile["validation"]["validation_status"] = "passed"
    profile["validation"]["execution_readiness"] = "ready"
    profile["review"] = {
        "review_status": "unreviewed",
        "reviewer": None,
        "reviewed_at": None,
        "issue_refs": [],
    }
    profile["metadata"]["content_hash"] = profile_hash(profile)
    status, destination = materialize(
        profile,
        args.output_root,
        schema,
        args.dry_run,
        expected_commit,
    )
    return Outcome(
        api=source_profile["target"]["python_api"],
        status=status,
        paths=[destination.as_posix()],
    )


def split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = start = 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def parse_native_schema(schema: str) -> tuple[list[dict[str, Any]], list[str]]:
    match = re.match(r"^[^(]+\((.*)\)\s*->\s*(.+)$", schema)
    if not match:
        return [], []
    raw_parameters, raw_returns = match.groups()
    parameters: list[dict[str, Any]] = []
    keyword_only = False
    for item in split_top_level(raw_parameters):
        if item == "*":
            keyword_only = True
            continue
        parsed = re.match(
            r"^(?P<type>.+?)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:=(?P<default>.*))?$",
            item,
        )
        if parsed:
            parameters.append({
                "name": parsed.group("name"),
                "schema_type": parsed.group("type").strip(),
                "default": parsed.group("default"),
                "keyword_only": keyword_only,
            })
    returns = raw_returns.strip()
    if returns.startswith("(") and returns.endswith(")"):
        returns = returns[1:-1]
    return parameters, split_top_level(returns)


def normalized_types(type_text: str | None) -> list[str]:
    if not type_text:
        return ["unknown"]
    lowered = type_text.lower().strip()
    optional = lowered.startswith("optional[") and lowered.endswith("]")
    if optional:
        lowered = lowered[len("optional["):-1]

    parts: list[str] = []
    depth = start = 0
    for index, char in enumerate(lowered):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif char == "|" and depth == 0:
            parts.append(lowered[start:index].strip())
            start = index + 1
    parts.append(lowered[start:].strip())

    def classify(part: str) -> str:
        root = part.split("[", 1)[0].strip()
        normalized_root = root.rsplit(".", 1)[-1].lstrip("_")
        if part.endswith("[]") or (root in {"list", "sequence"} and "tensor" in part):
            return "tensor_sequence"
        if "tensor" in normalized_root:
            return "tensor"
        if normalized_root in {"symint", "int", "integer"}:
            return "integer"
        if normalized_root in {"float", "double"}:
            return "floating"
        if normalized_root == "scalar":
            return "scalar"
        if normalized_root in {"bool", "boolean"}:
            return "boolean"
        if normalized_root in {"str", "string"}:
            return "string"
        if normalized_root in {"dtype", "scalartype"}:
            return "dtype"
        if normalized_root == "device":
            return "device"
        if normalized_root == "layout":
            return "layout"
        if normalized_root == "memoryformat":
            return "memory_format"
        if normalized_root == "generator":
            return "generator"
        if normalized_root == "callable":
            return "callable"
        if normalized_root in {"none", "nonetype", "null"}:
            return "none"
        return "object"

    found: list[str] = []
    for part in parts:
        value = classify(part)
        if value not in found:
            found.append(value)
    if optional and "none" not in found:
        found.append("none")
    return found or ["object"]


def semantic_role(name: str, types: list[str], ordinal: int) -> str:
    lowered = name.lower()
    if lowered in {"dim", "dims", "axis", "axes"}:
        return "dimension_selector"
    if "shape" in lowered or lowered in {"size", "sizes"}:
        return "shape"
    for role in ("dtype", "device", "layout", "memory_format"):
        if role in types:
            return role
    if "index" in lowered or "indices" in lowered:
        return "index_tensor" if "tensor" in types else "configuration"
    if "tensor" in types or "tensor_sequence" in types:
        return "input_tensor" if ordinal == 0 else "other_tensor"
    if any(item in types for item in ("scalar", "integer", "floating")):
        return "scalar"
    if "boolean" in types:
        return "boolean_flag"
    return "configuration" if types != ["unknown"] else "unknown"


def default_value(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {"kind": "no_default", "value": None}
    if raw == "None":
        return {"kind": "none_literal", "value": None}
    try:
        value = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return {"kind": "runtime_defined", "value": None}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return {"kind": "literal", "value": value}
    return {"kind": "literal", "value": raw}


def evidence(
    evidence_id: str,
    source_kind: str,
    source_location: str,
    source_revision: str | None,
    locator: str | None,
    content_hash: str | None,
    excerpt: str | None,
    collected_at: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_kind": source_kind,
        "source_location": source_location,
        "source_revision": source_revision,
        "locator": locator,
        "content_hash": content_hash,
        "excerpt": excerpt[:1000] if excerpt else None,
        "collected_at": collected_at,
    }


def source_url(commit: str, relative_path: str) -> str:
    return f"https://github.com/pytorch/pytorch/blob/{commit}/{relative_path}"


def collect_flashfuzz_support(
    api: str,
    root: Path,
    api_list: Path,
    expected_commit: str,
    collected_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    commit = result.stdout.strip()
    if result.returncode or commit != expected_commit:
        raise BuildError(
            f"FlashFuzz commit mismatch: expected {expected_commit}, found {commit or 'unknown'}"
        )
    if not api_list.is_file():
        raise BuildError(f"FlashFuzz API list does not exist: {api_list}")
    entries = {
        line.strip()
        for line in api_list.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    present = api in entries
    record = {
        "flashfuzz_commit": commit,
        "api_list_status": "listed" if present else "unlisted",
        "evidence_refs": ["ev_flashfuzz_api_list"],
    }
    proof = evidence(
        "ev_flashfuzz_api_list", "flashfuzz_api_list", api_list.as_posix(),
        commit, api, file_hash(api_list), api if present else None, collected_at,
    )
    return record, proof


def select_python_contract(probe: dict[str, Any]) -> dict[str, Any]:
    """Select one Python-facing contract without substituting an ATen schema."""

    runtime = probe["runtime"]
    runtime_signature = runtime.get("signature")
    if runtime_signature:
        return {
            "signature": runtime_signature,
            "parameters": runtime.get("parameters", []),
            "return_annotation": runtime.get("return_annotation"),
            "source": "runtime_signature",
            "signature_coverage": "complete",
            "parameter_coverage": "complete",
            "return_coverage": (
                "complete" if runtime.get("return_annotation") else "partial"
            ),
        }

    declarations = probe["pyi"].get("signatures", [])
    if len(declarations) == 1:
        declaration = declarations[0]
        return {
            "signature": declaration["declaration"],
            "parameters": declaration["parameters"],
            "return_annotation": declaration.get("return_annotation"),
            "source": "python_stub",
            "signature_coverage": "complete",
            "parameter_coverage": "complete",
            "return_coverage": (
                "complete" if declaration.get("return_annotation") else "partial"
            ),
        }
    return {
        "signature": (
            " | ".join(item["declaration"] for item in declarations)
            if declarations else None
        ),
        "parameters": [],
        "return_annotation": None,
        "source": "python_stub" if declarations else None,
        "signature_coverage": "conflicting" if declarations else "missing",
        "parameter_coverage": "conflicting" if declarations else "missing",
        "return_coverage": "conflicting" if declarations else "missing",
    }


def build_python_parameters(
    source_parameters: list[dict[str, Any]],
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    records = []
    for ordinal, item in enumerate(source_parameters):
        types = normalized_types(item.get("annotation"))
        default = default_value(item.get("default"))
        records.append({
            "parameter_id": f"param_{ordinal:03d}_{safe_component(item['name'])}",
            "name": item["name"],
            "ordinal": None if item["kind"].startswith("variadic") else ordinal,
            "parameter_kind": item["kind"],
            "required": default["kind"] == "no_default" and not item["kind"].startswith("variadic"),
            "documented_type": item.get("annotation"),
            "normalized_types": types,
            "default": default,
            "semantic_role": semantic_role(item["name"], types, ordinal),
            "normalization_basis": "deterministic",
            "constraint_refs": [],
            "evidence_refs": evidence_refs,
        })
    return records


def build_returns(
    return_annotation: str | None,
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    source: list[str] = []
    if return_annotation:
        source = [return_annotation]
        try:
            expression = ast.parse(return_annotation, mode="eval").body
        except SyntaxError:
            expression = None
        if isinstance(expression, ast.Subscript):
            root = expression.value
            root_name = (
                root.id if isinstance(root, ast.Name)
                else root.attr if isinstance(root, ast.Attribute)
                else None
            )
            elements = (
                list(expression.slice.elts)
                if isinstance(expression.slice, ast.Tuple)
                else []
            )
            if (
                root_name is not None
                and root_name.lower() == "tuple"
                and elements
                and not any(
                    isinstance(item, ast.Constant) and item.value is Ellipsis
                    for item in elements
                )
            ):
                source = [
                    ast.get_source_segment(return_annotation, item)
                    or ast.unparse(item)
                    for item in elements
                ]
    records = []
    for position, item in enumerate(source):
        types = normalized_types(item)
        if "tensor_sequence" in types:
            role = "result_tensor_sequence"
        elif "tensor" in types:
            role = "result_tensor"
        elif "boolean" in types:
            role = "boolean_result"
        elif any(value in types for value in ("scalar", "integer", "floating")):
            role = "scalar_result"
        else:
            role = "object_result"
        records.append({
            "return_id": f"return_{position:03d}",
            "position": position,
            "documented_type": item,
            "normalized_types": types,
            "semantic_role": role,
            "description": None,
            "evidence_refs": evidence_refs,
        })
    return records


def _resolve_wrapper_expression(
    expression: ast.AST,
    assignments: dict[str, ast.AST | None],
    resolving: set[str] | None = None,
) -> ast.AST | None:
    """Resolve wrapper-local temporaries without replacing API parameters."""

    resolving = set() if resolving is None else set(resolving)
    if isinstance(expression, ast.Name) and expression.id in assignments:
        if expression.id in resolving:
            return copy.deepcopy(expression)
        if assignments[expression.id] is None:
            return None
        resolving.add(expression.id)
        return _resolve_wrapper_expression(
            copy.deepcopy(assignments[expression.id]), assignments, resolving
        )

    resolved = copy.deepcopy(expression)

    class Resolver(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802
            if not isinstance(node.ctx, ast.Load) or node.id not in assignments:
                return node
            replacement = _resolve_wrapper_expression(node, assignments, resolving)
            if replacement is None:
                raise ValueError(f"Ambiguous wrapper assignment for {node.id}")
            return ast.copy_location(replacement, node)

    try:
        return ast.fix_missing_locations(Resolver().visit(resolved))
    except ValueError:
        return None


def _assigned_names(statements: list[ast.stmt]) -> set[str]:
    names: set[str] = set()
    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
    return names


def _apply_wrapper_statements(
    statements: list[ast.stmt],
    incoming: dict[str, ast.AST | None],
) -> dict[str, ast.AST | None]:
    """Track simple assignments and join if/else definitions conservatively."""

    environment = dict(incoming)
    for statement in statements:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = (
                statement.targets if isinstance(statement, ast.Assign)
                else [statement.target]
            )
            value = _resolve_wrapper_expression(statement.value, environment)
            for target in targets:
                if isinstance(target, ast.Name):
                    environment[target.id] = value
            continue
        if isinstance(statement, ast.If):
            body = _apply_wrapper_statements(statement.body, environment)
            alternate = _apply_wrapper_statements(statement.orelse, environment)
            changed = _assigned_names(statement.body) | _assigned_names(statement.orelse)
            for name in changed:
                before = environment.get(name, ast.Name(id=name, ctx=ast.Load()))
                body_value = body.get(name, before)
                alternate_value = alternate.get(name, before)
                if body_value is None or alternate_value is None:
                    environment[name] = None
                elif ast.dump(body_value) == ast.dump(alternate_value):
                    environment[name] = body_value
                else:
                    test = _resolve_wrapper_expression(statement.test, environment)
                    environment[name] = (
                        ast.IfExp(
                            test=test,
                            body=body_value,
                            orelse=alternate_value,
                        )
                        if test is not None else None
                    )
            continue
        if isinstance(statement, (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match)):
            for name in _assigned_names([statement]):
                environment[name] = None
    return environment


def _wrapper_call_context(
    wrapper_source: str | None,
    target_leaf: str,
) -> tuple[list[ast.AST] | None, dict[str, ast.AST], dict[str, ast.AST | None]]:
    if not wrapper_source:
        return None, {}, {}
    try:
        tree = ast.parse(wrapper_source)
    except (SyntaxError, ValueError):
        return None, {}, {}
    functions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if not functions:
        return None, {}, {}
    environment: dict[str, ast.AST | None] = {}
    for statement in functions[0].body:
        if not isinstance(statement, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match)):
            calls = [
                node for node in ast.walk(statement)
                if isinstance(node, ast.Call)
                and (
                    (isinstance(node.func, ast.Name) and node.func.id == target_leaf)
                    or (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == target_leaf
                    )
                )
            ]
            if calls:
                target = calls[-1]
                return (
                    list(target.args),
                    {
                        keyword.arg: keyword.value
                        for keyword in target.keywords
                        if keyword.arg is not None
                    },
                    environment,
                )
        environment = _apply_wrapper_statements([statement], environment)
    return None, {}, environment


def build_argument_mapping(
    python_parameters: list[dict[str, Any]],
    binding_parameters: list[dict[str, Any]],
    wrapper_source: str | None,
    target_leaf: str,
    evidence_refs: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    by_name = {item["name"]: item for item in python_parameters}
    records: list[dict[str, Any]] = []
    complete = True
    call_arguments, keyword_arguments, assignment_values = _wrapper_call_context(
        wrapper_source, target_leaf
    )

    mapped_python_refs: dict[str, tuple[str, str | None]] = {}
    for item in binding_parameters:
        source = by_name.get(item["name"])
        if source is not None:
            binding_type_text = item["schema_type"]
            if binding_type_text.endswith("?"):
                binding_type_text = binding_type_text[:-1] + " | None"
            python_types = set(source["normalized_types"]) - {"none", "unknown"}
            binding_types = set(normalized_types(binding_type_text)) - {"none", "unknown"}
            numeric_compatible = (
                "scalar" in python_types
                and bool(binding_types & {"integer", "floating"})
            ) or (
                "scalar" in binding_types
                and bool(python_types & {"integer", "floating"})
            )
            if (
                python_types and binding_types
                and not (python_types & binding_types)
                and not numeric_compatible
            ):
                source = None
        kind = "unresolved"
        transformation = None
        mapping_evidence = list(evidence_refs)
        raw_expression: ast.AST | None = keyword_arguments.get(item["name"])
        if raw_expression is None and call_arguments is not None:
            ordinal = item["ordinal"]
            if ordinal < len(call_arguments):
                raw_expression = call_arguments[ordinal]
        expression = (
            _resolve_wrapper_expression(raw_expression, assignment_values)
            if raw_expression is not None else None
        )
        source_refs: list[str] = []
        expression_classified = False
        if raw_expression is not None and expression is None:
            complete = False
        elif expression is not None:
            names = sorted(
                {
                    node.id for node in ast.walk(expression)
                    if isinstance(node, ast.Name) and node.id in by_name
                },
                key=lambda name: (
                    by_name[name]["ordinal"] is None,
                    by_name[name]["ordinal"]
                    if by_name[name]["ordinal"] is not None else 0,
                    name,
                ),
            )
            if isinstance(expression, ast.Name) and expression.id in by_name:
                source = by_name[expression.id]
                kind = "direct" if expression.id == item["name"] else "renamed"
                transformation = None if kind == "direct" else ast.unparse(expression)
                source_refs = [source["parameter_id"]]
                expression_classified = True
            elif len(names) == 1:
                source = by_name[names[0]]
                kind = "converted"
                transformation = ast.unparse(expression)
                source_refs = [source["parameter_id"]]
                expression_classified = True
            elif len(names) > 1:
                source = None
                kind = "packed"
                transformation = ast.unparse(expression)
                source_refs = [by_name[name]["parameter_id"] for name in names]
                expression_classified = True
            elif isinstance(expression, ast.Constant):
                source = None
                kind = "default_injected"
                transformation = ast.unparse(expression)
                expression_classified = True
        if not expression_classified and raw_expression is None and source is not None:
            kind = "direct"
            source_refs = [source["parameter_id"]]
        elif not expression_classified and raw_expression is None and item["default"] is not None:
            kind = "default_injected"
        elif not expression_classified:
            complete = False
        source_ref = source_refs[0] if len(source_refs) == 1 else None
        for parameter_ref in source_refs:
            disposition = "converted" if kind in {"converted", "packed"} else "mapped"
            previous = mapped_python_refs.get(parameter_ref)
            if previous is None or disposition == "converted":
                mapped_python_refs[parameter_ref] = (disposition, transformation)
        records.append({
            "python_parameter_ref": source_ref,
            "source_parameter_refs": source_refs,
            "binding_parameter_ref": item["binding_parameter_id"],
            "mapping_kind": kind,
            "transformation": transformation,
            "evidence_refs": mapping_evidence,
        })

    wrapper_names: set[str] = set()
    if wrapper_source:
        try:
            wrapper_names = {
                node.id for node in ast.walk(ast.parse(wrapper_source))
                if isinstance(node, ast.Name)
            }
        except SyntaxError:
            wrapper_names = set()
    dispositions = []
    for parameter in python_parameters:
        parameter_ref = parameter["parameter_id"]
        mapped = mapped_python_refs.get(parameter_ref)
        if mapped is None:
            if wrapper_source and parameter["name"] in wrapper_names:
                disposition = "consumed_by_wrapper"
                description = "Consumed by the Python wrapper outside the selected binding expression."
            else:
                disposition = "unresolved"
                description = None
                complete = False
        else:
            disposition, expression_text = mapped
            description = (
                f"Participates in binding expression: {expression_text}"
                if expression_text else None
            )
        dispositions.append({
            "python_parameter_ref": parameter_ref,
            "disposition": disposition,
            "description": description,
            "evidence_refs": list(evidence_refs),
        })
    return records, dispositions, complete


def wrapper_calls_operator(wrapper_source: str | None, operator_leaf: str) -> bool:
    if not wrapper_source:
        return False
    try:
        tree = ast.parse(wrapper_source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == operator_leaf)
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == operator_leaf
            )
        )
        for node in ast.walk(tree)
    )


def build_validation(
    runtime_resolved: bool,
    runtime_doc_available: bool,
    runtime_version_mismatch: bool,
    signature_resolved: bool,
    binding_kind: str,
    argument_mapping_complete: bool,
    return_mapping_complete: bool,
    cpp_resolved: bool,
    refs: dict[str, str],
) -> dict[str, Any]:
    def check(
        check_id: str,
        kind: str,
        status: str,
        summary: str,
        proof: list[str],
    ) -> dict[str, Any]:
        return {
            "check_id": check_id,
            "check_kind": kind,
            "backend": "cpu",
            "status": status,
            "summary": summary,
            "evidence_refs": proof,
        }

    aten_route = binding_kind == "aten_operator"
    checks = [
        check(
            "check_python_resolution", "python_resolution",
            "passed" if runtime_resolved else "blocked",
            (
                "Python API resolved in the pinned runtime."
                if runtime_resolved
                else "Python API is unavailable in the selected runtime image."
            ),
            [refs[key] for key in ("signature", "doc") if refs.get(key)],
        ),
        check(
            "check_signature_resolution", "signature_resolution",
            "passed" if signature_resolved else "blocked",
            (
                "One structured Python signature was resolved."
                if signature_resolved
                else "No unambiguous structured Python signature was resolved."
            ),
            [refs["signature"]] if refs.get("signature") else [],
        ),
        check(
            "check_operator_schema_resolution", "operator_schema_resolution",
            ("passed" if refs.get("schema") else "blocked") if aten_route else "not_applicable",
            (
                "One target operator schema was selected."
                if aten_route and refs.get("schema")
                else "No target operator schema was resolved."
                if aten_route
                else "The selected execution route is Python-level and has no single ATen schema."
            ),
            [refs["schema"]] if refs.get("schema") else [],
        ),
        check(
            "check_argument_mapping", "argument_mapping",
            ("passed" if argument_mapping_complete else "blocked") if aten_route else "not_applicable",
            (
                "Python-to-binding argument mapping is complete."
                if aten_route and argument_mapping_complete
                else "Python-to-binding argument mapping is incomplete."
                if aten_route
                else "No Python-to-ATen mapping is required for the Python-level route."
            ),
            [refs[key] for key in ("signature", "wrapper", "schema") if refs.get(key)],
        ),
        check(
            "check_return_mapping", "return_mapping",
            ("passed" if return_mapping_complete else "blocked") if aten_route else "not_applicable",
            (
                "Binding-to-Python return mapping is complete."
                if aten_route and return_mapping_complete
                else "Binding-to-Python return mapping is incomplete."
                if aten_route
                else "No ATen return mapping is required for the Python-level route."
            ),
            [refs[key] for key in ("signature", "wrapper", "schema") if refs.get(key)],
        ),
        check(
            "check_cpp_binding_resolution", "cpp_binding_resolution",
            ("passed" if cpp_resolved else "blocked") if aten_route else "not_applicable",
            (
                "A C++/ATen callable candidate was resolved."
                if aten_route and cpp_resolved
                else "No C++/ATen callable candidate was resolved."
                if aten_route
                else "The Python-level route requires a non-C++ execution adapter."
            ),
            [refs["schema"]] if refs.get("schema") else [],
        ),
    ]
    for check_id, kind, summary in (
        ("check_cpp_compile", "cpp_compile", "Compile validation was not requested."),
        ("check_cpp_smoke_execution", "cpp_smoke_execution", "Smoke execution was not requested."),
        ("check_target_reachability", "target_reachability", "Target reachability was not measured."),
    ):
        checks.append({
            "check_id": check_id,
            "check_kind": kind,
            "backend": "cpu",
            "status": "not_run" if aten_route else "not_applicable",
            "summary": summary,
            "evidence_refs": [],
        })

    issues = []
    if runtime_version_mismatch:
        issues.append({
            "issue_id": "issue_runtime_version_mismatch",
            "issue_kind": "version_mismatch",
            "blocking": True,
            "description": "Imported torch runtime does not match the pinned PyTorch commit.",
            "affected_refs": ["target", "python_contract"],
            "evidence_refs": [],
        })
    if not runtime_doc_available and not runtime_version_mismatch:
        issues.append({
            "issue_id": "issue_runtime_doc_unavailable",
            "issue_kind": "missing_documentation",
            "blocking": False,
            "description": (
                "The pinned runtime exposes no docstring for the requested Python API."
                if runtime_resolved
                else "Runtime docstring collection is unavailable in the selected image."
            ),
            "affected_refs": ["python_contract"],
            "evidence_refs": [],
        })
    if not signature_resolved:
        issues.append({
            "issue_id": "issue_signature_ambiguity",
            "issue_kind": "signature_ambiguity",
            "blocking": True,
            "description": "No unambiguous structured Python signature was resolved.",
            "affected_refs": ["python_contract"],
            "evidence_refs": [refs["signature"]] if refs.get("signature") else [],
        })
    if aten_route and not refs.get("schema"):
        issues.append({
            "issue_id": "issue_binding_unresolved",
            "issue_kind": "binding_unresolved",
            "blocking": True,
            "description": "No exact target-version operator schema was resolved.",
            "affected_refs": ["target_binding"],
            "evidence_refs": [],
        })
    if aten_route and not argument_mapping_complete:
        issues.append({
            "issue_id": "issue_argument_mapping_unresolved",
            "issue_kind": "argument_mapping_unresolved",
            "blocking": True,
            "description": "A required binding argument lacks a Python mapping.",
            "affected_refs": ["target_binding"],
            "evidence_refs": [refs["schema"]],
        })
    if aten_route and not return_mapping_complete:
        issues.append({
            "issue_id": "issue_return_mapping_unresolved",
            "issue_kind": "return_mapping_unresolved",
            "blocking": True,
            "description": "A binding return position lacks a supported Python return mapping.",
            "affected_refs": ["target_binding", "python_contract.returns"],
            "evidence_refs": [
                refs[key] for key in ("signature", "wrapper", "schema")
                if refs.get(key)
            ],
        })
    if not aten_route:
        issues.append({
            "issue_id": "issue_execution_adapter_required",
            "issue_kind": "execution_adapter_required",
            "blocking": False,
            "description": (
                "The API is represented as a Python-level callable; the current "
                "C++ Harness pipeline requires a separate execution adapter."
            ),
            "affected_refs": ["target_binding", "validation"],
            "evidence_refs": [refs["signature"]] if refs.get("signature") else [],
        })
    blocking = any(item["blocking"] for item in issues)
    readiness = "blocked" if blocking else "unassessed" if aten_route else "needs_adapter"
    return {
        "validation_status": (
            "failed" if blocking else "partial" if aten_route else "passed"
        ),
        "execution_readiness": readiness,
        "checks": checks,
        "issues": issues,
    }


def build_profile(
    api: str,
    operator: dict[str, Any] | None,
    probe: dict[str, Any],
    runtime_config: dict[str, Any],
    ff_support: dict[str, Any],
    ff_evidence: dict[str, Any],
    backend: str,
    collected_at: str,
    source_image: str,
) -> dict[str, Any]:
    commit = probe["framework_commit"]
    expected = runtime_config["source_inputs"]["pytorch"]["commit"]
    if commit != expected:
        raise BuildError(f"PyTorch commit mismatch: expected {expected}, found {commit}")

    contract = select_python_contract(probe)
    signature = contract["signature"]
    runtime = probe["runtime"]
    runtime_verified = bool(runtime.get("resolved")) and runtime.get("torch_git_version") == commit
    runtime_mismatch = bool(runtime.get("resolved")) and not runtime_verified
    proofs: list[dict[str, Any]] = []
    refs = {"flashfuzz": ff_evidence["evidence_id"]}
    docstring = runtime.get("docstring") if runtime_verified else None
    if docstring:
        refs["doc"] = "ev_runtime_docstring"
        proofs.append(evidence(
            refs["doc"], "runtime_docstring",
            f"container://{source_image}/{api}",
            commit, api, canonical_hash(docstring), docstring, collected_at,
        ))
    if contract["source"] == "runtime_signature" and signature:
        refs["signature"] = "ev_runtime_signature"
        proofs.append(evidence(
            refs["signature"], "runtime_signature",
            f"container://{source_image}/{api}",
            commit, api, canonical_hash(signature), signature, collected_at,
        ))
    elif contract["source"] == "python_stub" and probe["pyi"].get("content_hash"):
        refs["signature"] = "ev_python_signature_source"
        pyi_location = (
            source_url(commit, "torch/_C/_VariableFunctions.pyi")
            if probe["pyi"].get("origin") == "source_repository"
            else f"container://{source_image}{probe['pyi']['path']}"
        )
        proofs.append(evidence(
            refs["signature"], "pytorch_source",
            pyi_location, commit,
            api.rsplit(".", 1)[-1], probe["pyi"]["content_hash"], signature, collected_at,
        ))

    wrapper_source = runtime.get("source_text") if runtime_verified else None
    wrapper_file = runtime.get("source_file") if runtime_verified else None
    if wrapper_source and wrapper_file:
        refs["wrapper"] = "ev_python_wrapper_source"
        source_path = Path(wrapper_file)
        try:
            relative_source = source_path.relative_to("/root/pytorch")
            wrapper_location = source_url(commit, relative_source.as_posix())
        except ValueError:
            wrapper_location = f"container://{source_image}{wrapper_file}"
        proofs.append(evidence(
            refs["wrapper"], "python_wrapper_source", wrapper_location, commit,
            f"{api}:L{runtime.get('source_line')}" if runtime.get("source_line") else api,
            runtime.get("source_hash"), wrapper_source, collected_at,
        ))

    native_parameters: list[dict[str, Any]] = []
    native_returns: list[str] = []
    if operator:
        native_parameters, native_returns = parse_native_schema(operator["operator_schema"])
        refs["schema"] = "ev_operator_schema"
        proofs.append(evidence(
            refs["schema"], "operator_schema",
            source_url(commit, "aten/src/ATen/native/native_functions.yaml"), commit,
            f"{operator['operator_name']}.{operator['operator_overload']}",
            probe["native_yaml"].get("content_hash"), operator["operator_schema"], collected_at,
        ))
    contract_refs = [refs[key] for key in ("doc", "signature") if refs.get(key)]
    parameters = build_python_parameters(contract["parameters"], [refs["signature"]] if refs.get("signature") else [])
    returns = build_returns(contract["return_annotation"], [refs["signature"]] if refs.get("signature") else [])
    binding_parameters = [
        {
            "binding_parameter_id": f"binding_param_{index:03d}_{safe_component(item['name'])}",
            "name": item["name"],
            "ordinal": index,
            "schema_type": item["schema_type"],
            "default": item["default"],
        }
        for index, item in enumerate(native_parameters)
    ]
    if operator:
        binding_kind = "aten_operator"
        operator_name = operator["operator_name"]
        overload = operator["operator_overload"]
        cpp_callable = (
            f"at::{operator_name.split('::', 1)[-1]}"
            if "function" in operator.get("variants", []) else None
        )
        binding_token = f"{operator_name.replace('::', '.')}.{overload}"
    else:
        binding_kind = "python_callable"
        operator_name = overload = cpp_callable = None
        binding_status, binding_token = (
            ("resolved", "python_callable")
            if runtime_verified and signature else ("unresolved", "python_callable")
        )

    if operator:
        mapping, parameter_dispositions, argument_mapping_complete = build_argument_mapping(
            parameters,
            binding_parameters,
            wrapper_source,
            operator_name.split("::", 1)[-1],
            [refs[key] for key in ("signature", "wrapper", "schema") if refs.get(key)],
        )
        binding_status = "partial"
    else:
        mapping = []
        argument_mapping_complete = True
        parameter_dispositions = [
            {
                "python_parameter_ref": item["parameter_id"],
                "disposition": "not_applicable_to_binding",
                "description": "The selected route invokes the Python callable directly.",
                "evidence_refs": [refs["signature"]] if refs.get("signature") else [],
            }
            for item in parameters
        ]

    return_mapping = [
        {
            "binding_return_position": index,
            "python_return_ref": returns[index]["return_id"] if index < len(returns) else None,
            "mapping_kind": "direct" if index < len(returns) else "unresolved",
            "description": None,
            "evidence_refs": [refs["schema"]] if refs.get("schema") else [],
        }
        for index in range(len(native_returns))
    ]
    return_mapping_complete = (
        not operator
        or (
            len(native_returns) == len(returns)
            and all(item["mapping_kind"] != "unresolved" for item in return_mapping)
        )
    )
    if operator:
        binding_status = (
            "resolved"
            if cpp_callable and argument_mapping_complete and return_mapping_complete
            else "partial"
        )
    proofs.append(ff_evidence)
    profile_id = ":".join([
        "api_prof", "pytorch", runtime_config["source_inputs"]["pytorch"]["tag"],
        backend, api, "python_default", binding_token,
    ])
    profile = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "revision": 1,
        "metadata": {
            "parent_revision_ref": None,
            "generated_at": collected_at,
            "builder_version": BUILDER_VERSION,
            "content_hash": "0" * 64,
        },
        "target": {
            "framework": "pytorch",
            "framework_version": runtime_config["source_inputs"]["pytorch"]["tag"],
            "framework_commit": commit,
            "backend_scope": [backend],
            "python_api": api,
            "callable_kind": "tensor_method" if api.startswith("torch.Tensor.") else "function",
            "python_variant": "python_default",
            "aliases": [],
        },
        "python_contract": {
            "documentation_status": (
                "partial" if docstring or signature
                else "missing"
            ),
            "coverage": {
                "signature": contract["signature_coverage"],
                "parameters": contract["parameter_coverage"],
                "returns": contract["return_coverage"],
                "domains": "not_collected",
                "exceptions": "not_collected",
                "constraints": "not_collected",
                "effects": "not_collected",
            },
            "signature": signature,
            "behavior_summary": (
                re.sub(r"\s+", " ", docstring.split("\n\n", 1)[0])[:1000]
                if docstring else None
            ),
            "parameters": parameters,
            "returns": returns,
            "documented_domains": [],
            "documented_exceptions": [],
            "evidence_refs": contract_refs,
        },
        "target_binding": {
            "binding_kind": binding_kind,
            "status": binding_status,
            "operator_name": operator_name,
            "operator_overload": overload,
            "operator_schema": operator["operator_schema"] if operator else None,
            "cpp_callable": cpp_callable,
            "binding_parameters": binding_parameters,
            "argument_mapping": mapping,
            "parameter_dispositions": parameter_dispositions,
            "return_mapping": return_mapping,
            "evidence_refs": [
                refs[key] for key in ("signature", "wrapper", "schema")
                if refs.get(key)
            ],
        },
        "documented_constraints": [],
        "effects": [],
        "flashfuzz_support": ff_support,
        "validation": build_validation(
            runtime_verified,
            bool(docstring),
            runtime_mismatch,
            bool(signature) and contract["parameter_coverage"] == "complete",
            binding_kind,
            argument_mapping_complete,
            return_mapping_complete,
            cpp_callable is not None,
            refs,
        ),
        "evidence": proofs,
        "review": {
            "review_status": "unreviewed",
            "reviewer": None,
            "reviewed_at": None,
            "issue_refs": [],
        },
    }
    profile["metadata"]["content_hash"] = profile_hash(profile)
    return profile


def validate_profile(
    profile: dict[str, Any],
    schema: dict[str, Any],
    expected_api: str | None = None,
    expected_commit: str | None = None,
) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(profile),
        key=lambda item: list(item.path),
    )
    if errors:
        detail = "; ".join(
            f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
            for error in errors[:10]
        )
        raise BuildError(f"JSON Schema validation failed: {detail}")
    if profile["metadata"]["content_hash"] != profile_hash(profile):
        raise BuildError("metadata.content_hash is not reproducible")
    if expected_api and profile["target"]["python_api"] != expected_api:
        raise BuildError("target.python_api does not match the requested API")
    if expected_commit and profile["target"]["framework_commit"] != expected_commit:
        raise BuildError("target.framework_commit does not match runtime configuration")
    if profile["revision"] == 1 and profile["metadata"]["parent_revision_ref"] is not None:
        raise BuildError("Revision 1 must have parent_revision_ref = null")

    evidence_ids = [item["evidence_id"] for item in profile["evidence"]]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise BuildError("Evidence IDs are not unique")

    referenced_evidence: set[str] = set()
    def collect_evidence_refs(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence_refs":
                    referenced_evidence.update(child)
                else:
                    collect_evidence_refs(child)
        elif isinstance(value, list):
            for child in value:
                collect_evidence_refs(child)

    collect_evidence_refs(profile)
    missing = sorted(referenced_evidence - set(evidence_ids))
    if missing:
        raise BuildError(f"Unknown evidence references: {missing}")

    parameters = profile["python_contract"]["parameters"]
    returns = profile["python_contract"]["returns"]
    binding = profile["target_binding"]
    binding_parameters = binding["binding_parameters"]
    id_groups = {
        "parameter": [item["parameter_id"] for item in parameters],
        "return": [item["return_id"] for item in returns],
        "binding parameter": [item["binding_parameter_id"] for item in binding_parameters],
        "constraint": [item["constraint_id"] for item in profile["documented_constraints"]],
        "effect": [item["effect_id"] for item in profile.get("effects", [])],
        "validation check": [item["check_id"] for item in profile["validation"]["checks"]],
        "validation issue": [item["issue_id"] for item in profile["validation"]["issues"]],
    }
    for label, identifiers in id_groups.items():
        if len(identifiers) != len(set(identifiers)):
            raise BuildError(f"Duplicate {label} IDs")

    parameter_ids = set(id_groups["parameter"])
    binding_parameter_ids = set(id_groups["binding parameter"])
    return_ids = set(id_groups["return"])
    for item in binding["argument_mapping"]:
        if item["python_parameter_ref"] is not None and item["python_parameter_ref"] not in parameter_ids:
            raise BuildError("argument_mapping contains an unknown Python parameter reference")
        if item["binding_parameter_ref"] not in binding_parameter_ids:
            raise BuildError("argument_mapping contains an unknown binding parameter reference")
        if profile["schema_version"] == "1.3":
            source_refs = item["source_parameter_refs"]
            unknown_sources = set(source_refs) - parameter_ids
            if unknown_sources:
                raise BuildError(
                    "argument_mapping contains unknown source_parameter_refs: "
                    f"{sorted(unknown_sources)}"
                )
            if (
                item["python_parameter_ref"] is not None
                and item["python_parameter_ref"] not in source_refs
            ):
                raise BuildError(
                    "python_parameter_ref must be included in source_parameter_refs"
                )
            if item["mapping_kind"] in {"direct", "renamed", "converted"} and len(source_refs) != 1:
                raise BuildError(
                    f"{item['mapping_kind']} mapping requires exactly one source parameter"
                )
            if item["mapping_kind"] == "packed" and len(source_refs) < 2:
                raise BuildError("packed mapping requires at least two source parameters")
            if item["mapping_kind"] in {"default_injected", "omitted"} and source_refs:
                raise BuildError(
                    f"{item['mapping_kind']} mapping cannot claim source parameters"
                )
    for item in binding["return_mapping"]:
        if item["python_return_ref"] is not None and item["python_return_ref"] not in return_ids:
            raise BuildError("return_mapping contains an unknown Python return reference")
    constraint_ids = set(id_groups["constraint"])
    for item in parameters:
        unknown_constraints = set(item["constraint_refs"]) - constraint_ids
        if unknown_constraints:
            raise BuildError(
                f"Parameter {item['parameter_id']} has unknown constraint_refs: "
                f"{sorted(unknown_constraints)}"
            )
    if profile["schema_version"] in {"1.2", "1.3"}:
        dispositions = binding["parameter_dispositions"]
        disposition_refs = [item["python_parameter_ref"] for item in dispositions]
        if len(disposition_refs) != len(set(disposition_refs)):
            raise BuildError("parameter_dispositions contains duplicate Python references")
        if set(disposition_refs) != parameter_ids:
            raise BuildError("parameter_dispositions must cover every Python parameter exactly once")
        mapped_binding_refs = [item["binding_parameter_ref"] for item in binding["argument_mapping"]]
        if binding["binding_kind"] == "aten_operator" and (
            set(mapped_binding_refs) != binding_parameter_ids
            or len(mapped_binding_refs) != len(binding_parameter_ids)
        ):
            raise BuildError("argument_mapping must cover every ATen binding parameter exactly once")
    if profile["schema_version"] == "1.3" and binding["binding_kind"] == "aten_operator":
        return_positions = [
            item["binding_return_position"] for item in binding["return_mapping"]
        ]
        if return_positions != list(range(len(return_positions))):
            raise BuildError(
                "return_mapping must cover contiguous binding return positions exactly once"
            )
        mapped_return_refs = []
        for item in binding["return_mapping"]:
            if item["mapping_kind"] in {"unresolved", "unpacked"}:
                if binding["status"] == "resolved":
                    raise BuildError(
                        "ATen return_mapping contains a mapping unsupported by the current pipeline"
                    )
                continue
            if item["mapping_kind"] == "omitted":
                continue
            if item["python_return_ref"] is None:
                raise BuildError("Resolved return mapping requires python_return_ref")
            mapped_return_refs.append(item["python_return_ref"])
        if len(mapped_return_refs) != len(set(mapped_return_refs)):
            raise BuildError("return_mapping repeats a Python return reference")
        if binding["status"] == "resolved" and set(mapped_return_refs) != return_ids:
            raise BuildError("return_mapping must resolve every documented Python return")
    unknown_review_issues = set(profile["review"]["issue_refs"]) - set(id_groups["validation issue"])
    if unknown_review_issues:
        raise BuildError(f"review.issue_refs contains unknown IDs: {sorted(unknown_review_issues)}")

    parent = profile["metadata"]["parent_revision_ref"]
    if profile["revision"] > 1:
        if parent is None:
            raise BuildError("Revision greater than 1 requires parent_revision_ref")
        if parent["profile_id"] != profile["profile_id"] or parent["revision"] >= profile["revision"]:
            raise BuildError("parent_revision_ref does not identify an earlier revision of this profile")
    binding_kind = binding.get("binding_kind", "aten_operator")
    if binding["status"] == "resolved" and binding_kind == "aten_operator" and not (
        binding["operator_schema"] and binding["cpp_callable"]
    ):
        raise BuildError("Resolved ATen binding requires operator_schema and cpp_callable")
    if binding_kind == "python_callable" and any(
        binding.get(key) is not None
        for key in ("operator_name", "operator_overload", "operator_schema", "cpp_callable")
    ):
        raise BuildError("Python-callable binding must not claim an ATen operator")
    validation = profile["validation"]
    if validation["execution_readiness"] == "ready":
        if validation["validation_status"] != "passed":
            raise BuildError("execution_readiness=ready requires validation_status=passed")
        required_checks = {
            "cpp_compile", "cpp_smoke_execution", "target_reachability"
        }
        if profile["schema_version"] == "1.3":
            required_checks.update({"argument_mapping", "return_mapping"})
        passed_kinds = {
            item["check_kind"] for item in validation["checks"]
            if item["status"] == "passed"
        }
        if binding_kind != "aten_operator" or not required_checks <= passed_kinds:
            raise BuildError("execution_readiness=ready requires passed ATen runtime checks")
    if profile["review"]["review_status"] == "approved":
        if binding["status"] != "resolved" or validation["validation_status"] == "failed":
            raise BuildError("Approved review requires a resolved, non-failed Profile")


def existing_revisions(api_dir: Path, binding_slug: str) -> list[tuple[Path, dict[str, Any]]]:
    records = []
    for candidate in sorted(api_dir.glob(f"api_profile__{binding_slug}__r*.json")):
        try:
            records.append((candidate, load_json(candidate)))
        except (OSError, json.JSONDecodeError) as exc:
            raise BuildError(f"Cannot read existing revision {candidate}: {exc}") from exc
    return records


def materialize(
    profile: dict[str, Any],
    output_root: Path,
    schema: dict[str, Any],
    dry_run: bool,
    expected_commit: str,
    force_revision: bool = False,
) -> tuple[str, Path]:
    api = profile["target"]["python_api"]
    binding = profile["target_binding"]
    token = (
        f"{binding['operator_name'].replace('::', '.')}.{binding['operator_overload']}"
        if binding["operator_name"] else "unresolved"
    )
    if binding.get("binding_kind") == "python_callable":
        token = "python_callable"
    binding_slug = safe_component(token)
    api_dir = (
        output_root
        / "pytorch"
        / safe_component(profile["target"]["framework_version"])
        / profile["target"]["backend_scope"][0]
        / safe_component(api)
    )
    existing = existing_revisions(api_dir, binding_slug)
    if existing:
        latest_path, latest = max(existing, key=lambda item: item[1]["revision"])
        if latest["profile_id"] != profile["profile_id"]:
            raise BuildError(f"Profile identity collision at {latest_path}")
        if not force_revision and semantic_payload(latest) == semantic_payload(profile):
            validate_profile(latest, schema, api, expected_commit)
            return "unchanged", latest_path
        profile["revision"] = latest["revision"] + 1
        profile["metadata"]["parent_revision_ref"] = {
            "profile_id": latest["profile_id"],
            "revision": latest["revision"],
            "content_hash": latest["metadata"]["content_hash"],
        }
        profile["metadata"]["content_hash"] = profile_hash(profile)

    destination = api_dir / f"api_profile__{binding_slug}__r{profile['revision']:03d}.json"
    validate_profile(profile, schema, api, expected_commit)
    if not dry_run:
        api_dir.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return ("planned" if dry_run else "created"), destination


def review_profile(
    profile_path: Path,
    args: argparse.Namespace,
    runtime_config: dict[str, Any],
    schema: dict[str, Any],
) -> Outcome:
    source_profile = load_json(profile_path)
    expected_commit = runtime_config["source_inputs"]["pytorch"]["commit"]
    validate_profile(source_profile, schema, expected_commit=expected_commit)
    binding = source_profile["target_binding"]
    token = (
        f"{binding['operator_name'].replace('::', '.')}.{binding['operator_overload']}"
        if binding["operator_name"] else
        "python_callable" if binding.get("binding_kind") == "python_callable" else
        "unresolved"
    )
    api_dir = (
        args.output_root / "pytorch"
        / safe_component(source_profile["target"]["framework_version"])
        / source_profile["target"]["backend_scope"][0]
        / safe_component(source_profile["target"]["python_api"])
    )
    revisions = existing_revisions(api_dir, safe_component(token))
    if revisions:
        _, latest = max(revisions, key=lambda item: item[1]["revision"])
        if latest["metadata"]["content_hash"] != source_profile["metadata"]["content_hash"]:
            raise BuildError("Human review must target the latest retained Profile revision")
    decision = args.review_decision
    if decision == "approved":
        if source_profile["target_binding"]["status"] != "resolved":
            raise BuildError("Approval requires target_binding.status=resolved")
        if source_profile["validation"]["validation_status"] != "passed":
            raise BuildError("Approval requires validation.validation_status=passed")
    known_issue_ids = {
        item["issue_id"] for item in source_profile["validation"]["issues"]
    }
    requested_issue_ids = set(args.review_issue)
    unknown = sorted(requested_issue_ids - known_issue_ids)
    if unknown:
        raise BuildError(f"Unknown --review-issue values: {unknown}")
    if decision == "approved":
        requested_issue_ids.update(known_issue_ids)

    profile = copy.deepcopy(source_profile)
    collected_at = utc_now()
    profile["metadata"]["generated_at"] = collected_at
    profile["metadata"]["builder_version"] = BUILDER_VERSION
    profile["review"] = {
        "review_status": decision,
        "reviewer": args.reviewer.strip(),
        "reviewed_at": collected_at,
        "issue_refs": sorted(requested_issue_ids),
    }
    profile["metadata"]["content_hash"] = profile_hash(profile)
    status, destination = materialize(
        profile,
        args.output_root,
        schema,
        args.dry_run,
        expected_commit,
        force_revision=True,
    )
    return Outcome(
        api=source_profile["target"]["python_api"],
        status=status,
        paths=[destination.as_posix()],
    )


def build_api(
    api: str,
    args: argparse.Namespace,
    runtime_config: dict[str, Any],
    schema: dict[str, Any],
) -> Outcome:
    collected_at = utc_now()
    probe = run_probe(args.docker_image, api, args.probe_timeout)
    support, support_evidence = collect_flashfuzz_support(
        api,
        args.flashfuzz_root,
        args.flashfuzz_api_list,
        runtime_config["source_inputs"]["flashfuzz"]["base_commit"],
        collected_at,
    )
    candidates = probe["native_yaml"].get("operators", [])
    if api.count(".") > 1:
        wrapper_source = probe.get("runtime", {}).get("source_text")
        candidates = [
            candidate for candidate in candidates
            if wrapper_calls_operator(
                wrapper_source,
                candidate["operator_name"].split("::", 1)[-1],
            )
        ]
    candidates = candidates or [None]
    statuses: list[str] = []
    paths: list[str] = []
    for operator in candidates:
        profile = build_profile(
            api,
            operator,
            probe,
            runtime_config,
            copy.deepcopy(support),
            copy.deepcopy(support_evidence),
            args.backend,
            collected_at,
            args.docker_image,
        )
        status, destination = materialize(
            profile,
            args.output_root,
            schema,
            args.dry_run,
            runtime_config["source_inputs"]["pytorch"]["commit"],
        )
        statuses.append(status)
        paths.append(destination.as_posix())
    status = (
        "unchanged" if all(item == "unchanged" for item in statuses)
        else "planned" if args.dry_run
        else "created"
    )
    return Outcome(api=api, status=status, paths=paths)


def validate_files(paths: list[Path], schema: dict[str, Any]) -> int:
    failures = 0
    for path in paths:
        try:
            validate_profile(load_json(path), schema)
            print(f"[VALID] {path}")
        except (OSError, json.JSONDecodeError, BuildError) as exc:
            failures += 1
            print(f"[INVALID] {path}: {exc}", file=sys.stderr)
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic, version-pinned PyTorch API Profiles"
    )
    parser.add_argument("--api", action="append", default=[], help="Python API; repeatable")
    parser.add_argument("--api-file", action="append", type=Path, default=[], help="One API per line")
    parser.add_argument("--runtime-config", type=Path, default=DEFAULT_RUNTIME_CONFIG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--validation-case-schema",
        type=Path,
        default=DEFAULT_VALIDATION_CASE_SCHEMA,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--flashfuzz-root", type=Path, default=DEFAULT_FLASHFUZZ_ROOT)
    parser.add_argument("--flashfuzz-api-list", type=Path, default=DEFAULT_FLASHFUZZ_API_LIST)
    parser.add_argument("--docker-image", help="Override runtime-config API metadata image")
    parser.add_argument("--backend", choices=["cpu"], default="cpu")
    parser.add_argument("--probe-timeout", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--summary-json", type=Path, help="Optional machine-readable run summary")
    parser.add_argument("--validate-only", action="append", type=Path, default=[], metavar="PROFILE")
    parser.add_argument(
        "--promote-runtime",
        action="append",
        type=Path,
        default=[],
        metavar="PROFILE",
        help="Compile and execute an existing resolved Profile, then write a new ready revision.",
    )
    parser.add_argument(
        "--validation-case",
        type=Path,
        help="Evidence-backed ordinary smoke case used by --promote-runtime.",
    )
    parser.add_argument(
        "--reviewer",
        help="Human reviewer identifier for --review-profile.",
    )
    parser.add_argument(
        "--review-profile",
        action="append",
        type=Path,
        default=[],
        metavar="PROFILE",
        help="Record a separate human review as a new Profile revision.",
    )
    parser.add_argument(
        "--review-decision",
        choices=("approved", "needs_revision"),
        help="Decision recorded for --review-profile.",
    )
    parser.add_argument(
        "--review-issue",
        action="append",
        default=[],
        help="Existing validation issue ID retained by the reviewer; repeatable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        schema = load_json(args.schema)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FATAL] Cannot load schema: {exc}", file=sys.stderr)
        return 2
    if args.validate_only:
        return 1 if validate_files(args.validate_only, schema) else 0
    try:
        runtime_config = load_json(args.runtime_config)
    except (OSError, json.JSONDecodeError, KeyError, BuildError) as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 2
    args.docker_image = (
        args.docker_image or runtime_config.get("images", {}).get("api_metadata_runtime")
    )
    if not args.docker_image:
        print("[FATAL] No Docker image is configured", file=sys.stderr)
        return 2
    if args.promote_runtime and args.review_profile:
        print("[FATAL] --promote-runtime and --review-profile are mutually exclusive", file=sys.stderr)
        return 2
    if args.validation_case is not None and len(args.promote_runtime) != 1:
        print(
            "[FATAL] --validation-case requires exactly one --promote-runtime",
            file=sys.stderr,
        )
        return 2
    if args.promote_runtime:
        if args.api or args.api_file:
            print("[FATAL] --promote-runtime cannot be combined with --api/--api-file", file=sys.stderr)
            return 2
        outcomes: list[Outcome] = []
        for profile_path in args.promote_runtime:
            print(f"[PROMOTE] {profile_path}")
            try:
                outcome = promote_runtime_profile(
                    profile_path, args, runtime_config, schema
                )
                print(
                    f"[{outcome.status.upper()}] {outcome.api}: "
                    f"{len(outcome.paths)} profile(s)"
                )
            except (BuildError, KeyError, OSError, json.JSONDecodeError) as exc:
                outcome = Outcome(
                    api=profile_path.as_posix(),
                    status="failed",
                    message=str(exc),
                )
                print(f"[FAILED] {profile_path}: {exc}", file=sys.stderr)
            outcomes.append(outcome)
        counts: dict[str, int] = {}
        for outcome in outcomes:
            counts[outcome.status] = counts.get(outcome.status, 0) + 1
        print("[SUMMARY] " + json.dumps(counts, sort_keys=True))
        return 1 if counts.get("failed") else 0
    if args.review_profile:
        if args.api or args.api_file:
            print("[FATAL] --review-profile cannot be combined with --api/--api-file", file=sys.stderr)
            return 2
        if not args.reviewer or not args.reviewer.strip() or not args.review_decision:
            print(
                "[FATAL] --review-profile requires --reviewer and --review-decision",
                file=sys.stderr,
            )
            return 2
        outcomes = []
        for profile_path in args.review_profile:
            print(f"[REVIEW] {profile_path}")
            try:
                outcome = review_profile(profile_path, args, runtime_config, schema)
                print(
                    f"[{outcome.status.upper()}] {outcome.api}: "
                    f"{len(outcome.paths)} profile(s)"
                )
            except (BuildError, KeyError, OSError, json.JSONDecodeError) as exc:
                outcome = Outcome(
                    api=profile_path.as_posix(), status="failed", message=str(exc)
                )
                print(f"[FAILED] {profile_path}: {exc}", file=sys.stderr)
            outcomes.append(outcome)
        counts = {}
        for outcome in outcomes:
            counts[outcome.status] = counts.get(outcome.status, 0) + 1
        print("[SUMMARY] " + json.dumps(counts, sort_keys=True))
        return 1 if counts.get("failed") else 0
    try:
        apis = collect_apis(args.api, args.api_file)
    except (OSError, KeyError, BuildError) as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 2

    outcomes: list[Outcome] = []
    for raw_api in apis:
        print(f"[BUILD] {raw_api}")
        try:
            api = normalize_api(raw_api)
            outcome = build_api(api, args, runtime_config, schema)
            print(f"[{outcome.status.upper()}] {api}: {len(outcome.paths)} profile(s)")
        except (BuildError, KeyError, OSError, json.JSONDecodeError) as exc:
            outcome = Outcome(api=raw_api, status="failed", message=str(exc))
            print(f"[FAILED] {raw_api}: {exc}", file=sys.stderr)
            outcomes.append(outcome)
            if args.fail_fast:
                break
            continue
        outcomes.append(outcome)

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    summary = {
        "builder_version": BUILDER_VERSION,
        "generated_at": utc_now(),
        "dry_run": args.dry_run,
        "counts": counts,
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }
    print("[SUMMARY] " + json.dumps(counts, sort_keys=True))
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[SUMMARY_FILE] {args.summary_json}")
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
