# Knowledge-to-HarnessSpec Synthesis Rules v1.1

## 1. Scope

These rules guide the LLM in converting one target-API input bundle into the
semantic portion of a HarnessSpec.

Inputs are:

- one API Profile;
- one Helper Capability Profile;
- one Candidate Manifest shortlist;
- compact synthesis views of shortlisted API-specific Knowledge records;
- the HarnessSpec synthesis contract.

The contract defines output shape, controlled vocabularies, and Builder-owned
fields. These rules define synthesis decisions only. Do not reproduce source
records, code, Helper calls, Strategy Primitives, hidden reasoning, or
Builder-owned fields.

## 2. Processing order

1. Assess each candidate's applicability to the target API.
2. Assess whether the supplied Helper Profile supports its semantic intent.
3. Select, defer, or reject every candidate.
4. Resolve material relationships among candidates.
5. Derive global validity constraints.
6. Construct exploration branches.
7. Define target properties and activation targets.
8. Define Oracle requirements.
9. Verify references and output only the contract response.

Do not select a candidate merely to ensure historical Knowledge is used. A valid
result may contain no selected Knowledge.

The Candidate Manifest has already bounded the prompt input. Do not make a
second prompt-length or execution-budget selection decision in this step.

## 3. Candidate decisions

Create exactly one decision for every candidate in the Candidate Manifest
shortlist.

Select a candidate only when all of the following hold:

- it is `applicable`, or its explicitly identified applicable subset is usable;
- the Helper Profile is `supported`, or its explicitly identified supported
  subset is sufficient;
- it contributes a distinct risk, target property, exploration goal, or Oracle;
- its contribution can form a valid branch alone or with compatible candidates;
- no exclusion, safety restriction, unresolved contradiction, or stronger
  duplicate contribution prevents its use.

Use `deferred` when the Knowledge could be useful but the current input cannot
justify a reliable branch decision: applicability is unknown, a potentially
resolvable Helper gap exists, the supported subset is unclear, or a material
interaction cannot yet be resolved.

Use `rejected` when the current target and revision have a definite reason not
to use the Knowledge: it is not applicable, matches an exclusion condition,
violates a safety restriction, cannot be supported within the supplied Helper
Profile and current scope, is a semantic or lineage duplicate, is subsumed by a
stronger contribution, or has a conflict that cannot be separated safely into
branches.

`selected`, `deferred`, and `rejected` describe use in this target HarnessSpec
revision only; they do not judge whether the underlying Knowledge record is
correct or useful in a future HarnessSpec revision.
`decision_confidence = null` cannot accompany `selected`.

Each API-specific Knowledge record still requires an applicability check against
the target API Profile. Direct API association alone is insufficient when its
semantic applicability conditions or exclusions do not match the target context.

Use reason codes from the contract. Give every decision at least one reason code
and a concise evidence-based summary.

## 4. Relationship resolution

Create a Resolution Record only for a material interaction among at least two
candidates. Do not record pairs that do not affect selection or branch design.

Interpret relationships as follows:

- `duplicate`: the relevant semantic contribution is equivalent;
- `subsumption`: one candidate contains the useful contribution of another;
- `partial_overlap`: contributions share a subset but retain distinct parts;
- `complementary`: contributions cover compatible, distinct concerns;
- `conflicting`: contributions cannot be satisfied together in the same scope.

Use a permissive merge default: selected contributions in the same target-API
scope should share a Knowledge-directed branch unless a concrete split condition
below applies. Different risk dimensions alone do not require separate branches.

First remove duplicate or subsumed semantic parts. Then merge the remaining
contributions when their combined conditions are satisfiable and their combined
state can be activated and observed in one coherent execution path.

Create separate branches only when at least one split condition applies:

- one requires `intentionally_invalid` inputs while another requires
  `expected_valid` or `boundary_valid` inputs;
