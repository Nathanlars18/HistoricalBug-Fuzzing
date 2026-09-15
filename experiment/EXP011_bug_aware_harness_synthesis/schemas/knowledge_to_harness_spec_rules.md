# Knowledge-to-HarnessSpec Synthesis Rules v1.7

## 1. Scope

These rules guide the LLM in converting one target-API input bundle into the
semantic portion of a HarnessSpec.

Inputs are:

- one API Profile;
- compact synthesis views of available Helper Profiles;
- compact synthesis views of deterministically supplied eligible API-specific Knowledge records;
- the HarnessSpec synthesis contract.

The contract defines output shape, controlled vocabularies, and Builder-owned
fields. These rules define synthesis decisions only. Do not reproduce source
records, code, Helper calls, Strategy Primitives, hidden reasoning, or
Builder-owned fields.

## 2. Processing order

1. Assess each eligible Knowledge record's applicability to the target API.
2. Screen its semantic needs against capabilities advertised by the available Helper Profile set.
3. Select, defer, or reject every eligible Knowledge record.
4. Resolve material relationships among eligible Knowledge records.
5. Derive global validity constraints.
6. Construct exploration branches.
7. Define target properties and activation targets.
8. Define Oracle requirements.
9. Verify references and output only the contract response.

Do not select a Knowledge record merely to ensure historical Knowledge is used. A valid
result may contain no selected Knowledge.

The Builder has already determined the eligible Knowledge input set. Do not
perform retrieval, add unseen Knowledge, or make a second prompt-length or
execution-budget selection decision in this step.

## 3. Knowledge decisions

Create exactly one decision for every eligible Knowledge record supplied to
synthesis.

Select a Knowledge record only when all of the following hold:

- it is `applicable`, or its explicitly identified applicable subset is usable;
- the available Helper Profile set advertises support for the selected semantic
  contribution, or for an explicitly identified usable subset;
- it contributes a distinct risk, target property, exploration goal, or Oracle;
- its contribution can form a valid branch alone or with compatible Knowledge records;
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

`capability_status` is preliminary capability compatibility, not final Strategy
feasibility. Use `supported` when profiles advertise all capabilities needed by
the selected contribution; use `partially_supported` only when the selected
usable subset is advertised but other Knowledge content is not. Final Helper
binding, execution ordering, fallback, and implementation feasibility belong to
the Strategy layer.

Each API-specific Knowledge record still requires an applicability check against
the target API Profile. Direct API association alone is insufficient when its
semantic applicability conditions or exclusions do not match the target context.

Use reason codes from the contract. Give every decision at least one reason code
and a concise evidence-based summary.

## 4. Relationship resolution

Create a Resolution Record only for a material interaction among at least two
eligible Knowledge records. Do not record pairs that do not affect selection or branch design.

Interpret relationships as follows:

- `duplicate`: the relevant semantic contribution is equivalent;
- `subsumption`: one Knowledge record contains the useful contribution of another;
- `partial_overlap`: contributions share a subset but retain distinct parts;
- `complementary`: contributions cover compatible, distinct concerns;
- `conflicting`: contributions cannot be satisfied together in the same scope.

Use a permissive merge default: selected contributions in the same target-API
scope should share a Knowledge-directed branch unless a concrete split condition
below applies. Different risk dimensions alone do not require separate branches.

First remove duplicate or subsumed semantic parts. Then merge the remaining
contributions when their combined semantic conditions are satisfiable, no known
capability contradiction exists, and one coherent branch claim can be stated.
This is not proof that a concrete Strategy can implement the branch.

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
part and merge or separate the remaining parts using the same criteria. For `conflicting` Knowledge records, separate
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
- a Branch Precondition gates entry into one branch but is not itself the state being explored;
- a Target Property is a state deliberately generated or explored.

A historical input, output, relation, or context state named by the branch goal
must not be represented solely as a Branch Precondition. Encode it as a Target
Property and use a linked Activation Target. Do not duplicate the same semantic
state as both a Precondition and a Target Property; reserve Preconditions for
independent feasibility or entry conditions.

Put a condition in the global set only when it applies to every branch. Do not
treat an intentionally violated API condition as a Constraint of that invalid
branch; express the violated state as a Target Property. Safety, resource,
backend, and environment guardrails remain Constraints when they must still hold.

Use only facts supported by the supplied API Profile or selected Knowledge. Mark
evidence status accurately and do not convert missing information into a guessed
requirement. Helper Profiles may screen capability compatibility, but must not be
cited as semantic evidence for a Constraint, Precondition, Target Property, or
Oracle.

## 6. Branch construction

Create exactly one `default` branch. It must:

- use `expected_valid` input intent;
- contain no source Knowledge IDs;
- represent the canonical API-valid path;
- include at least one required Oracle.

For `controlled_baseline`, return exactly this default branch. Do not create `generic_exploration` or `knowledge_directed` branches.

A `generic_exploration` branch is available only in bug-aware modes. It uses only API/Profile information and contains no
historical Knowledge IDs. Create it only when the API Profile identifies a
distinct, Helper-supported and observable exploration target that is not already
represented by the default branch. It must have an activation target and a
required Oracle. Its content must be derived only from the versioned API and
Helper Profile set; cross-mode comparability is enforced by the experiment
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

Do not emit `budget_policy_ref` or `budget_share`. For a controlled baseline, the Builder stores a null policy reference and assigns the sole default branch a share of `1.0`. For revision 1 of either bug-aware mode, it records the versioned initial policy and assigns shares from that policy. Later Adaptive revisions are owned by the feedback stage and must reference their feedback-derived policy.

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
- `activation_targets`: retain one required observation target for each material
  Target Property that supports a risk-activation claim;
