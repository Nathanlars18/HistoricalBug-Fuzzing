# Pattern Review Protocol v1.0

## Purpose

Automatic validation proves only structural and referential consistency. This review checks the semantic decisions introduced when a Report is abstracted into a Pattern.

## Scope

- Review every Pattern selected for an experiment.
- For larger exploratory collections, review a predeclared stratified sample covering source dataset, target API, root-cause category, symptom category, and nullable classifications.
- Select the sample before inspecting model quality results; record the sampling rule with the study artifacts.

## Checks

For each reviewed Pattern, compare it with the bound Report revision and cited Evidence IDs:

1. `target_api` is explicitly `affected`, not merely mentioned.
2. Historical conditions are supported, do not overstate necessity, and contain only historical setup or state rather than implementation causes, fixes, or corrected expectations.
3. `defect_mechanism` is null when the source does not support a cause.
4. A mechanism supported for one implementation file, backend, device path, or execution path has not been generalized to another without direct evidence.
5. Any root-cause category matches the supported mechanism, not a trigger keyword.
6. The failure description and optional symptom category match the historical manifestation.
7. Historical observations are factual, exclude incidental logs and project-management metadata, and are not rewritten as future testing oracles.
8. Conditions, mechanism, failure description, and observations do not substantially duplicate the same semantic fact across fields.
9. No Harness, mutation, Strategy, or feedback decision has entered the Pattern.

## Outcomes

- `approved`: all checks pass; the Pattern may be used downstream.
- `needs_revision`: evidence is sufficient but the Pattern representation must be corrected and regenerated or revised with provenance.
- `rejected`: the Report/API projection cannot support a usable Pattern.

Keep the review outcome, Pattern ID and hash, reviewer identifier, review time, and concise reason in the experiment's review ledger. Do not edit an existing Pattern silently; issue a new Pattern revision or regenerate it from the same immutable Report input.
