# 01 — The Project: What Gufo Is and How It Is Built

Sources: upstream tree at `800ce328` (`README.md`, `docs/`, `docs/internal/`,
`NOTICE`, `docs/reference-projects.md`), gufo.blog (homepage + all three blog
posts), GitHub API. See `00-INDEX.md` for method.

## 1. One paragraph

Gufo is an open-source (MIT) inference engine built for exactly one machine
class: **AMD Strix Halo** — the Ryzen AI MAX+ 395 with its Radeon 8060S
integrated GPU (`gfx1151`) and up to 128 GiB of unified memory. It is a single
native binary (no Python or other runtime dependency in the shipped artifact)
that serves text, vision, embeddings, speech recognition, speech synthesis
with voice cloning, image generation/editing, and video generation through
OpenAI-compatible HTTP APIs, on Linux (the released, tested platform) and
native Windows. The project began, by its own account on the blog
("Why does Gufo have a blog?", 2026-10-16), as a pet project: the authors
bought a Framework Desktop with Strix Halo as a homelab, tried Ollama and
llama.cpp, and were "annoyed that we couldn't use our hardware at its peak
potential" — breadth-first engines cannot tune kernels for every backend, so
Gufo narrowed the scope to one machine and a few models and asked how far
they can go. The repository was created 2026-08-11; by 2026-11-15 it had
1,180 stars, ~207 forks, 63 contributors, 525 issues, 691 pull requests (566
merged), and 41 releases, the latest being v0.34.0 (2026-11-11).

## 2. The four principles (README.md, stated verbatim in substance)

1. **One machine.** Everything is tuned for Strix Halo and nothing else. The
   build enforces it: the CMake option `ENGINE_ENABLE_HIP` accepts **only
   `gfx1151`** (`docs/internal/development.md`). There is no discrete-GPU or
   other-vendor path, and the project says so plainly.
2. **The best model per use case.** Gufo ships few models on purpose: fewer
   models means less code and more optimization per model. Each model keeps
   its own kernels, so a change to one model cannot break another. The blog
   ("Bring your own model", Nov 2026) is candid about the cost: this rule
   "is also why a few models and quantizations requested by the community
   have not been upstreamed" — the extension system (section 6) is the
   project's answer to that friction.
3. **Quality before speed.** Every model carries a quality report comparing
   it against an independent reference implementation. In the README's own
   words: "an optimization that changes the output isn't one." Speculative
   decoding must reproduce exactly what plain autoregressive decoding would
   have produced (see section 5).
4. **Real workloads.** Concurrent requests, cancellation, and long
   conversations are first-class design cases, not afterthoughts — the
   continuation cache (section 4) exists because coding agents resend
   100k-token conversations every turn.

A fifth, quieter principle runs through the internal docs: a **small
production footprint** — few runtime dependencies, and development/reference
tooling kept out of the shipped package (`docs/internal/development.md`,
`docs/internal/releasing.md`).

## 3. The model curation method

The shipped set (README.md models table; `extensions.lock`) is eight
extensions covering nine model rows:

| Model | Capability | Weight license (per README) |
| --- | --- | --- |
| Qwen3.8 Flash-Next | text + images (flagship hybrid) | Qwen Community License 1.0 |
| Qwen3.8 27B | text + images, dense | Apache-2.0 |
| DeepSeek V4 Flash | text (MoE) | MIT |
| EmbeddingGemma 2 | multimodal embeddings (GPU + NPU) | Apache-2.0 |
| Qwen3-ASR 1.7B | speech to text (GPU + NPU) | Apache-2.0 |
| Qwen3-TTS 1.7B | speech synthesis + voice cloning (GPU + NPU) | Apache-2.0 |
| Qwen-Image-2.1 + Turbo | image generation/editing | Qwen Research License (non-commercial) |
| MiniMax H3 | video with sound | MiniMax H3 Community License |

Curation mechanics worth noting:

- **Shipping is a one-line act.** A model becomes official by being listed
  in `extensions.lock` (`{"schema":1,"extensions":[...]}` at the repo root);
  discovery builds compile every extension present, lock builds compile
  exactly the list (`docs/internal/development.md`,
  `docs/internal/extension-distribution.md`).
- **Weights are never bundled.** Each extension pins its model files —
  Hugging Face revision plus every file's size and SHA-256 in
  `models.lock.json` — and `gufo model install` downloads exactly those
  files (`docs/install.md`, `docs/writing-extensions.md`). Weight licenses
  are tracked per model and stated in the README table; an extension author
  must "document weight licenses, don't bundle weights you may not
  redistribute."
