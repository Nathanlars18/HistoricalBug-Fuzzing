# Issue Source Selection and Provenance Protocol (Draft v0.8)

## Scope

This protocol governs selection, identity, and preservation of historical
PyTorch bug sources before Report construction. It does not extract Report
claims, assign Pattern or Knowledge labels, or assert that an old bug persists
in the current test build. EXP006's `source_to_report_mapping.md` governs the
subsequent conversion of admitted source bundles into Reports.

Issue discovery, capture, identity, deduplication, and admission are
deterministic operations. This layer must not use an LLM to infer an affected
API, a trigger, a failure, a diagnosis, or a fix. Missing or ambiguous facts
remain unresolved for later review; they are not completed from plausibility.

The initial frozen candidate sources are the Harzevili et al. API-level
DL-fuzzer benchmark and BugsInDLLs. They are discovery sources, not assumed to
be complete or already admissible case sets. A case from another dataset,
including Chen et al., must pass the same checks. Dataset annotations are
discovery aids and remain attributed to their authors; they are not
substituted for upstream evidence.

Dataset sources: [Benchmarking-DL-Fuzzers](https://github.com/dmc1778/Benchmarking-DL-Fuzzers),
[BugsInDLLs](https://github.com/ncsu-swat/bugsindlls), and optional
[DLFrameworkBugsData](https://github.com/DLFrameworkBug/DLFrameworkBugsData).

## Units and Admission

- A **source record** is one row or bug entry in a named dataset, or one
  GitHub discovery entry. Keep its discovery identity even if
  another source contains the same historical bug.
- A **case** is one distinct reported historical defect candidate supported by
  upstream Issue and/or linked fix evidence. A case can have several source
  records; candidate status does not imply that the report is a confirmed bug.
- An **API association** links a case to an API with cited evidence. A case can
  have multiple supported API associations without becoming multiple bugs.
- A **contextual API mention** records an API used for preparation,
  comparison, or an oracle without asserting that the API is affected.

Apply these gates in order. The three required facts in Gate 2 need not be
present in the dataset row itself; they must be supported by captured upstream
material. Apply the same gates to dataset and supplemental discoveries:

1. **Candidate:** the source entry resolves to a PyTorch upstream Issue, or
   to a PR/commit with an explicit, inspectable relation to a bug report. An
   annotation alone is insufficient.
2. **Historical-case admissible:** captured upstream material supports an
   affected API, a triggering operation, input, or environment context, and
   an observed erroneous behavior. Exact parameter boundaries, a verified
   root cause, and reproduction code are not mandatory. Do not infer missing
   facts from dataset labels. Documentation, installation/build-only, and
   feature requests are outside the historical API-bug case pool. Expected
   rejection of unsupported or invalid inputs alone is not a bug case;
   reported internal crashes or assertions during rejection may remain
   historical candidates, with the input-validity question recorded.
3. **Current-experiment eligible:** the target API and the relevant input
   behavior can be represented by the selected PyTorch build, CPU environment,
   and available Harness capabilities. This is a separate feasibility decision;
   failure here does not erase an otherwise valid historical case.

For the small-scale experiment, select an API only if it has at least two
distinct, evidence-supported, current-experiment-eligible cases after
deduplication. This is an API-cohort rule, not a gate for retaining an
individual historical case. Freeze the cohort before observing fuzzing results;
changing this threshold requires an explicit protocol revision before the
experiment. Eligibility means that the historical risk can be meaningfully
tested in the current environment, not that the old bug still exists in the
current build. A fixed historical bug may still provide
Knowledge; it must not be described as reproduced without runtime evidence.

Track the reported failure separately from its upstream disposition. `closed`
alone proves neither that the behavior was a bug nor that it was fixed: a case
may be closed as expected behavior, duplicate, or without a merged fix. Record
maintainer conclusions, conflicting comments, and whether a linked PR/commit
was actually merged. Call a behavior fixed in code only when an identified
merged change addresses it, supported by the patch, a regression test, or
explicit maintainer confirmation. Claim it is fixed in a specific release only
with release/tag evidence. Otherwise leave the confirmation or fix status
unresolved; do not promote a dataset label or closed Issue to a verified fix.
An explicit upstream conclusion that the behavior is expected or not a bug,
with no later evidence overturning that conclusion, excludes it from usable
bug Knowledge. Unresolved disagreements about whether a defect exists are
deferred rather than resolved by selecting only favorable comments. Lack of
an official confirmation alone is not grounds for exclusion.

## Case Identity and API Attribution

Normalize upstream URLs before exact-match deduplication. Multiple dataset
records pointing to the same Issue represent one case. A linked fix PR or
commit is supporting evidence, not automatically another case. Merge distinct
Issues only with an explicit upstream duplicate relationship or documented
human verification; leave uncertain matches separate and flagged for review.
Preserve every original record and merge rationale.

Associate an API only when the source supports that it is affected by the bug.
An API used merely for input preparation, comparison, or an oracle is a
contextual mention, not an affected API. More than one affected API may be
associated with one case, and Issue selection does not require choosing a
primary API among equally supported affected APIs. Preserve the source's API
spelling separately from the experiment target API. Name similarity, a shared
backend, membership in the same operator family, or a wrapper relationship
alone does not establish equivalence; uncertain associations remain unresolved
and do not enter Pattern extraction.

The current study does not transfer Knowledge from one API to a merely similar
API. A supported mapping across versions is limited to the same public API, an
evidenced canonical alias or rename, or an evidenced binding to the same API's
operator overload. Record the mapping as `exact_same`, `canonical_alias`,
`signature_changed`, `removed`, or `unresolved`. Only `exact_same` and
`canonical_alias` are eligible by default; other states require an explicit
feasibility decision. Count distinct cases, not dataset rows, API associations,
Reports, or Patterns, when reporting historical bug totals.

## Version and Source Preservation

Distinguish the reported version, any evidenced buggy/fixed versions, and the
experiment's target version. Unknown version or hardware information remains
unknown. GPU-only cases may remain in the source pool while being ineligible
for a CPU-only experiment. Historical presence, current feasibility, and
current reproduction are different claims.

For each admitted dataset source, retain the dataset name, frozen release or
commit, row/entry identifier, and original entry content. For GitHub
discoveries, retain the frozen search information and result identity.
For each admitted case, retain the canonical upstream URL and an immutable
capture of the Issue title, body, and full available comment thread, with
capture time, available upstream update time, and a hash of the captured
bytes. Record unavailable or partially captured material explicitly; do not
describe a partial capture as complete. Incomplete comments do not by
themselves reject a case if the available evidence supports admission and no
known unresolved contradiction remains. Capture cited PR/commit evidence with
its own identity and hash. Keep original text distinct from researcher
summaries, dataset-authored reproduction scripts, Report claims, and later
LLM outputs. Never silently rewrite a captured source; a new capture receives
new provenance.

## Time Window and Candidate Inventory

Before fixing the study window, build a deterministic candidate inventory from
the frozen datasets and upstream metadata. At minimum, inventory the upstream
Issue identity, dataset discovery identities, `created_at`, `updated_at`,
`closed_at`, native labels, dataset API annotations, and duplicate URLs. The
inventory describes candidates; it is not a semantic Report.

Freeze one continuous `created_at` interval for all APIs in a study cohort
before case screening and before observing fuzzing results. The interval dates
and rationale belong to a protocol revision. Dataset publication, repository
commit, capture, update, and close dates do not substitute for Issue
`created_at`. A later protocol may define a separately reported recent cohort,
but it must not silently merge a different time window into the original
cohort.

Apply the same interval to frozen-dataset candidates and GitHub discoveries.
An old Issue is not excluded solely because of age; compatibility with the
experiment target is decided separately under the version and feasibility
rules. Likewise, a recent Issue is not automatically eligible. The minimum
number of usable cases required to select an API is not a discovery stopping
rule.

## GitHub Discovery

Use the two frozen datasets as candidate inputs and cross-check them against
upstream evidence. For every API considered for a study cohort, search the
official PyTorch Issue tracker over the same frozen time window; do not search
only APIs that happen to have fewer dataset cases. Before each search, record
the target API, evidence-backed aliases, exact queries, time interval, result
order, and stopping rule such as a predefined result limit or exhaustion of
the queries. Retain the actual search date with that batch information.

Candidate discovery is not restricted to one search interface. Search API
names directly through GitHub or a search engine; datasets and third-party
discussions can also supply leads. Prefer the official
[PyTorch Issue tracker](https://github.com/pytorch/pytorch/issues) for upstream
evidence. Search the full API name and evidenced aliases separately. Do not
require `closed` state, a `bug` label, or an existing fix. A third-party mention
alone does not replace the upstream evidence required by the admission gates.

Inspect candidates in the declared order until the stopping rule is reached,
verify upstream evidence, and apply the same admission and deduplication rules
as for dataset discoveries. Do not stop at favorable fuzzing outcomes or
after reaching the minimum per-API case count, and do not silently alter search
limits to obtain desired cases. The discovery route is provenance, not a
different evidence standard.

Maintain one minimal candidate inventory for every discovered result. It is an
audit ledger, not a semantic Report and not a second copy of the Issue. The
active inventory format is defined in this protocol and checked by the sole
collector; it deliberately has no separate JSON Schema while only one producer
and consumer own it.

The inventory root contains `inventory_version`, `protocol_version`,
`inventory_id`, `created_at`, `updated_at`, `collection_scope`, and
`candidates`. `collection_scope` freezes the repository, Issue `created_at`
interval, dataset-source revisions, and exact GitHub queries. Each candidate
contains its identity, upstream URL, discovery records, timestamps, native
labels, matched API search terms, optional immutable snapshot reference,
duplicate relation, and screening decision. `matched_api_terms` means only that
a discovery expression matched; it is never an affected-API assertion.

Screening uses the statuses `pending`, `admitted`, `excluded`, and `deferred`.
Record controlled reason codes such as `outside_time_window`, `duplicate`,
`no_affected_api_evidence`, `no_trigger_or_operation_context`, `no_erroneous_behavior`,
`expected_behavior`, `non_runtime_request`, `upstream_unavailable`, or
`ambiguous`. An admitted entry also records the exact source locators used to
check the admission gates. Context locators are separated into
`trigger_conditions` and `operation_contexts`; at least one of those arrays
must be non-empty, and `erroneous_behavior` must be non-empty. This split
identifies the factual role of an exact excerpt without rewriting it or
classifying a Pattern. The entry also records every explicitly supported API
association as `affected` or `mentioned`. The Report Builder resolves these
locators and creates the canonical claims and Evidence IDs. The inventory must
not contain normalized prose, root-cause, resolution, Oracle, symptom, or
Pattern fields.

If another independent producer or consumer later needs this format, freeze a
versioned machine Schema before that integration rather than duplicating the
Report Contract now.

## Handoff to Report

Deliver an admitted case's immutable upstream captures, original dataset entries
or search provenance, and capture metadata to Report construction. Preserve the
relations between the Issue, comments, reproduction material, and cited fixes;
do not flatten them into an unattributed summary. Multiple discovery sources for
the same Issue remain provenance of one case, not separate Reports.

Deliver all evidence-supported affected API associations and contextual API
mentions without forcing a primary API. One admitted case normally produces
one Report even when several affected APIs are supported. Report v5 records
only `affected` and `mentioned`; Pattern extraction later operates separately
for each affected API and owns any API-specific `primary_api` designation.

The normal primary source is the upstream Issue snapshot. A PR/commit discovery
should resolve to its bug report; a PR-only report requires an explicitly
supported input profile before conversion. A fix commit alone is insufficient.

Historical-case admission is governed here. Report construction checks readable
inputs, evidence-backed assertions, identities, hashes, and references; it does
not reapply CPU feasibility or the per-API case-count threshold. Report review
checks mapping fidelity and is not automatically approved by dataset admission.
Experiment eligibility remains a later, separate decision.

## Audit and Research Claims

Keep the applicable protocol version, candidate manifest, batch search
information, source provenance, supported API associations, duplicate and
merge relations, and exclusion or deferral reasons. The manifest is the audit
record that the declared search and screening rules were applied; written
rules alone do not prove execution. A dedicated screening Schema is not
required unless later tooling needs one.

Only admitted source bundles enter Report construction, but excluded and
deferred manifest entries remain available for counts and method audit. Claim
exhaustive coverage only when every declared query was exhausted; a fixed
result limit supports only a bounded-search claim.

The Issue layer preserves sources and admission provenance, not extracted
trigger, oracle, or root-cause claims. Native GitHub JSON and dataset rows may
be retained as source formats; semantic structuring belongs to Report. Report
conversion must preserve their identities and capture limitations rather than
treating dataset annotations as upstream statements. Issue selection and
Report conversion do not use an LLM; Pattern extraction is the first layer
allowed to perform evidence-bounded semantic abstraction.

A case used to generate Knowledge may be evaluated for
historical-case activation or reproduction, but not counted as evidence of
generalization to an unseen bug. The active Inventory 1.0 structure and its
single collector are defined here; this does not imply that the full dataset
screening or experiment has already been completed.
