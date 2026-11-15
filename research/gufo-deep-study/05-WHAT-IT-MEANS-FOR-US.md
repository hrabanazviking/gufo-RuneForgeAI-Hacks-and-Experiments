# 05 — What It Means for Us: Gufo on the RuneForgeAI Road

Synthesis for Volmarr's fleet and projects, from dossiers 01–04 (upstream
tree at `800ce328`, v0.34.0). Our side of each comparison is cited to our
own campaign records; Gufo's side is cited to its docs as in the earlier
dossiers. Nothing here was run on purpleraider — the machine is paused by
Volmarr's order and this study is VM + web only; every "would/should"
below waits for his "done done" or a specific order.

## 1. The fit in one paragraph

Gufo is, almost eerily, the engine our own work has been converging
toward: one Strix Halo machine, a curated Qwen3.8 27B, a checkpoint cache
built for long agent conversations, speculative decoding with an
exactness contract, and quality graded against independent references.
Our Aesir campaign proved the same truths from the other side (hybrid
qwen35 state cannot be rewound; prefix snapshots must be bit-exact;
HIP decode speed is the hard part). Gufo is the mature, MIT-licensed,
actively maintained implementation of that shape — 41 releases in three
months, two principal authors, hardware-gated CI. For purpleraider's
long-term "use our own programs instead of Voxta" road, Gufo is both a
candidate serving layer *and* the reference implementation to measure
Aesir against.

## 2. Install roads under the no-Docker law

Volmarr's law: no Docker ever on his machines; the project's quickstart
defaults to Podman/toolbox images, which are therefore **not our road**.
Gufo offers three native roads (`docs/install.md`), in our order of
preference:

1. **The Debian package** — `gufo_<version>-1_amd64.deb` attached to each
   GitHub release, built for Debian 13 with AMD's ROCm packages, verified
   by the project in a fresh container, checksum published. On
   purpleraider (Kubuntu 26.10) this is the fastest evaluation road:
   `sudo apt install ./gufo_...deb; gufo diagnose`. Caveat to verify at
   install time: the package targets Debian 13; Kubuntu's library
   versions may differ — `gufo diagnose` is the arbiter.
2. **Nix** — `nix profile install github:gufo-org/gufo#release` installs
   the lock-mode shipped build (official extensions only); Cachix
   (`gufo.cachix.org`) provides binaries. This is the project's own
   reference toolchain (GCC 16.2 + ROCm 10.1.0), and the only road that
   carries the ROCm queue-residency patch by default. It is also the
   road that reproduces their published numbers.
3. **Source build** — Nix dev shell preferred; without Nix: C++20
   compiler, CMake ≥3.21 (≥3.27 for extension modules), Ninja, ROCm
   HIP/hipBLAS/hipBLASLt/rocBLAS/hipCUB/rocPRIM/rocWMMA, Rust 1.88+,
   ICU/curl/OpenSSL/png/jpeg/webp, and XRT built from `amd/xdna-driver`
   for the NPU. This is the road our fork work would use, and the one
   where the ROCm patch (`.devops/nix/patches/rocr-fixed-cwsr-rocm10.
   patch` — keeps GPU queues resident under memory pressure) must be
   applied by hand outside Nix.

