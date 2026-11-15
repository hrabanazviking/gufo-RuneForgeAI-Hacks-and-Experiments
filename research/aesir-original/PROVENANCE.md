# Provenance — Project Aesir original campaign research

- **Copied:** 2026-11-15, by Yrsa (@yrsafreydisdottir), on Volmarr's order.
- **Primary source:** purpleraider (Volmarr's ASUS ROG Flow Z13, device
  homelink-775910), the hip-serve worktree's records at
  `/home/volmarr/aesir-hipserve/hidden_files/`, read-only pull of the markdown
  records only (tarball sha256
  `0ab2ae593265e3b2294ac82f31f96b9a17fcdea85bef996e615db235999661fd`,
  verified identical on both sides of the transfer).
- **Also checked:** `hrabanazviking/RuneForgeAI-Project-Aesir`, branches `main`
  (`31ab9363`) and `yrsa/hip-serve` (`a04148cc`). The hip-serve branch's
  `hidden_files/` carries the same 42 markdown files by name; the device copies
  were taken as canonical.

## What was taken (42 files, 539,453 bytes)
- `hip-serve/` (8): GATE_AND_27B_RESULTS.md, HS3_RESULTS.md, HS4_RESULTS.md,
  HS5_RESULTS.md, HS6_RESULTS.md, HS7_RESULTS.md, MAP.md, QWEN35_PLAN.md.
- `qwen35-adapter/` (25): QWEN35_RESULTS.md, QC_RESULTS.md, RESIDENCY-NOTE.md,
  LEDGER.md, MAP.md, QC-0-PLAN.md, Q35-1/2/3/3b/3r/4/4b/5/6/7-NOTES.md,
  QC-1/2/3a/3b/4/5/6-NOTES.md, Q8-1-FIX-NOTES.md, F-3b-1-NOTES.md.
- `qwen35-speed/` (9): QS-0-BASELINE.md, QS-1/2/2.5/3/4/5-NOTES.md, LEDGER.md, MAP.md.

## What was deliberately excluded, and why
- `hip-serve/VOXTA_SWITCHOVER.md` — an operational runbook (how to point Voxta at
  the serve), not research.
- All non-markdown material in those folders (build/bench logs, bench scripts,
  shader binaries, config backups) — raw working artefacts, not research documents.
- The A### slice ledgers at the top level of `hidden_files/` (A002…A127 and their
  probe sources/logs) — records of the main Aesir roadmap campaign, a different
  body of work from the serve/adapter/compression/speed research gathered here.
- `research/runner-memory-corpus/` inside the Aesir repo — a byte-identical copy
  of the Ollama research corpus, already imported as Collection 1
  (`../ollama-experiments-corpus/`); not duplicated.
- The Aesir repo's root-level design/spec/task documents — project working
  documentation, not measured research results.
