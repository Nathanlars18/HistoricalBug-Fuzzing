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


BUILDER_VERSION = "api_profile_builder_v0.3"
SCHEMA_VERSION = "1.0"
DEFAULT_RUNTIME_CONFIG = Path("runtime/flashfuzz_2_10/runtime_config.json")
DEFAULT_SCHEMA = Path(
    "experiment/EXP011_bug_aware_harness_synthesis/"
    "schemas/api_profile_record.schema.json"
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
            signature = str(inspect.signature(obj))
        except Exception:
            signature = None
        try:
            docstring = inspect.getdoc(obj)
        except Exception:
            docstring = None
        return {
            "resolved": True,
            "signature": signature,
            "docstring": docstring,
            "torch_version": getattr(torch, "__version__", None),
            "torch_git_version": getattr(getattr(torch, "version", None), "git_version", None),
            "torch_package_root": str(Path(torch.__file__).resolve().parent),
            "error": None,
        }
    except Exception as exc:
        return {
            "resolved": False,
            "signature": None,
            "docstring": None,
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


def cpp_runtime_probe_source(profile: dict[str, Any]) -> str:
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
        schema_type = str(parameter["schema_type"])
        if "Tensor" not in schema_type:
            raise BuildError(
                "Runtime promotion v1 supports required Tensor parameters only; "
                f"unsupported {parameter['name']}: {schema_type}"
            )
        variable = f"hbfg_arg_{index}"
        declarations.append(
            f"    auto {variable} = torch::ones({{2, 2}}, "
            "torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU));"
        )
        arguments.append(variable)

    if not arguments:
        raise BuildError("Runtime promotion requires at least one bound argument")
    body = "\n".join(declarations)
    return f"""#include <torch/torch.h>
#include <exception>
#include <iostream>

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
) -> tuple[str, str, str]:
    source = cpp_runtime_probe_source(profile)
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
        raise BuildError(
            "C++ API probe compilation failed: "
            + (result.stdout + result.stderr).strip()[-2000:]
        )
    if result.returncode != 0 or run_status != 0:
        raise BuildError(
            "C++ API probe execution failed: "
            + (result.stdout + result.stderr).strip()[-2000:]
        )
    if "HBFG_TARGET_REACHED" not in result.stdout:
        raise BuildError("C++ API probe did not emit target-reached evidence")
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

    collected_at = utc_now()
    source, log, image_id = run_cpp_runtime_probe(
        args.docker_image,
        source_profile,
        args.probe_timeout,
    )
    run_id = collected_at.replace("-", "").replace(":", "").replace(".", "")
    log_path = (
        args.output_root
        / "_runs"
        / f"api_profile_runtime_validation__{safe_component(run_id)}"
        / f"{safe_component(source_profile['target']['python_api'])}.log"
    )
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
            check["evidence_refs"] = [update[0]]
    if profile["validation"]["issues"]:
        raise BuildError("Runtime promotion cannot approve a Profile with issues")
    profile["validation"]["validation_status"] = "passed"
    profile["validation"]["execution_readiness"] = "ready"
    profile["review"] = {
        "review_status": "approved",
        "reviewer": args.reviewer,
        "reviewed_at": collected_at,
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
    lowered = type_text.lower()
    tests = [
        ("tensor[]", "tensor_sequence"), ("list[tensor", "tensor_sequence"),
        ("tensor", "tensor"), ("symint", "integer"), ("int", "integer"),
        ("float", "floating"), ("double", "floating"), ("scalar", "scalar"),
        ("bool", "boolean"), ("str", "string"), ("dtype", "dtype"),
        ("scalartype", "dtype"), ("device", "device"), ("layout", "layout"),
        ("memoryformat", "memory_format"), ("generator", "generator"),
    ]
    found: list[str] = []
    for token, value in tests:
        if token in lowered and value not in found:
            found.append(value)
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


def select_signature(probe: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    runtime_signature = probe["runtime"].get("signature")
    declarations = probe["pyi"].get("signatures", [])
    if runtime_signature:
        return runtime_signature, declarations
    texts = [item["declaration"] for item in declarations]
    return (" | ".join(texts) if texts else None), declarations


def build_python_parameters(
    signatures: list[dict[str, Any]],
    native: list[dict[str, Any]],
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    source = signatures[0]["parameters"] if len(signatures) == 1 else []
    if not source:
        source = [
            {
                "name": item["name"],
                "kind": "keyword_only" if item["keyword_only"] else "positional_or_keyword",
                "annotation": item["schema_type"],
                "default": item["default"],
            }
            for item in native
        ]
    records = []
    for ordinal, item in enumerate(source):
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
    signatures: list[dict[str, Any]],
    native_returns: list[str],
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    source = native_returns
    if not source and len(signatures) == 1 and signatures[0].get("return_annotation"):
        source = [signatures[0]["return_annotation"]]
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


def build_argument_mapping(
    python_parameters: list[dict[str, Any]],
    binding_parameters: list[dict[str, Any]],
    evidence_refs: list[str],
) -> tuple[list[dict[str, Any]], bool]:
    by_name = {item["name"]: item for item in python_parameters}
    unused = list(python_parameters)
    records: list[dict[str, Any]] = []
    complete = True
    for item in binding_parameters:
        source = by_name.get(item["name"])
        kind = "direct"
        if source is None and unused:
            source, kind = unused[0], "renamed"
        if source is not None:
            unused = [candidate for candidate in unused if candidate is not source]
            source_ref = source["parameter_id"]
        elif item["default"] is not None:
            source_ref, kind = None, "default_injected"
        else:
            source_ref, kind, complete = None, "unresolved", False
        records.append({
            "python_parameter_ref": source_ref,
            "binding_parameter_ref": item["binding_parameter_id"],
            "mapping_kind": kind,
            "transformation": None,
            "evidence_refs": evidence_refs,
        })
    return records, complete


def build_validation(
    runtime_resolved: bool,
    runtime_doc_available: bool,
    runtime_version_mismatch: bool,
    signature_count: int,
    schema_resolved: bool,
    mapping_complete: bool,
    cpp_resolved: bool,
    refs: dict[str, str],
) -> dict[str, Any]:
    def check(check_id: str, kind: str, passed: bool, yes: str, no: str, proof: list[str]):
        return {
            "check_id": check_id,
            "check_kind": kind,
            "backend": "cpu",
            "status": "passed" if passed else "blocked",
            "summary": yes if passed else no,
            "evidence_refs": proof,
        }

    checks = [
        check("check_python_resolution", "python_resolution", runtime_resolved,
              "Python API resolved in the pinned runtime.",
              "Python API is unavailable in the selected runtime image.",
              [refs["doc"]] if refs.get("doc") else []),
        check("check_signature_resolution", "signature_resolution", signature_count == 1,
              "One Python signature was resolved.",
              f"Resolved {signature_count} Python signature declarations.",
              [refs["signature"]] if refs.get("signature") else []),
        check("check_operator_schema_resolution", "operator_schema_resolution", schema_resolved,
              "One target operator schema was selected.",
              "No target operator schema was resolved.",
              [refs["schema"]] if refs.get("schema") else []),
        check("check_argument_mapping", "argument_mapping", mapping_complete,
              "Python-to-binding argument mapping is complete.",
              "Python-to-binding argument mapping is incomplete.",
              [refs[key] for key in ("signature", "schema") if refs.get(key)]),
        check("check_cpp_binding_resolution", "cpp_binding_resolution", cpp_resolved,
              "A C++/ATen callable candidate was resolved.",
              "No C++/ATen callable candidate was resolved.",
              [refs["schema"]] if refs.get("schema") else []),
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
            "status": "not_run",
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
    if signature_count != 1:
        issues.append({
            "issue_id": "issue_signature_ambiguity",
            "issue_kind": "signature_ambiguity",
            "blocking": signature_count == 0,
            "description": f"Expected one Python signature declaration; found {signature_count}.",
            "affected_refs": ["python_contract"],
            "evidence_refs": [refs["signature"]] if refs.get("signature") else [],
        })
    if not schema_resolved:
        issues.append({
            "issue_id": "issue_binding_unresolved",
            "issue_kind": "binding_unresolved",
            "blocking": True,
            "description": "No exact target-version operator schema was resolved.",
            "affected_refs": ["target_binding"],
            "evidence_refs": [],
        })
    if schema_resolved and not mapping_complete:
        issues.append({
            "issue_id": "issue_argument_mapping_unresolved",
            "issue_kind": "argument_mapping_unresolved",
            "blocking": True,
            "description": "A required binding argument lacks a Python mapping.",
            "affected_refs": ["target_binding"],
            "evidence_refs": [refs["schema"]],
        })
    blocking = any(item["blocking"] for item in issues)
    readiness = "blocked" if blocking else "unassessed"
    return {
        "validation_status": "failed" if blocking else "partial",
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

    signature, signatures = select_signature(probe)
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
    if probe["pyi"].get("content_hash"):
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
    contract_refs = [refs[key] for key in ("doc", "signature", "schema") if refs.get(key)]
    parameters = build_python_parameters(signatures, native_parameters, contract_refs)
    returns = build_returns(signatures, native_returns, contract_refs)
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
    mapping, mapping_complete = build_argument_mapping(
        parameters,
        binding_parameters,
        [refs[key] for key in ("signature", "schema") if refs.get(key)],
    )

    if operator:
        operator_name = operator["operator_name"]
        overload = operator["operator_overload"]
        cpp_callable = (
            f"at::{operator_name.split('::', 1)[-1]}"
            if "function" in operator.get("variants", []) else None
        )
        binding_status = "resolved" if cpp_callable and mapping_complete else "partial"
        binding_token = f"{operator_name.replace('::', '.')}.{overload}"
    else:
        operator_name = overload = cpp_callable = None
        binding_status, binding_token = "unresolved", "unresolved"

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
                "available" if docstring and signature
                else "partial" if docstring or signature
                else "missing"
            ),
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
            "status": binding_status,
            "operator_name": operator_name,
            "operator_overload": overload,
            "operator_schema": operator["operator_schema"] if operator else None,
            "cpp_callable": cpp_callable,
            "binding_parameters": binding_parameters,
            "argument_mapping": mapping,
            "return_mapping": return_mapping,
            "evidence_refs": [refs["schema"]] if refs.get("schema") else [],
        },
        "documented_constraints": [],
        "flashfuzz_support": ff_support,
        "validation": build_validation(
            runtime_verified,
            bool(docstring),
            runtime_mismatch,
            len(signatures) or (1 if runtime_verified and runtime.get("signature") else 0),
            operator is not None,
            mapping_complete,
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
    for item in binding["return_mapping"]:
        if item["python_return_ref"] is not None and item["python_return_ref"] not in return_ids:
            raise BuildError("return_mapping contains an unknown Python return reference")
    unknown_review_issues = set(profile["review"]["issue_refs"]) - set(id_groups["validation issue"])
    if unknown_review_issues:
        raise BuildError(f"review.issue_refs contains unknown IDs: {sorted(unknown_review_issues)}")

    parent = profile["metadata"]["parent_revision_ref"]
    if profile["revision"] > 1:
        if parent is None:
            raise BuildError("Revision greater than 1 requires parent_revision_ref")
        if parent["profile_id"] != profile["profile_id"] or parent["revision"] >= profile["revision"]:
            raise BuildError("parent_revision_ref does not identify an earlier revision of this profile")
    if binding["status"] == "resolved" and not (
        binding["operator_schema"] and binding["cpp_callable"]
    ):
        raise BuildError("Resolved binding requires operator_schema and cpp_callable")


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
) -> tuple[str, Path]:
    api = profile["target"]["python_api"]
    binding = profile["target_binding"]
    token = (
        f"{binding['operator_name'].replace('::', '.')}.{binding['operator_overload']}"
        if binding["operator_name"] else "unresolved"
    )
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
        if semantic_payload(latest) == semantic_payload(profile):
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
    candidates = probe["native_yaml"].get("operators", []) or [None]
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
        "--reviewer",
        help="Human reviewer recorded for --promote-runtime.",
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
    if args.promote_runtime:
        if args.api or args.api_file:
            print("[FATAL] --promote-runtime cannot be combined with --api/--api-file", file=sys.stderr)
            return 2
        if not args.reviewer or not args.reviewer.strip():
            print("[FATAL] --promote-runtime requires --reviewer", file=sys.stderr)
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
