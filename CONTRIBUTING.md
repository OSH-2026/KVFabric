# Contributing

Thanks for considering a contribution to KVFabric.

## Current Stage

This repository is currently in the baseline and architecture phase. The most valuable contributions right now are:

- documenting vLLM deployment and bring-up details
- improving reproducible environment notes
- refining benchmark and workload definitions
- scoping Python-layer vLLM prototype changes around scheduler and KV cache management
- reviewing architecture and module boundaries for the future C++ runtime

## Development Workflow

1. Create a branch for your change.
2. Keep changes focused on one topic.
3. If your change affects baseline validation, include:
   - target environment
   - commands executed
   - observed behavior
4. Open a pull request with:
   - motivation
   - design summary
   - affected documents or baseline steps
   - validation notes

## Coding Notes

- Do not add custom runtime code before the vLLM baseline and Python-layer prototype boundary are clearly established.
- Prefer design notes, deployment records, and benchmark plans over premature implementation.
- For short-term vLLM source changes, prefer Python control-plane paths such as scheduler, KV cache manager, block pool, and metadata/metrics code.
- Do not touch C++/CUDA kernels unless the change explicitly requires new physical KV layout, slot-mapping semantics, or kernel-level copy/write behavior.
- Keep the long-term goal aligned with a portable C++ scheduler/runtime.
