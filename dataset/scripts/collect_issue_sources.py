#!/usr/bin/env python3
"""Build and validate an auditable Issue candidate inventory without an LLM."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


INVENTORY_VERSION = "1.0"
PROTOCOL_VERSION = "0.8"
DEFAULT_REPOSITORY = "pytorch/pytorch"
ADMISSION_STATUSES = {"pending", "admitted", "excluded", "deferred"}
REASON_CODES = {
    "outside_time_window", "duplicate", "no_affected_api_evidence",
    "no_trigger_or_operation_context", "no_erroneous_behavior", "expected_behavior",
    "non_runtime_request", "upstream_unavailable", "ambiguous",
}
RELATIONS = {"affected", "mentioned"}
LOCATOR_KINDS = {"json_pointer", "json_string_line_range"}


class InventoryError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def canonical_issue_url(repository: str, issue_number: int) -> str:
    return f"https://github.com/{repository}/issues/{issue_number}"


def candidate_id(repository: str, issue_number: int) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", repository.lower()).strip("_")
    return f"ic_{stem}_{issue_number}"


def new_inventory(repository: str, created_from: str, created_to: str) -> dict[str, Any]:
    now = utc_now()
    scope_key = f"{repository}:{created_from}:{created_to}"
    return {
        "inventory_version": INVENTORY_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "inventory_id": "inventory_" + hashlib.sha256(scope_key.encode()).hexdigest()[:16],
        "created_at": now,
        "updated_at": now,
        "collection_scope": {
            "repository": repository,
            "created_from": created_from,
            "created_to": created_to,
            "dataset_sources": [],
            "github_queries": [],
        },
        "candidates": [],
    }


def _nonempty(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InventoryError(f"{location} must be a non-empty string")
    return value


def validate_locator(locator: Any, location: str) -> None:
    if not isinstance(locator, dict):
        raise InventoryError(f"{location} must be an object")
    if locator.get("locator_type") not in LOCATOR_KINDS:
        raise InventoryError(f"{location}.locator_type is unsupported")
    _nonempty(locator.get("artifact_path"), f"{location}.artifact_path")
    value = _nonempty(locator.get("value"), f"{location}.value")
    if not value.startswith("/"):
        raise InventoryError(f"{location}.value must be a JSON pointer")
    if locator["locator_type"] == "json_string_line_range":
        start, end = locator.get("start_line"), locator.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            raise InventoryError(f"{location} has an invalid line range")


def validate_inventory(value: Any, base_dir: Path | None = None) -> None:
    if not isinstance(value, dict):
        raise InventoryError("inventory root must be an object")
    if value.get("inventory_version") != INVENTORY_VERSION:
        raise InventoryError(f"inventory_version must be {INVENTORY_VERSION}")
    if value.get("protocol_version") != PROTOCOL_VERSION:
        raise InventoryError(f"protocol_version must be {PROTOCOL_VERSION}")
    _nonempty(value.get("inventory_id"), "inventory_id")
    scope = value.get("collection_scope")
    if not isinstance(scope, dict):
        raise InventoryError("collection_scope must be an object")
    repository = _nonempty(scope.get("repository"), "collection_scope.repository")
    for key in ("created_from", "created_to"):
        _nonempty(scope.get(key), f"collection_scope.{key}")
    if not isinstance(scope.get("dataset_sources"), list) or not isinstance(scope.get("github_queries"), list):
        raise InventoryError("collection_scope source/query fields must be arrays")
    candidates = value.get("candidates")
    if not isinstance(candidates, list):
        raise InventoryError("candidates must be an array")
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for index, item in enumerate(candidates):
        loc = f"candidates[{index}]"
        if not isinstance(item, dict):
            raise InventoryError(f"{loc} must be an object")
        cid = _nonempty(item.get("candidate_id"), f"{loc}.candidate_id")
        if cid in seen_ids:
            raise InventoryError(f"duplicate candidate_id: {cid}")
        seen_ids.add(cid)
        if item.get("source_kind") not in {"external_dataset", "github_search", "both"}:
            raise InventoryError(f"{loc}.source_kind is invalid")
        if item.get("repository") != repository:
            raise InventoryError(f"{loc}.repository is outside collection_scope")
        number = item.get("issue_number")
        if not isinstance(number, int) or number < 1:
            raise InventoryError(f"{loc}.issue_number must be positive")
        expected_url = canonical_issue_url(repository, number)
        if item.get("canonical_url") != expected_url:
            raise InventoryError(f"{loc}.canonical_url is not canonical")
        if expected_url in seen_urls:
            raise InventoryError(f"duplicate upstream Issue: {expected_url}")
        seen_urls.add(expected_url)
        for key in ("discovered_by", "matched_api_terms", "native_labels"):
            if not isinstance(item.get(key), list):
                raise InventoryError(f"{loc}.{key} must be an array")
        screening = item.get("screening")
        if not isinstance(screening, dict) or screening.get("status") not in ADMISSION_STATUSES:
            raise InventoryError(f"{loc}.screening.status is invalid")
        reasons = screening.get("reason_codes")
        if not isinstance(reasons, list) or any(code not in REASON_CODES for code in reasons):
            raise InventoryError(f"{loc}.screening.reason_codes is invalid")
        associations = screening.get("api_associations", [])
        if not isinstance(associations, list):
            raise InventoryError(f"{loc}.screening.api_associations must be an array")
        for offset, association in enumerate(associations):
            aloc = f"{loc}.screening.api_associations[{offset}]"
            _nonempty(association.get("api_name"), f"{aloc}.api_name")
            if association.get("relation") not in RELATIONS:
                raise InventoryError(f"{aloc}.relation is invalid")
            validate_locator(association.get("source_locator"), f"{aloc}.source_locator")
        gates = screening.get("admission_gate_locators", {})
        if not isinstance(gates, dict):
            raise InventoryError(f"{loc}.screening.admission_gate_locators must be an object")
        allowed_gates = {"trigger_conditions", "operation_contexts", "erroneous_behavior"}
        if set(gates) != allowed_gates:
            raise InventoryError(
                f"{loc}.screening.admission_gate_locators must contain exactly "
                f"{sorted(allowed_gates)}"
            )
        for gate in sorted(allowed_gates):
            entries = gates.get(gate, [])
            if not isinstance(entries, list):
                raise InventoryError(f"{loc}.screening.admission_gate_locators.{gate} must be an array")
            for offset, locator in enumerate(entries):
                validate_locator(locator, f"{loc}.screening.admission_gate_locators.{gate}[{offset}]")
        if screening["status"] == "admitted":
            if not any(a.get("relation") == "affected" for a in associations):
                raise InventoryError(f"{loc}: admitted candidate needs an affected API")
            has_context = bool(gates.get("trigger_conditions") or gates.get("operation_contexts"))
            if not has_context or not gates.get("erroneous_behavior"):
                raise InventoryError(
                    f"{loc}: admitted candidate needs trigger/operation context and erroneous behavior"
                )
        snapshot = item.get("snapshot")
        if snapshot is not None:
            if not isinstance(snapshot, dict):
                raise InventoryError(f"{loc}.snapshot must be null or an object")
            path_text = _nonempty(snapshot.get("capture_path"), f"{loc}.snapshot.capture_path")
            _nonempty(snapshot.get("content_hash"), f"{loc}.snapshot.content_hash")
            if base_dir is not None:
                path = Path(path_text)
                if not path.is_absolute():
                    path = base_dir / path
                if not path.is_file():
                    raise InventoryError(f"{loc}.snapshot file is missing: {path}")


def load_or_create(path: Path, repository: str, created_from: str, created_to: str) -> dict[str, Any]:
    if path.exists():
        value = read_json(path)
        validate_inventory(value)
        return value
    return new_inventory(repository, created_from, created_to)


def merge_candidate(inventory: dict[str, Any], issue: dict[str, Any], discovery: dict[str, Any], api_terms: Iterable[str]) -> None:
    repository = inventory["collection_scope"]["repository"]
    number = int(issue["number"])
    url = canonical_issue_url(repository, number)
    item = next((row for row in inventory["candidates"] if row["canonical_url"] == url), None)
    if item is None:
        labels = [label.get("name", "") for label in issue.get("labels", []) if isinstance(label, dict)]
        item = {
            "candidate_id": candidate_id(repository, number), "source_kind": discovery["kind"],
            "repository": repository, "issue_number": number, "canonical_url": url,
            "created_at": issue.get("created_at"), "updated_at": issue.get("updated_at"),
            "closed_at": issue.get("closed_at"), "native_labels": sorted(set(labels)),
            "discovered_by": [], "matched_api_terms": [], "snapshot": None,
            "duplicate_of": None,
            "screening": {"status": "pending", "reason_codes": [], "reviewed_by": None,
                          "reviewed_at": None, "api_associations": [],
                          "admission_gate_locators": {
                              "trigger_conditions": [], "operation_contexts": [],
                              "erroneous_behavior": []}},
        }
        inventory["candidates"].append(item)
    elif item["source_kind"] != discovery["kind"]:
        item["source_kind"] = "both"
    if discovery not in item["discovered_by"]:
        item["discovered_by"].append(discovery)
    item["matched_api_terms"] = sorted(set(item["matched_api_terms"]) | {x for x in api_terms if x})
    inventory["candidates"].sort(key=lambda row: row["issue_number"])
    inventory["updated_at"] = utc_now()


def github_json(url: str, token: str | None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "HistoricalBug-Fuzzing-collector/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=60) as response:
            return json.load(response)
    except (HTTPError, URLError) as exc:
        raise InventoryError(f"GitHub request failed for {url}: {exc}") from exc


def command_import_csv(args: argparse.Namespace) -> None:
    inventory = load_or_create(args.inventory, args.repository, args.created_from, args.created_to)
    source = {"source_name": args.source_name, "source_ref": args.source_ref,
              "local_path": str(args.csv), "content_hash": sha256_file(args.csv)}
    if source not in inventory["collection_scope"]["dataset_sources"]:
        inventory["collection_scope"]["dataset_sources"].append(source)
    with args.csv.open(newline="", encoding="utf-8-sig") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            raw_url = (row.get(args.url_column) or "").strip()
            match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/issues/(\d+)/?", raw_url)
            if not match or match.group(1).lower() != args.repository.lower():
                continue
            issue = {"number": int(match.group(2)), "labels": [], "created_at": None,
                     "updated_at": None, "closed_at": None}
            discovery = {"kind": "external_dataset", "source_name": args.source_name,
                         "record_id": str(line_number), "source_ref": args.source_ref}
            terms = [(row.get(args.api_column) or "").strip()] if args.api_column else []
            merge_candidate(inventory, issue, discovery, terms)
    validate_inventory(inventory)
    atomic_write(args.inventory, inventory)


def command_search(args: argparse.Namespace) -> None:
    inventory = load_or_create(args.inventory, args.repository, args.created_from, args.created_to)
    for term in args.api_term:
        query = f'repo:{args.repository} is:issue created:{args.created_from}..{args.created_to} "{term}"'
        items: list[dict[str, Any]] = []
        total_count = 0
        page = 1
        while len(items) < args.limit:
            per_page = min(args.limit - len(items), 100)
            endpoint = f"https://api.github.com/search/issues?q={quote(query)}&per_page={per_page}&page={page}"
            payload = github_json(endpoint, os.environ.get("GITHUB_TOKEN"))
            total_count = int(payload.get("total_count", 0))
            batch = payload.get("items", [])
            items.extend(batch)
            if len(batch) < per_page or len(items) >= total_count:
                break
            page += 1
        inventory["collection_scope"]["github_queries"].append({
            "api_term": term, "query": query, "result_limit": args.limit,
            "searched_at": utc_now(), "reported_total_count": total_count,
            "captured_result_count": len(items), "exhausted": len(items) >= total_count,
        })
        for issue in items[: args.limit]:
            merge_candidate(inventory, issue, {"kind": "github_search", "query": query}, [term])
    validate_inventory(inventory)
    atomic_write(args.inventory, inventory)


def command_capture(args: argparse.Namespace) -> None:
    inventory = read_json(args.inventory)
    validate_inventory(inventory)
    selected = [item for item in inventory["candidates"] if not args.candidate_id or item["candidate_id"] in args.candidate_id]
    if not selected:
        raise InventoryError("no candidates selected")
    token = os.environ.get("GITHUB_TOKEN")
    for item in selected:
        repository, number = item["repository"], item["issue_number"]
        issue = github_json(f"https://api.github.com/repos/{repository}/issues/{number}", token)
        comments: list[Any] = []
        page = 1
        while True:
            batch = github_json(f"https://api.github.com/repos/{repository}/issues/{number}/comments?per_page=100&page={page}", token)
            comments.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        directory = args.output_root / f"issue_{number}"
        issue_path, comments_path = directory / "issue.json", directory / "comments.json"
        atomic_write(issue_path, issue)
        atomic_write(comments_path, comments)
        capture = {"issue_path": str(issue_path), "comments_paths": [str(comments_path)],
                   "comments_complete": True, "captured_at": utc_now(), "companions": []}
        capture_path = directory / "capture.json"
        atomic_write(capture_path, capture)
        item.update({"created_at": issue.get("created_at"), "updated_at": issue.get("updated_at"),
                     "closed_at": issue.get("closed_at"),
                     "native_labels": sorted({label.get("name", "") for label in issue.get("labels", []) if label.get("name")}),
                     "snapshot": {"capture_path": str(capture_path), "content_hash": sha256_file(capture_path),
                                  "captured_at": capture["captured_at"]}})
    inventory["updated_at"] = utc_now()
    validate_inventory(inventory)
    atomic_write(args.inventory, inventory)


def command_validate(args: argparse.Namespace) -> None:
    value = read_json(args.inventory)
    validate_inventory(value, args.base_dir)
    print(json.dumps({"status": "valid", "candidate_count": len(value["candidates"]),
                      "inventory_id": value["inventory_id"]}))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--inventory", type=Path, required=True)
    common.add_argument("--repository", default=DEFAULT_REPOSITORY)
    common.add_argument("--created-from", required=True)
    common.add_argument("--created-to", required=True)
    importer = commands.add_parser("import-dataset", parents=[common])
    importer.add_argument("--csv", type=Path, required=True)
    importer.add_argument("--source-name", required=True)
    importer.add_argument("--source-ref", required=True)
    importer.add_argument("--url-column", required=True)
    importer.add_argument("--api-column")
    search = commands.add_parser("search-github", parents=[common])
    search.add_argument("--api-term", action="append", required=True)
    search.add_argument("--limit", type=int, default=100)
    capture = commands.add_parser("capture")
    capture.add_argument("--inventory", type=Path, required=True)
    capture.add_argument("--candidate-id", action="append")
    capture.add_argument("--output-root", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--inventory", type=Path, required=True)
    validate.add_argument("--base-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    actions = {"import-dataset": command_import_csv, "search-github": command_search,
               "capture": command_capture, "validate": command_validate}
    actions[args.command](args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InventoryError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        raise SystemExit(1)
