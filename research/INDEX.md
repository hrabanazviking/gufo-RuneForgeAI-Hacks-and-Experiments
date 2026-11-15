# Research brought into the Gufo fork — Index

On 2026-11-15 Volmarr ordered three bodies of original RuneForgeAI research banked
into this fork (`hrabanazviking/gufo-RuneForgeAI-Hacks-and-Experiments`), so the
Gufo hacks and experiments on AMD Strix Halo (gfx1151) can draw on everything the
earlier campaigns learned about running models and about memory. Copied 2026-11-15
by Yrsa (@yrsafreydisdottir, write collaborator) onto branch `yrsa/research-import`.
All copies are byte-identical to their sources; each collection folder carries its
own `PROVENANCE.md` with full source details and exclusion notes.

## 1. `ollama-experiments-corpus/` — the Ollama-hack research corpus
The whole research corpus built for the Ollama Memory Forge campaign: the field map
of model runners (v4), 35 runner dossiers, 78 paper dossiers, 15 memory dossiers,
the Aesir study, the MASTER-COMPENDIUM and MEMORY-COMPENDIUM, the IDEA-LEDGER (v6:
59 ranked ideas, 29 rejected/deferred, 35 open questions), the living bibliography,
and the machine-verified index.
**134 files, 5,641,040 bytes.**
Source: `hrabanazviking/RuneForgeAI-Ollama-Experiments`, branch `yrsa/research-corpus`,
head `fefe7c2e95a01164e3f2855239df9bd7c7fac8bc`, `research/` tree.

## 2. `aesir-original/` — Project Aesir's own campaign research
The measured results, verdicts, ledgers, maps and slice notes of the three Strix Halo
serve campaigns run for Project Aesir on the Z13 (purpleraider): the HIP serve line
(`hip-serve/`: HS3–HS7 results, gate + 27B results, campaign map, Qwen3.5 plan), the
Qwen3.5 hybrid-memory adapter + QC compression campaigns (`qwen35-adapter/`:
QWEN35_RESULTS.md, QC_RESULTS.md, RESIDENCY-NOTE.md, ledger, map, Q35/QC slice notes),
and the speed campaign (`qwen35-speed/`: QS-0 baseline through QS-5 notes, ledger, map).
**42 files, 539,453 bytes.**
Source: purpleraider (device), `/home/volmarr/aesir-hipserve/hidden_files/`, copied
2026-11-15; the same markdown set is also banked in `hrabanazviking/RuneForgeAI-Project-Aesir`,
branch `yrsa/hip-serve`, head `a04148cc`.

## 3. `mimiralloc/` — MimirAlloc original research data
The MimirAlloc campaign record: the full `docs/` tree (248 files — campaign closure
Z-117, the Z-series slice records, `docs/research/`, `docs/field-notes/`, failure
taxonomy and classification records) plus one preserved evidence run
(`evidence/runs/20261106T114752Z-smoke-fail-0f4a3c/`, 6 files). Includes the honest
benchmark verdicts, among them the Pi campaign's grading against glibc.
**254 files, 4,376,302 bytes.**
Source: `hrabanazviking/RuneForgeAI-MimirAlloc`, branch `main`,
head `e78d8716` (Z-117 campaign closure commit).

## Why here
Gufo is an inference engine built for exactly this chip. These three collections are
the measured ground truth the RuneForgeAI side already owns — runner behaviour,
memory behaviour, adapter/compression/speed verdicts on gfx1151, and allocator
benchmarks — gathered in one place so Gufo experiments start from evidence, not
from scratch.