- `oracle_requirements`: retain compatible required observations and deduplicate
  semantically equivalent Oracles.

If two properties describe different states of one subject, retain both only if
they can occur in the same invocation. If they cannot, split the group. Likewise,
split the group when required Oracles imply different expected outcomes.

All emitted Activation Targets are required for the branch's risk-activation
claim. Alternative target states use separate branches; do not encode an `any`
combination inside one branch.

The primary goal should make the Branch easy to summarize, but it need not carry
all semantic detail in one sentence. Split only when the structured fields reveal
an actual contradiction or no coherent primary objective.

## 8. Target properties and activation

Represent intended risk states as structured Target Properties without Helper
calls or code. Use the shared Semantic Requirement representation, stable API
Profile parameter identifiers, and normalized property paths. Each Target
Property lists one or more risk dimensions, all of which also occur in the
containing branch.

Every executable branch must reach the target API, but target reachability is a
fixed downstream execution and monitoring invariant rather than an Activation
Target. Every Knowledge-directed branch must include structured evidence of its
Knowledge contribution. When that contribution introduces a Target Property,
include exactly one linked Activation Target. A selected Knowledge contribution
may have no Target Property only when it introduces no deliberately generated or
explored state and is solely Oracle- or behavior-directed. In that case add
`oracle_only_contribution` to that Knowledge Decision's `reason_codes` and cite
the Knowledge from a supported Oracle. Do not use this code merely because a
trigger state was placed in Branch Preconditions.

Choose observation points semantically:

- a non-transition input, relation, or context state uses one `evaluate` point;
- an output property uses one `evaluate` point after the target call;
- a `state_transition` uses one `before` and one `after` point.

Every Activation Target references exactly one Target Property. All Activation
Targets in one branch are required for the branch's risk-activation claim.
Alternative target states require separate branches.

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

Every Oracle has one or more observation subjects. Use exact API Profile
`parameter_id` or `return_id` values, or one of `context.backend`,
`context.device`, `context.autograd`, `context.execution`, and
`context.resource`. Choose subjects from the behavior actually evaluated:

- crash, exception, sanitizer, and timeout Oracles normally observe
  `context.execution`;
- output-property and determinism Oracles normally observe an exact return ID;
- resource-usage Oracles normally observe `context.resource`;
- differential, metamorphic, and state-consistency Oracles name every API input
  or result required by their comparison.

Do not emit an empty subject list, generated C++ variable name, Helper ID, or
free-form description as an observation subject.

Keep Oracle type and expected behavior distinct. `oracle_type` uses only the
Oracle vocabulary. For example, a no-crash check uses `oracle_type: crash` and
`expected_behavior.requirement_type: no_crash`; a repeated-result check uses
`oracle_type: determinism` and
`expected_behavior.requirement_type: result_equivalence`. Oracle-only
requirement types such as `result_equivalence` and `no_crash` must not be used as
Target Property requirement types.

Oracle requirements define observations and expected behavior, not code.

## 10. Empty and nullable values

Use `null` only where the contract permits it:

- `semantic_requirement.description` may be `null` when parameters suffice;
- `knowledge_decision.decision_confidence` may be `null` only for an unresolved
  decision and never for a selected Knowledge record.

Arrays may be empty only when semantically justified:

- Knowledge Decisions only for a baseline or an input with no eligible Knowledge records;
- Resolution Records when no material multi-Knowledge interaction exists;
- source Knowledge IDs only for default or generic branches;
- Branch Preconditions when there is no entry gate;
- branch Constraints when global Constraints are sufficient;
- Target Properties may be empty when a branch has no deliberately explored
  input, output, relation, or context state; every source Knowledge in such a
  Knowledge-directed branch uses `oracle_only_contribution` and is cited by an
  Oracle;
- Activation Targets may be empty when Target Properties are empty; otherwise
  each risk-claim Target Property has exactly one Activation Target;
- Oracle Preconditions when the Oracle has no semantic prerequisite;
- result branch IDs for effects that defer or reject Knowledge records.

Source References for Constraints, Target Properties, Preconditions, and Oracles
must be non-empty whenever the object is emitted.

## 11. Output discipline

Return only the JSON object allowed by the contract. A semantic Source Reference
uses only the exact supplied API Profile `profile_id` or eligible Knowledge
`knowledge_id`; never use an internal API Profile or Knowledge evidence ID as
`source_id`. Keep summaries concise, record outcomes rather than
hidden reasoning, and do not add undefined fields.

Before returning, verify that:

- every supplied eligible Knowledge record has one decision;
- every Knowledge ID referenced by a branch is selected;
- every internal identifier reference resolves;
- every Resolution Record has at least two Knowledge IDs, one interaction
  dimension, and one effect;
- exactly one default branch exists;
- every branch has a required Oracle and is semantically intended to reach the
  target API;
- every Oracle has at least one observation subject that resolves to the API
  Profile or the allowed `context.*` vocabulary;
- each Target Property risk dimension is included in its branch;
- every risk-claim Target Property has exactly one linked Activation Target with
  a valid observation-point shape;
- every selected Knowledge is cited by at least one substantive Constraint,
  Precondition, Target Property, or Oracle, and each Knowledge-directed branch's
  source IDs equal its branch-local Knowledge Source Reference union;
- every non-Oracle-only source Knowledge of a Knowledge-directed branch is cited
  by a Target Property; every `oracle_only_contribution` source is cited by an
  Oracle and not by a Target Property;
- no Builder-owned field is emitted.
