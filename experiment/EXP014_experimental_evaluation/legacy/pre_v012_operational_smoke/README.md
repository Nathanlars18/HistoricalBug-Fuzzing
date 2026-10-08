# Pre-v012 operational smoke archive

The `lineage_manifest.json` logically archives 29 previous generated
configurations and six earlier operational run indexes. These records include
interrupted runs and intermediate snapshots; they are not formal experiments
or substitutes for the completed v012 checkpoint.

Frozen configurations stay at their original `configs/` paths, preserving
their hashes. Local run directories stay at their original `runs/` paths so
logs, retry history and evidence references remain usable. Do not refresh old
matrix hashes, overwrite old directories, or present interrupted runs as
successful after later code repairs.

The current checkpoint uses `configs/two_api_operational_smoke__v012.json` and
`runs/two_api_operational_smoke_v012`. Synthetic feedback/replay fixtures are
separate interface tests, never experimental outcomes.

Git publishes source, contracts, reviewed inputs and bounded checkpoint
reports. Large local profiles, binaries, corpora and full candidate evidence
are retained locally, not deleted or uploaded as part of this archive.