Host prerequisites to check on purpleraider before any road: kernel
≥6.18.4 (we run 7.3 — fine), linux-firmware ≥20260110 (ours is 20260915 —
fine), `video`+`render` group membership, `/dev/kfd` + render nodes +
`/dev/accel/accel0` present. **Two standing warnings from their docs map
directly onto our crash history:** heavy GPU + NPU work simultaneously
can hang some Strix Halo hosts until power-cycled (amd/xdna-driver#1605)
— serialize GPU/NPU loads in any Gufo trial plan; and the NPU's
runtime-suspend wake costs ~110 ms on the first request after 5 s idle.

Model files: `gufo model install qwen27-q4` (or `qwen27-q8`) fetches the
pinned Unsloth UD GGUFs + mmproj + the DFlash2 draft, hash-verified, into
`$GUFO_MODELS_DIR` or `~/.local/share/gufo/models`. **Storage law
applies:** point `GUFO_MODELS_DIR` at the vault
(`/mnt/vault/models/gufo`) — programs on the SSD, all model bulk on the
4 TB vault. Note the 27B Q8 target file is 29.30 GiB and Q4 16.45 GiB —
different files from our heretic GGUFs (see §5).

## 3. The cache question — Gufo vs the Ollama Memory Forge vs Aesir

Three different answers to "the model forgets / the prompt is re-paid
every turn," now directly comparable:

| | Gufo continuation cache | Ollama Memory Forge (ours, purplelongship) | Aesir residency (ours, purpleraider) |
| --- | --- | --- | --- |
| Layer | Inside the engine, at the state level | In front of stock Ollama, at the text level | Inside our engine, session level |
| What is kept | Checkpoints: frozen recurrent state + shared KV chunks, RAM + disk tiers | Anchor block + distilled fact ledger + prose summary band, re-injected as text | Resident session: prefix snapshots (SSM+conv+boundary KV), bit-exact restore |
| Hybrid models | Designed for them; checkpoints because recurrent state can't rewind | Model-agnostic (works on any Ollama model) | qwen35 adapter built for exactly this; snapshots ≈158.9 MB for the 27B |
| Edit handling | Fall back to deepest checkpoint before the edit; recompute the gap | Ledger supersedes facts; raw turns shed in batches | Snapshot restore at stored boundaries |
| Measured effect | 101,545-token prompt: 280.4 s → 2.4 s; disk restore 24,866 tok in 1.8 s vs ~50 s | Overflow accuracy: H-facts 0/4 correct/4 wrong → 4/4 correct/0 wrong; front-edit prefill ~56% cut | Prefix restore bit-exact (logits diff 0.0 on resident path) |
| Failure it fixes | Re-prefill cost (speed) | Silent middle-cut + confabulation (accuracy) — Ollama truncates long prompts with no API warning (our ZO-2 finding) | Re-prefill cost + session continuity for Voxta |

The honest synthesis: **these solve different problems and compose.**
Gufo's cache makes long conversations *fast* but does not change what
the model *remembers* beyond the context window; the Memory Forge's
ledger makes overflow *truthful* but pays text-level re-injection costs.
A Gufo serving layer under a Memory-Forge-style anchor/ledger front end
is a coherent architecture for Rúnmál-class workloads — and Gufo's
learned-checkpoint mechanism (capture a checkpoint where conversations
diverge, ≥512 tokens past the restore point) is a design our Aesir cache
work should study closely: it solves the shared-system-prompt subagent
pattern that our own subagent crews generate constantly. Conversely,
Gufo's provenance rule — chunks shared by computation provenance, never
by content, because different prefill shapes yield last-bit-different
bytes — validates Aesir's bit-exactness discipline from an independent
implementation, and its "same tokens aren't the same bytes" section is
the clearest published explanation of why our Q35 snapshot work had to
be exact.

## 4. ASR/TTS and the Voxta SenseVoice gap

Our open wound: Voxta's SenseVoice transcription dies on purpleraider
("Could not import module 'Qwen3ForCausalLM'" — torch 2.9.1's quantizer
under Python 3.14), leaving Voxta's AudioTranscription role disabled.
Gufo bears on this three ways:

- **Qwen3-ASR 1.7B is a core Gufo extension** (GPU + NPU) with a published
  functional contract: English WER ≤ 0.15, exact greedy replay, streaming
  SSE equal to buffered output, malformed-WAV recovery. It is a
  maintained, native, torch-free ASR path on exactly our hardware — a
  credible replacement transcription service behind an OpenAI-compatible
  surface, independent of the SenseVoice repair.
- **Qwen3-TTS 1.7B with voice cloning** is likewise core (GPU + NPU).
  Our Orpheus TTS in Voxta was fixed and load-proven 2026-11-14, so TTS
  is a comparison opportunity rather than a gap — but a single-binary
  ASR+TTS pair from one engine simplifies the eventual post-Voxta stack.
- Neither fixes SenseVoice *inside* Voxta (Voxta calls its own module);
  the import-ladder diagnosis remains owed on its own merits. Gufo's
  bearing is on the replacement road, not the repair road — dossier
  honesty requires saying so.

## 5. Model identity caution — the heretic files are not Gufo's files

Gufo's 27B support is written against **Unsloth UD-Q4_K_XL / UD-Q8_K_XL**
GGUFs of Qwen3.8-27B (architecture per its probes), with its own DFlash2
draft. Our vault's 27B is the *heretic* Q8_0 build (28,596,003,296 B,
architecture `qwen35`) plus DavidAU's MTP Q4_K_M cut. Whether Gufo's
qwen27 provider probe accepts the heretic file is an empirical question
for the evaluation sitting — probes answer from metadata, and a refusal
is a clean error, not a partial run. The Flash-Next flagship is likewise
Gufo's own curated artifact. Plan any trial around Gufo's pinned files
first (downloaded to the vault), and treat heretic-file acceptance as a
bonus experiment, not the baseline. The same caution applies to the 40B:
Gufo has no 40B — its ceiling is the 27B/Flash-Next class by curation,
and the 40B remains Aesir/Ollama territory.

## 6. Speed expectations, honestly framed

Our Ollama yardsticks on purpleraider (ZO road, tuned): 27B Q8 gen
7.58 tok/s, Q4 12.24 tok/s, 7B 44.91 tok/s. Gufo's published method
(pp2048/tg128 through HTTP, reference implementation beside it) and its
per-model tables in `docs/internal/models/*/BENCHMARKS.md` are the only
numbers to quote before we measure; fork-circulated figures (~650 tok/s
prefill, ~70 tok/s single-user decode for the 27B Q4 with DFlash2) suggest
the gap Ollama leaves on this hardware is large — decode several-fold —
but our own standard applies: **no number is ours until we measure it on
purpleraider under the machine laws** (fenced, serialized, MemAvailable
checked, never on a just-booted machine, never while Volmarr is using
it). When that sitting comes, Gufo's own `benchmark-model` skill is the
procedure to follow — it is stricter than ours in two places worth
adopting regardless: recording the ACPI platform profile with every run,
and cold-cache runs verified with `mincore`.

