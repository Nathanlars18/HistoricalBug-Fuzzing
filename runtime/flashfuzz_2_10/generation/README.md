# Python Generation and API-Profile Environment

This directory is reserved for a separately pinned Python environment using
PyTorch 2.10. It will support API Profile extraction and Harness generation.

It is intentionally not created from the existing FlashFuzz `torch==2.7.0`
environment. The exact Python dependency lock will be added after the C++
PyTorch 2.10 fuzz runtime has passed its first smoke test, so the profile and
target runtime are validated against the same framework release.
