# Environment

This directory records lightweight, project-owned environment inputs. The
PyTorch fuzzing and coverage runtimes are built as Docker images under
`runtime/`; the local Python virtual environment is only for control scripts,
metadata processing, schema validation, and experiment orchestration.

## Local Python control environment

Create the environment from the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r environment/python-control-requirements.txt
```

The `.venv/` directory is local state and must not be committed.
