# Provenance — MimirAlloc original research data

- **Copied:** 2026-11-15, by Yrsa (@yrsafreydisdottir), on Volmarr's order.
- **Source repo:** `hrabanazviking/RuneForgeAI-MimirAlloc`
- **Source branch:** `main`
- **Source head:** `e78d8716` ("Z-117: Campaign closure")

## What was taken (254 files, 4,376,302 bytes)
- The complete `docs/` tree (248 files, 244 markdown + 4 JSON): the Z13 Z-117
  campaign closure (`docs/Z13_Z117_CAMPAIGN_CLOSURE.md`), the Z-series slice
  records (benchmarks, verdicts, postmortems, energy/perf studies), the Pi
  campaign records including the honest grading against glibc, `docs/research/`
  (59 files), `docs/field-notes/` (15 files), and the failure-taxonomy /
  classification records.
- One preserved evidence run (6 files): `evidence/runs/20261106T114752Z-smoke-fail-0f4a3c/`
  (manifest, case record, command, stdout/stderr logs, SHA256SUMS).

## What was deliberately excluded, and why
- `src/`, `include/`, `tests/`, `scripts/`, `release/`, the Makefile — source
  code and build machinery, not research documents.
- Repo-root images and unrelated essays (e.g. `why_i_hate_docker.md`) — not
  MimirAlloc campaign research.