- **Each model owns its evidence.** Every model carries public docs
  (`docs/models/<model>.md`, ≤120 lines) and internal `BENCHMARKS.md`,
  `QUALITY.md`, and `EXPERIMENTS.md` under `docs/internal/models/<model>/`.
  The Qwen3.8 27B quality file is representative: dated entries, exact match
  counts (e.g. greedy DFlash2 vs isolated AR on 160 measured requests across
  Q4/Q8 and concurrency 1–8), named unqualified areas ("original-target and
  GGUF-conversion parity remain unqualified"), and at least one result
  explicitly labelled **inconclusive** with its cause "not established."
  Failed and unresolved results stay in the file; they are not edited away.

## 4. The continuation cache — the heart of the engine

Gufo's cache is a **checkpoint cache for hybrid models**, designed for
coding-agent workloads (`docs/cache.md`; `docs/internal/cache.md`; blog
"How Gufo caches a hybrid model"). The design follows from one fact: the
models Gufo serves are hybrids — attention layers leave append-only KV rows,
but Gated DeltaNet recurrent layers keep a fixed-size state that describes
one exact position and **cannot be wound back**. So Gufo cannot do
llama.cpp-style prefix truncation; instead it saves **checkpoints**: frozen
copies of the recurrent state at exact token depths, plus references to the
KV rows up to that depth.

Key mechanics, all from the project's own documents:

- A new request resumes from the **deepest checkpoint whose tokens are an
  exact prefix** of the new prompt and prefills only the remainder. Editing
  a middle message falls back to the last checkpoint before the edit — the
  blog works the example: an edit at token 7,001 with checkpoints every
  2,048 restarts at 6,144 and recomputes 856 unchanged tokens.
- Rows are stored in fixed-size **chunks** (256 rows for Flash-Next) that
  checkpoints reference rather than own, so six checkpoints over a
  95,434-token conversation cost 3.43 GB instead of 12.4 GB of full copies.
- Chunks are shared **by provenance, not by content**: the same tokens
  computed by different prefill shapes or batch compositions can differ in
  the last bits, and mixing state from one computation with rows from
  another would continue from a state no execution ever produced. A restore
  hands over the original bytes with their provenance; two cold prefills of
  the same text never share.
- The cache **learns divergence boundaries**: when a request's shared prefix
  extends ≥512 tokens past its restore point, the cache captures a *learned
  checkpoint* exactly at the divergence — built for the parent-agent /
  subagent pattern, where many conversations share a system prompt and
  diverge at the same token. Learned checkpoints are written to disk without
  the usual spacing rule so the boundary survives restarts.
- Two tiers: RAM (default budget = half the RAM free at model load, capped
  at 32 GiB, always leaving 4 GiB for the system) and an optional disk tier
  (off by default, 8 GiB default cap, survives restarts; one server owns a
  directory — a second server pointed at it fails at startup). Eviction
  ranks by usefulness, detailed in `docs/internal/cache.md`.
- Measured results published in `docs/cache.md` (Oct 2026, Strix Halo):
  Qwen3.8 27B with a 101,545-token prompt — 280.4 s from scratch, **2.4 s
  reused**; Flash-Next at 203,047 tokens — 184.4 s → **0.7 s**. Restoring a
  24,866-token prompt from disk after a restart took 1.8 s vs ~50 s.
- Per-request controls on the chat/responses/completions endpoints:
  `cache_prompt: false` (don't reuse) and `cache_persist: false` (RAM only).
  Reuse is broken by changing tools, system prompt, response schema, or
  earlier images — sampling settings do not affect it. Observability:
  `timings.cache_n` in responses and a Prometheus counter.

The cache is mid-redesign by open process: `docs/internal/design/
cache-redesign/RFC.md` is a full public-in-repo RFC (context, problem
statement, five evaluated solutions including llama.cpp-like, SGLang-like
and vLLM-like approaches, a comparison table, an acceptance contract, and a
per-model capacity matrix required before implementation).

## 5. Speculative decoding and speed machinery

- **Native MTP and DFlash2.** Flash-Next uses multi-token prediction; the
  27B uses a DFlash2 draft model (`Qwen3.8-27B-DFlash2-Q4_K_M.gguf`,
  installed alongside the target by `gufo model install qwen27-q4`). The
  quality contract is strict: speculative output must equal autoregressive
  output — greedy DFlash2 is checked token-for-token against isolated AR
  across depths 0–128K and concurrency 1–8 (`docs/internal/models/
  qwen3.8-27b/QUALITY.md`), and the benchmark skill requires reporting
  acceptance, correctness, and end-to-end speed as separate numbers, with
  repetitive-corpus peaks labelled so they are "not mistaken for typical."
- **Per-model kernels.** Each model owns hand-tuned HIP kernels under its
  own directory; kernel work follows the shipped `optimize-kernel` agent
  skill (dossier 02). Measured on-device peaks, not spec sheets, govern:
  the skill records ~240 GB/s large-buffer controls and warns that the
  32 MiB MALL cache can make small reused matrices look "unrealistically
  fast" unless weights are rotated beyond cache capacity.
- **The NPU is a real target.** EmbeddingGemma 2, Qwen3-ASR, and Qwen3-TTS
  run on the XDNA NPU via AMD's IRON toolchain (MLIR-AIE); the NPU GEMM core
  is adapted from Xilinx's mlir-aie (credited in `THIRD_PARTY_NOTICES.md`).
  `docs/internal/npu.md` and the root `AGENTS.md` carry NPU-specific rules
  (keep repeated runtime work inside IRON `range_` loops; time cold builds).
- **Published speed shape** (from `docs/benchmarks.md` method, numbers in
  each model's `BENCHMARKS.md`): pp2048 / tg128 through the HTTP server,
  thinking off, greedy, on release builds, with the same workload run on the
  model's reference project (llama.cpp for Qwen, antirez/ds4 for DeepSeek)
  on the same machine. Fork-circulated figures (e.g. ~650 tok/s prefill,
  ~70 tok/s decode for the 27B Q4) are consistent in shape with this method
  but are **not** cited here as upstream numbers; the per-model tables in
  the tree are the authoritative source.

## 6. The extension architecture — "bring your own model"

Since late 2026 every model is an **extension**: one directory holding
sources, kernels, tests, and a manifest, wired in by the build with no edits
to shared files (`docs/extensions.md`, `docs/writing-extensions.md`,
`docs/internal/extension-distribution.md`, blog "Bring your own model").

- **The boundary is the step.** Gufo (the core) owns HTTP/OpenAI semantics,
  scheduling, cache retention, memory budgets, diagnostics, and the test
  harness; it decides when a prefill/decode step runs and which requests
  share it. The extension owns everything inside the step: execution,
  tokenization, chat templates, tool-call syntax, speculative decoding,
  input preprocessing, and its part of cached-state identity.
- **A provider** is one implementation of one capability (text, embeddings,
  ASR, TTS, image, video, decision). It brings an ID (e.g. `flash-next-q4`),
  artifact keys (e.g. `gguf:qwen4exp`), a cheap metadata-only **probe** (no
  GPU, no weight loading; first "yes" in registry order wins; no yes is a
  hard error), and a factory.
- **Two manifests:** `extension.json` (facts — providers, keys, options,
  targets, model pins; readable by CMake, Nix, CI, and the Python test
  harness without compiling) and `extension.cmake` (build logic). The build
  generates a registry source file and a constants header so code and
  manifest cannot drift.
- **Compiled in, not loaded** — the blog compares four designs (dlopen
  plugins, worker processes, models-as-data, build-time source extensions)
  and chose the last: same compiler, ROCm, and flags as the core; statically
  linked; the boundary costs one call per step. Loadable **modules** also
  exist but are explicitly **experimental** (Nov 2026): a module works only
  with the exact build it was compiled for (build identity = hash of API
  headers, compilers, ROCm, flags, arch, build type, sanitizers) and is
  skipped as `needs update` after a Gufo upgrade until rebuilt.
- **The public surface** is the headers under `include/gufo/ext/` backed by
  the single library `gufo_ext_runtime`; shared GPU building blocks live in
  `include/gufo/ext/experimental/` with no compatibility promise. The
  boundary is enforced mechanically in CI (link-graph and isolation gates;
  dossier 03).
- **API versioning:** the extension API is series **0.3** at this HEAD
  (`api-series.json`: major 0, minor 3); the revision counts immutable
  change records under `include/gufo/ext/changes/<major>.<minor>/`.
  Pre-1.0, a minor may break source compatibility; a revision is additive
  only; compatibility means *rebuild from source*, never ABI. API 1.0 is
  gated by published RFC criteria (measured text surface, an external
  pilot, a pinned external compatibility fixture, five additive features, a
  real 60-day stability period) — "no 1.0 claim is made today"
  (`docs/internal/releasing.md`).
- **Four support states** (`docs/internal/extension-distribution.md`):
  **Core** (in-tree, in `extensions.lock`, named maintainer, all repo
  gates), **Reviewed community** (out-of-tree, registry-listed after a
  maintainer's source review at an exact commit), **Community** (author's
  own repo, conformance + documented limits, never a Gufo release gate),
  **Abandoned** (last passing revision and open failures kept visible; lock
  removal is a reviewed release decision). "A registry entry promises
  reviewed source, not quality."

## 7. Serving surface

One binary, many commands (`docs/cli.md`, `docs/server.md`): `gufo chat`,
`prompt`, `serve` (llm/tts/asr/embedding/image/video), `transcribe`,
`bench`, `diagnose`, `model` (list/install/update/remove), `extension`
(list/install/update/remove). The server speaks OpenAI Chat Completions
(streaming, images, function tools), the OpenAI Responses API, and the
Anthropic Messages API; `docs/server.md` also documents llama-swap
compatibility and an **Exposure** section — Gufo has **no authentication**;
remote exposure requires a reverse proxy with TLS and access control
(`docs/internal/extension-distribution.md` hardening notes). The server
binds 127.0.0.1 by default.

## 8. Reference projects and credited ancestry

Gufo is explicit about standing on other work (`docs/reference-projects.md`,
`NOTICE`, `THIRD_PARTY_NOTICES.md`):

- **llama.cpp / ggml** — compact serving design, GGUF, CPU/GPU correctness
  paths; adapted quantization, attention, and model-private HIP kernels
  pinned to exact upstream commits.
- **Three Strix Halo llama.cpp forks** (LaurentZuijdwijk, Nathan Wilson,
  gaetan-puleo) — platform optimizations; Wilson's copyright notice is
  retained in `licenses/strix-halo-llamacpp.txt`.
- **vLLM** — continuous batching and paged request scheduling ideas.
- **hipEngine** — torch-free HIP execution and native speculative cycles.
- **ds4** (antirez) — DeepSeek V4 Flash: MoE scheduling, DSpark; adapted
  loader/tokenizer/sessions/kernels, plus a GB10/GX10 fork's paired MoE
  launch code.
- **audio.cpp** — speech recognition and synthesis models.
- **h3.c** (antirez) and its **ccv** ancestry for MiniMax H3.
- **An individual's fork contribution** — Flash-Next GDN row reuse and an
  SSM stride optimization adapted from `mikealanni/gufo` at a named commit,
  credited in both `NOTICE` and `THIRD_PARTY_NOTICES.md`. This is the
  project's own proof that outside work gets absorbed *with credit*.
- **Lemonade** (AMD's local-AI server) lists Gufo as a supported backend
  (gufo.blog homepage), and the org keeps a fork of it.

## 9. The RDMA community fork — two machines

The one community project the project itself names (README.md, homepage):
**Gufo RDMA** (`neuhaus/gufo`, created 2026-09-24), a fork adding tensor
parallelism over RDMA (InfiniBand, RoCE v2, or USB4/Thunderbolt) so two
Strix Halo systems run one model together; Flash-Next is the only
multi-host model so far; it is an optional build
(`-DGUFO_ENABLE_TP2_RDMA=ON`, needs libibverbs) and is **not merged** into
upstream. Its existence matters socially: the project's answer to "my idea
doesn't fit the one-machine principle" is a named, linked, community fork —
not a rejection.

## 10. The organization around the repo

`gufo-org` (created 2026-08-26, 21 followers) holds eight public repos: the
engine; **toolboxes** (the OCI images — "Gufo OCI Images for AMD Strix
Halo", 25 stars; also the release-publishing machinery); **website**
(gufo.blog source); **nixpkgs** (their Nix packages fork); **gufo-extension**
(the registry); **lfm3-gufo-extension** (the worked community-extension
example: LFM3 text+ASR+TTS+decision providers on one backbone); **hrx-system**
("HRX: Hip Runtime Extended", a HIP-runtime project with an in-repo migration
doc, `docs/internal/hrx-migration.md`); and the **lemonade** fork. The
engine repo's work is concentrated: of 63 contributors, two authors
(francescobozzo 368, fedeizzo 284 contributions) account for the large
majority, followed by jabata (61) and a release bot (40) — a small,
maintainer-led project, not a foundation.

## Sources

- Tree at `800ce328`: `README.md`; `docs/cache.md`, `docs/benchmarks.md`,
  `docs/extensions.md`, `docs/writing-extensions.md`, `docs/install.md`,
  `docs/cli.md`, `docs/server.md`, `docs/versions.md`,
  `docs/reference-projects.md`, `docs/extension-api.md`;
  `docs/internal/development.md`, `docs/internal/extension-distribution.md`,
  `docs/internal/releasing.md`, `docs/internal/models/qwen3.8-27b/QUALITY.md`,
  `docs/internal/design/cache-redesign/RFC.md`; `NOTICE`;
  `THIRD_PARTY_NOTICES.md`; `extensions.lock`; `api-series.json`;
  `version.txt`.
- gufo.blog: homepage; "Why does Gufo have a blog?" (2026-10-16); "Bring
  your own model: how Gufo extensions work" (Nov 2026); "How Gufo caches a
  hybrid model" (Nov 2026).
- GitHub API, 2026-11-15: repo, org, contributors, releases, search counts.