## 7. Method transfers — what to steal for our own projects

Independent of whether Gufo ever runs here, its protocols are a toolbox
for RuneForgeAI (all consistent with Volmarr's existing laws; listed
because Gufo proves them at scale):

- **The timing law** (per-request/per-phase, never averaged; noisy =
  visibly inconclusive; never widen margins) — a sharper form of our
  verify-from-disk discipline, directly adoptable in Aesir/MimirAlloc
  reporting.
- **Matched-token grading** — Gufo's teacher/candidate distribution
  comparison is our Aesir raw-oracle discipline, independently derived;
  their "earliest changed boundary" debugging ladder (embedding →
  normalization → attention → recurrent state → expert → layer → LM
  head) is a checklist our debug-model skill can absorb.
- **Frozen-oracle port proofs** for any future component migration,
  including the retirement rule: once the port ships, replace comparison
  loops with expected-result tests.
- **The docs constitution** — public pages: current behavior only, no
  history, dated exact numbers, line budgets, a filler ban list, prose
  that fully describes every figure "because agents read the text."
  Adoptable wholesale for our public repos' docs.
- **Immutable change records** for public contracts (the `ext/changes/`
  pattern) — a cleaner audit trail than changelog archaeology for
  Aesir's serve API and Rúnmál's engine contracts.
- **The registry review checklist** as the template for any future
  RuneForgeAI extension/plugin trust decision: whole-diff reading, no
  unreviewable binaries, public surface only, reachable maintainers.
- **Ship-your-procedures-as-skills**: Gufo versions its agent procedures
  (`.agents/skills/`) inside the repo — our custom-skills practice, in
  their case traveling with the code they govern.

## 8. Fork etiquette — what stays private, what could go upstream

The fork is `hrabanazviking/gufo-RuneForgeAI-Hacks-and-Experiments`
(public, Volmarr's), described by him as "hacks and mad data science
experiments… We will try to donate back to the project but we cannot know
if they will like our crazy ideas!" Operating rules that follow from
dossier 04:

- **The fork is our lab notebook, not a billboard.** Research corpora
  (this study; the Ollama/Aesir/MimirAlloc imports on
  `yrsa/research-import`) live on side branches; `main` tracks upstream
  so future syncs stay cheap; no README edits (Volmarr's law and plain
  courtesy agree here).
- **Private by default:** anything touching Volmarr's machines,
  characters, or household (the standing privacy law) never leaves the
  fork's research branches, let alone goes upstream. Upstream material
  is limited to hardware/engine knowledge that is already impersonal:
  Strix Halo measurements, kernel experiments, cache findings.
- **Plausible donations, in their shapes:** (a) a *community extension*
  in our own repo (catalogue string `gufo-extension` in the
  description) if a RuneForgeAI model variant ever proves out — the
  door they built for exactly this; (b) small core PRs for measured
  gfx1151 defects or kernel wins, evidence-complete per dossier 04 §9;
  (c) benchmark/quality evidence filed as issues with full provenance
  when we find discrepancies — their culture treats a well-evidenced
  discrepancy report as a contribution; (d) if a hack grows into a
  divergent direction (as RDMA did), a named community fork linked
  from our side, offered for their community list.
- **Never:** a PR that asks them to bless the heretic weights, other
  hardware, Docker-based tooling for its own sake, or output-changing
  "optimizations." Each contradicts a stated principle; offering them
  would spend goodwill the fork may need later.
- **Attribution flows both ways:** our fork's research files carry
  provenance notes (as the import crew's `PROVENANCE.md` files do);
  anything of Gufo's we adapt in Aesir or elsewhere gets NOTICE-style
  credit at commit granularity — their standard, applied to ourselves.

## 9. Recommended sequence (for Volmarr's word, not started)

1. On his "done done" (or a specific order): install the Debian package
   on purpleraider, `GUFO_MODELS_DIR` on the vault, `gufo diagnose`,
   install `qwen27-q4`, run their benchmark procedure against our
   Ollama yardsticks — one fenced sitting, machine laws obeyed.
2. Probe test: offer Gufo the heretic Q8_0 file; record accept/refuse
   as evidence either way.
3. ASR trial: Qwen3-ASR behind a loopback endpoint as a SenseVoice
   alternative for the post-Voxta stack (not wired into Voxta).
4. Only after measurements exist: decide Gufo's place — serving layer
   candidate, Aesir reference, or study-only — and whether any hack is
   ripe to shape into an extension or PR under §8.

## Sources

- Dossiers 01–04 of this corpus and their sources (upstream tree at
  `800ce328`; `docs/install.md`; `docs/cache.md`; registry `REVIEW.md`;
  blog posts).
- Our records: Ollama Memory Forge campaign (OM-7/OM-8 gate records,
  `~/workspace/goals/ollama-memory-forge/`); Z13 Ollama front ZO-2/ZO-6
  records (RuneForgeAI-Ollama-Experiments); Aesir Q35/QC campaign records
  (purpleraider `~/aesir-hipserve/hidden_files/qwen35-adapter/`); Voxta
  AMD rebuild notes, 2026-11-14.
