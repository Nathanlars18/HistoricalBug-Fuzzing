# Historical Bug Source Data

This directory is the workspace for immutable historical source captures,
candidate inventories, and source-selection provenance.

`issue_source_protocol.md` defines upstream-source admission, case identity,
API attribution, and provenance before Report construction.

- `raw/` contains dataset records, upstream Issue captures, comments, linked
  fix material, and source-provided reproduction code.
- `manifests/` contains candidate inventories produced by the deterministic
  collector. Inventory entries are discovery and screening records, not Bug
  Reports.
- `scripts/collect_issue_sources.py` is the only active inventory producer and
  validator. It uses GitHub JSON APIs for collection and never calls an LLM.
- `interim/` contains legacy selection material only; it is not an active
  source of Report facts.

On 2026-09-28, previous curated sources and their EXP006 generated records were
moved to `legacy/pre_report_v3_20260928/`, with original paths and byte hashes
preserved. See its README and archive manifest before using historical results.
These archived files are not inputs for the active Report v5 pipeline. New
native GitHub captures and frozen dataset provenance are kept separately in the
historically named `raw/report_v3_calibration/` directory; the directory name
does not determine the active Report schema version.

Canonical processed bug reports, bug patterns, and knowledge-base items are not
stored in `dataset/`. The formal processed Historical Bug Information Database
is located at:

`experiment/EXP006_historical_bug_pattern_dataset/`
