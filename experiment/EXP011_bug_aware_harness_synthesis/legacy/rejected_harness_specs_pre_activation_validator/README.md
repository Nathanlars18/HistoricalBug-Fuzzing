# Rejected HarnessSpec Pilot Artifact

The archived `torch.matmul` HarnessSpecs passed their then-current structural
Validators but were rejected during human semantic review because selected
Knowledge branches had no `target_properties` or `activation_targets`.

The v0.5 artifact predates the activation gate. The v0.7 artifact exposed a
second ambiguity: historical trigger states were encoded only as Branch
Preconditions after Oracle-only branches became permitted. Associated failed-run diagnostics are retained for auditability. The v0.8
diagnostic additionally records pre-v0.9 field-placement ambiguity among Target
Property requirements, Oracle types, and nested API Profile evidence IDs.

These files were moved here before regeneration and must not be used as
executable Strategy inputs or experimental results.