- their required Preconditions or Constraints cannot hold together;
- they require mutually exclusive states of the same subject in one invocation;
- they require incompatible device, backend, dispatch, or execution contexts;
- their required Oracles specify incompatible expected behavior;
- their target states need independent API calls or independent activation claims
  to remain meaningful;
- the combined branch has no coherent primary objective or has internally
  inconsistent expected behavior.

When no split condition applies, retain all compatible contributions in one
branch even if they came from different Knowledge records or risk dimensions.
`expected_valid` and `boundary_valid` contributions may share a branch when the
boundary state still satisfies the API's validity requirements; set that branch's
intent to `boundary_valid`. For `partial_overlap`, deduplicate only the shared
part and merge or separate the remaining parts using the same criteria. For `conflicting` candidates, separate
them when branch-local separation is valid; otherwise defer or reject the weaker
contribution.

A merged branch retains all supporting Knowledge IDs. Do not invent a new
Knowledge ID for a merge.

Evaluate selected contributions as a set; do not rely on an LLM-created evidence
ranking or input order. Prefer the smallest number of compatible groups that
preserves all distinct useful contributions. A group remains valid only when its
combined conditions are satisfiable as a whole; pairwise compatibility alone is
not sufficient for a larger group.

## 5. Constraint classification

Classify each condition by semantic role:

- a global Constraint must hold throughout every branch;
- a branch Constraint must hold throughout one branch;
- a Branch Precondition gates entry into one branch;
- a Target Property is a state deliberately generated or explored.

Put a condition in the global set only when it applies to every branch. Do not
treat an intentionally violated API condition as a Constraint of that invalid
branch; express the violated state as a Target Property. Safety, resource,
backend, and environment guardrails remain Constraints when they must still hold.

Use only facts supported by the supplied API Profile, Helper Profile, or selected
Knowledge. Mark evidence status accurately and do not convert missing information
into a guessed requirement.

## 6. Branch construction

Create exactly one `default` branch. It must:

- use `expected_valid` input intent;
- contain no source Knowledge IDs;
- represent the canonical API-valid path;
- include a `target_api_reached` activation target;
- include at least one required Oracle.

A `generic_exploration` branch uses only API/Profile information and contains no
historical Knowledge IDs. Create it only when the API Profile identifies a
distinct, Helper-supported and observable exploration target that is not already
represented by the default branch. It must have an activation target and a
required Oracle. Its content must be derived only from the versioned API and
Helper Profiles; cross-mode comparability is enforced by the experiment
configuration and Builder, not by this LLM decision. Do not create it merely
because no Knowledge was selected.

A `knowledge_directed` branch corresponds to one compatible group of selected
Knowledge contributions and references every selected Knowledge record that
supports that group.

Do not create one branch per Knowledge automatically. Apply the merge-default
and split conditions in Relationship Resolution. A single branch may cover
several compatible risk dimensions and several Knowledge records.

Prefer one Knowledge-directed branch per API when compatible contributions can
share it, but do not impose a fixed branch count. Create an additional
Knowledge-directed branch only when a stated split condition requires it.

Each branch has a concise primary exploration goal. This goal is a label for the
branch's central intent, not a complete replacement for the structured target
properties, constraints, activation targets, and Oracles. A Knowledge-directed
branch may be Oracle- or behavior-directed without introducing a new Target
Property. If no Knowledge is selected, return only the justified default and
optional generic branches.

Do not emit `budget_share`. The Builder assigns initial shares from the versioned
budget policy.

## 7. Merged-branch materialization

Build a merged Knowledge-directed branch by semantic union, not by concatenating
source text:

- `source_knowledge_ids`: stable, deduplicated union of all supporting selected
  Knowledge IDs;
- `risk_dimensions`: deduplicated union of supported risk dimensions;
- `exploration_goal`: a concise primary objective, normally stating context,
  combined target states, and intended observation when applicable;
- `target_properties`: retain each non-conflicting intended state; merge only
  semantically equivalent properties and union their Source References;
- `branch_preconditions` and `branch_constraints`: deduplicate their conjunctive
  requirements; a condition applying to every branch belongs in the global set;
- `activation_targets`: retain evidence for each material Target Property and
  exactly one `target_api_reached` target;
- `oracle_requirements`: retain compatible required observations and deduplicate
  semantically equivalent Oracles.

If two properties describe different states of one subject, retain both only if
they can occur in the same invocation. If they cannot, split the group. Likewise,
split the group when required Oracles imply different expected outcomes.

Use `all_required` when all retained Target Properties are needed to support the
branch's combined claim. Use `any_required` when properties are alternative
trigger states for the same underlying risk or exploration objective and the
Branch remains meaningful when any one occurs. Do not use `any_required` merely
because jointly satisfying required states is difficult or rare.

The primary goal should make the Branch easy to summarize, but it need not carry
all semantic detail in one sentence. Split only when the structured fields reveal
an actual contradiction or no coherent primary objective.

## 8. Target properties and activation

Represent intended risk states as structured Target Properties without Helper
calls or code.

Every branch includes `target_api_reached` at the target call. Every
Knowledge-directed branch must include runtime evidence for its Knowledge-derived
contribution. When that contribution introduces a Target Property, include a
linked `property_state` activation target. A branch whose contribution is solely
Oracle- or behavior-directed may instead use target reachability together with
its Oracle requirements.

Choose observation points semantically:

- input state before the target call;
- reachability at the target call;
- output or post-state after the target call.

Use `all_required` when every activation target is necessary for the branch's
claim. Use `any_required` for alternative trigger states that support the same
underlying risk or exploration objective.

Activation Targets specify what must be observed, not how instrumentation works.

## 9. Oracle requirements

Choose Oracles that match the branch's validity intent, target properties, and
supported capabilities. Do not copy a historical Oracle when it does not fit the
target API.

Every branch has at least one required Oracle. For intentionally invalid inputs,
state the expected exception or safe failure behavior. Differential and
metamorphic Oracles require their semantic preconditions. An Oracle the Helper
Profile cannot implement must not be `required`; prefer a supported Oracle, mark
it `preferred` when still informative, or defer the affected contribution.

Oracle requirements define observations and expected behavior, not code.

## 10. Empty and nullable values

Use `null` only where the contract permits it:

- `semantic_requirement.description` may be `null` when parameters suffice;
- `candidate_decision.decision_confidence` may be `null` only for an unresolved
  decision and never for a selected candidate.

Arrays may be empty only when semantically justified:

- Candidate Decisions only for a baseline or an input with no candidates;
- Resolution Records when no material multi-Knowledge interaction exists;
- source Knowledge IDs only for default or generic branches;
- Branch Preconditions when there is no entry gate;
- branch Constraints when global Constraints are sufficient;
- Target Properties may be empty when a branch has no deliberately explored
  input, output, or state property; an Oracle- or behavior-directed Knowledge
  branch is allowed to use this case;
- Oracle Preconditions when the Oracle has no semantic prerequisite;
- result branch IDs for effects that defer or reject candidates.

Source References for Constraints, Target Properties, Preconditions, and Oracles
must be non-empty whenever the object is emitted.

## 11. Output discipline

Return only the JSON object allowed by the contract. Use exact supplied Knowledge
and source identifiers. Keep summaries concise, record outcomes rather than
hidden reasoning, and do not add undefined fields.

Before returning, verify that:

- every shortlisted candidate has one decision;
- every Knowledge ID referenced by a branch is selected;
- every internal identifier reference resolves;
- every Resolution Record has at least two Knowledge IDs, one interaction
  dimension, and one effect;
- exactly one default branch exists;
- every branch reaches the target API and has a required Oracle;
- a Knowledge-directed branch with a Target Property has a linked property-state
  activation, and an Oracle- or behavior-directed branch has adequate runtime
  reachability and Oracle evidence;
- no Builder-owned field is emitted.
