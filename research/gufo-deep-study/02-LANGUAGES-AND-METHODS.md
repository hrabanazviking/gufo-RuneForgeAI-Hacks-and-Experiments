# 02 — Languages and Methods: How Gufo Is Written, Built, Tested, and Measured

Sources: upstream tree at `800ce328`, measured with `git ls-files` and the
GitHub languages API; `docs/internal/development.md`,
`docs/internal/testing.md`, `docs/internal/benchmarks.md`,
`docs/internal/performance.md`, `docs/internal/ci.md`, the six `AGENTS.md`
files, `.agents/skills/`. See `00-INDEX.md` for method.

## 1. The language map (measured)

GitHub's language byte counts for the tree at study time (total ≈19.7 MB of
counted source):

| Language | Bytes | Share | Role |
| --- | --- | --- | --- |
| C++ | 14,379,438 | ~73% | The engine: core, serving, models, kernels' host side |
| Python | 2,837,432 | ~14% | CI checks, tools, functional test harness, benchmark drivers |
| HIP | 2,184,748 | ~11% | GPU kernels (589 `.cpp` + 116 `.hip` files in tree counts) |
| CMake | 306,835 | ~2% | Build definition everywhere |
| Rust | 190,148 | ~1% | Bounded components behind a C ABI (section 2) |
| Nix | 113,595 | <1% | Toolchain, packages, checks (`.devops/nix`, `flake.nix` 34 KB) |
| C | 57,455 | <1% | Vendored/adapted pieces (e.g. h3 ancestry) |
| Jinja | 13,969 | — | Reference chat templates |
| Shell | 7,445 | — | Small scripts |
| TypeScript | 1,674 | — | Marginal (tooling) |

Tree file counts agree with the picture: 2,229 tracked files — 589 `.cpp`,
496 `.hpp`, 251 `.py`, 218 `.json` (manifests, fixtures, lock files),
195 `.md`, 116 `.hip`, 45 `.h`, 24 `.cmake`, 23 `.nix`, 21 `.rs`,
11 `.toml`, 10 `.sh`, 9 workflow `.yml`. Tests are half the tree by bulk:
`tests/` is ~50 MB against `src/`'s ~15 MB — the project's own `cloc`
command in `docs/internal/benchmarks.md` counts tracked source including
HIP translation units, and the test tree mirrors `src/` directory for
directory (`tests/{benchmarks,cache,cli,core,diagnostics,extensions,
families,fixtures,functional,kernels,models,quality,sched,support,testing,
tools}`).

## 2. C++ — the engine language, with hard borders

- **C++20 is required** (`docs/internal/development.md`); HIP kernels build
  from the same tree. One deliberate exception: adapted llama.cpp quantized
  kernels keep their own **C++17 dialect in isolation**.
- **Ownership map** (development.md's layout table): `src/cli` (commands,
  terminal, HTTP adapters), `src/core` (GGUF loading, sampling,
  quantization, HIP helpers, diagnostics), `src/cache` (the continuation
  cache), `src/sched` (text scheduling policy — no serving or model code),
  `src/ext` (extension runtime), `src/models/<model>`, `src/families/
  <family>`, `src/eval`, `src/testing`. The top of the graph is
  `gufo_serving` + `gufo_http`; nothing under `gufo_ext_runtime` may include
  `src/cli/**` or link either — enforced by CI gates (dossier 03).
- **Platform quarantine rule** (root `AGENTS.md`): Windows-specific code
  lives only in leaf modules under `src/core/platform/`, one leaf per OS
  facility; no `windows.h` includes and no `_WIN32` conditionals outside
  that directory and vendored code; POSIX is never emulated with macros.
- **One name per behavior** (root `AGENTS.md`): each behavior gets one
  canonical long option and one backend name — no aliases.
- **Family/model layering:** a family library (e.g. `src/families/qwen`)
  declares its libraries in `library.json` files; the dependency graph must
  be acyclic, a family may use `gufo_core` plus declared dependencies only,
  never `src/models/**` headers, and `src/core` never includes family
  headers. Declared-but-unused and used-but-undeclared dependencies both
  fail the build's graph check (`src/families/qwen/AGENTS.md`).

## 3. Rust — a small, fenced enclave

Rust is ~1% of the tree and its charter is the strictest document in the
repo (`src/core/rust/AGENTS.md`, read in full for this study):

- **What Rust may do:** bounded byte parsing/conversion, or state kept
  behind an opaque handle. **What stays C++:** HIP and kernels, model
  runtimes, the cache (including durability), scheduling, HTTP loops and
  handlers, and the extension API's types.
- **Process rule:** proposing a *new* Rust component starts in **Discussion
  #864** before any code — the one place the project routes design talk to
  GitHub Discussions (discussions are enabled on the repo).
- **Structure:** one crate per component under `src/core/<name>`, registered
  in the root Cargo workspace (resolver "3", edition 2024, `publish =
  false`, MIT), linked through the single static library `gufo-rust`; each
  crate ships a C header in `include/gufo/<name>.h` using C types only,
  mirroring its `#[repr(C)]` types. The nine workspace members at this HEAD:
  `ffi`, `rust` (umbrella), `audio_decode`, `base64`, `http`, `png_decode`,
  `resample`, `wav_decode`, `websocket`. The 0.34.0 changelog shows the
  migration in motion: audio decoding for EmbeddingGemma 2 moved to Rust
  (dropping libsndfile and soxr), and WebSocket frame parsing + base64 moved
  to Rust.
- **Safety discipline:** crate roots carry `#![deny(unsafe_code)]` and
  `#![deny(clippy::undocumented_unsafe_blocks)]` (`forbid` only without a C
  boundary); every exported function runs under `gufo_ffi::guard`, which
  requires unwinding — a panic becomes an internal-failure value, partial
  outputs are discarded, and handles stay safe to free. Null pointers are
  allowed only at length 0. C++ never frees Rust allocations. Client-input
  errors (400-class) are distinguished from internal failures (500-class).
- **The port-proof method** (also `docs/internal/testing.md`): a component
  is ported only with a **frozen independent decoder** as oracle, generated
  test grids, and deterministic mutations; every behavioral difference must
  be explained, and unknown input must fail. Named examples in testing.md:
  `png_decode_test` (color types, depths, Adam7, EXIF; intentional
  differences recorded — e.g. the Rust decoder accepts missing Adler
  trailers, rejects bad IEND CRCs), `wav_decode_test`, `audio_decode_test`
  (bit-for-bit against Symphonia's PCM decoder; resampler passband error
  <1e-4), `http_request_test` (byte-at-a-time vs whole-buffer heads),
  `multipart_test` (against **frozen copies of the three 0.33.0 parsers**
  kept in `tests/cli/multipart_reference.cpp`, with form fixtures captured
  from curl, Python requests, Node.js, and Go). After a port ships, the
  frozen decoder and comparison loops are *replaced* by expected-result
  tests — testing.md records that the frozen C++ decoders were retired
  after their ports shipped in v0.34.0 or earlier.
- **Dependency discipline for crates:** pin exactly (`=x.y.z`), disable
  default features, prefer std-only; every new crate adds its license to
  `licenses/rust.txt`, a row to `THIRD_PARTY_NOTICES.md`, and its name to
  `tools/ci/check-dependencies.py`.
- **Toolchain:** Rust **1.88.0** pinned in `rust-toolchain.toml` (minimal
  profile + rustfmt + clippy). The gates: `cargo fmt --all --check`,
  `cargo clippy --workspace --locked --offline --all-targets -- -D
  warnings`, `cargo test --workspace --locked --offline`, and
  `nix build .#checks.x86_64-linux.rust`. CMake maps Debug → Cargo dev
  profile and RelWithDebInfo → the optimized profile with full debug info;
  the C++ sanitizer preset does not instrument the Rust library. Windows CI
  builds the C++ callers but does not run Rust tests.
- **Behavior changes to a port** need a `!` breaking mark and a list in the
  PR description; timing is measured against main with the same toolchain
  and workload.

## 4. HIP and kernels

- Kernels are **per-model property**: model code, tests, tools, and
  numerical contracts stay with their model (root `AGENTS.md`); the 27B's
  kernel compile options are bound per-source to its target directory and
  must move with the kernels unchanged (`src/models/qwen/AGENTS.md`).
- Kernel work follows the shipped skill `.agents/skills/optimize-kernel/
  SKILL.md` (14 KB): keep baseline and candidate binaries; one affected
  shape plus one control; pp2048/tg128 for retained results; profile with
  `tools/prof/prof.py` comparing stage totals, launch counts, GPU-busy vs
  wall span; warm batch shapes before calibrating (lazy allocations caused
  100 ms stalls); a microbenchmark gain must survive the full inference
  path; **the winner becomes the default** — rejected routes and dead code
  are deleted, no environment switches kept to preserve experiments; each
  experiment leaves one concise retained/rejected row in the model's
  `EXPERIMENTS.md`, speeds in `BENCHMARKS.md`, quality evidence in
  `QUALITY.md`.
- Hardware truths recorded in the skill: measure `tools/bench/
  gfx1151_peak.hip`, not spec sheets (large-buffer controls ~240 GB/s);
  beware the 32 MiB MALL cache flattering small reused matrices; GEMV
  guidance (coalesced packed loads, LDS staging, fused QKV/gate-up,
  preserved accumulation order, fusion vs VGPR pressure).
- `tools/ci/check-kernel-resources.py` + `kernel-resources.json` gate
  kernel resource usage in CI.

## 5. Python — the tooling and harness language

Python never ships in the binary; it runs the project's machinery:
seventeen CI checkers in `tools/ci/` (format, docs, dependencies, extension
API, extension isolation, target graph, PR title, Rust workspace,
kernel resources, infrastructure generation, artifact handling); the
functional test harness in `tests/functional/` (Python runners that start
isolated loopback servers and check real HTTP responses — including
`pi_agent.py`, the replay harness for coding-agent loops named in the root
`AGENTS.md`: "for reported coding-agent loops replay with
`tests/functional/pi_agent.py` and retain sessions"); benchmark drivers
(`tools/bench/model-bench.py`, `tools/serving/gufo-serving-bench.py`,
`tools/bench/speculative-corpus.py`); the model file locker
(`tools/models/lock.py`); and a Python mirror of the Qwen control-token
catalogue (`tools/gufo/control_tokens.py`) that must stay identical to the
C++ catalogue (`src/families/qwen/AGENTS.md`).

## 6. Toolchains and build methods

**The Nix flake is the reference toolchain** (root `AGENTS.md`: "Nix
supplies the pinned toolchain; CMake owns flags, dependencies, installation
and generated build files"). Source builds use **GCC 16.2 + ROCm 10.1.0**
(`docs/install.md`); published numbers use the Nix toolchain, and the doc
warns that different compilers or math libraries "can change results
slightly." The Nix build also applies a ROCm runtime patch
(`.devops/nix/patches/rocr-fixed-cwsr-rocm10.patch`) that keeps GPU queues
resident under memory pressure on Strix Halo — install.md tells non-Nix
builders to apply it to their own ROCm for the same behavior.

Flake outputs (from `flake.nix` structure and the docs): the default package
(dev build, all discovered extensions), `.#release` (lock-mode, no
tests/tools), `.#sdk` / `.#release-sdk` (extension module toolchains),
`.#checks.x86_64-linux.*` (including `.rust`), `lib.withExtensionModules`,
the dev shell (gdb, git, **jj**, ripgrep, radeontop, ccache, the IRON/NPU
toolchain), and pinned **reference packages** excluded from the shipped
product: `.#llama-cpp-reference`, `.#llama-cpp-mtp-reference`,
`.#ds4-reference`. Cachix (`gufo.cachix.org`) serves the project's binary
cache. One workflow law with teeth: **flakes see only tracked files** — new
files must be staged in git before any Nix build or check.

**CMake presets** (`CMakePresets.json`; `docs/internal/development.md`):
configure presets `release` (RelWithDebInfo, HIP, no tests/tools),
`gpu-test` (RelWithDebInfo + assertions, HIP + tests + tools), `cpu-test`
(host-only), `cpu-sanitizer` (Debug + ASan/UBSan), plus `windows-base`,
`windows-cpu-test`, `windows-release`; build preset `pr`; test presets
`gpu-fast`, `gpu-full`, `deepseek-gpu`, `qwen-gpu-kernel-oracle`. Key
options: `ENGINE_ENABLE_HIP` (default ON, gfx1151 only), `BUILD_TESTING`
(OFF), `GUFO_BUILD_TOOLS` (OFF), warnings ON, sanitizers OFF,
`GUFO_EXTENSIONS_FROM_LOCK` for lock-mode builds. The shipped configuration
is RelWithDebInfo — the Cargo workspace mirrors this with a `relwithdebinfo`
profile (full debug info) and a `checked` profile (assertions + overflow
checks) used when `BUILD_TESTING=ON`; **production binaries keep assertions
off**, and testing.md warns that performance must be qualified with a
`BUILD_TESTING=OFF` artifact because test-preset binaries keep assertions
inside the serving sources.

**Windows** uses vcpkg (`vcpkg.json`, baseline pinned, curl overridden to
8.23.0): ICU, curl, OpenSSL, libpng, libjpeg-turbo, libwebp, opus, FFmpeg
(trimmed features), pkgconf. `BUILD-WINDOWS.md` documents the self-build;
release ZIPs are verified with only the bundled runtime on PATH.

**Distribution builds** (details in dossier 03): GitHub releases carry
source + a **Debian 13 package** (`gufo_<version>-1_amd64.deb`, built with
AMD's ROCm packages, verified in a fresh container) + a Windows ZIP; OCI
images come from the `toolboxes` repo; Nix users install
`github:gufo-org/gufo#release`.

**Host requirements** (`docs/install.md`): Linux **6.18.4+** and
linux-firmware **20260110+** as of Nov 2026; the user in `video` and
`render` groups; devices `/dev/kfd`, `/dev/dri/renderD*`, `/dev/accel/
accel0` (NPU, amdxdna driver). XRT has no distro package — it is built from
`amd/xdna-driver` into `/opt/xilinx/xrt`; only `lib/gufo/libgufo_npu_xrt.so`
links it, loaded on first NPU use, so Gufo starts and runs on GPU without
XRT. A standing warning: **heavy GPU and NPU work at the same time can hang
some Strix Halo hosts until power-cycled** (upstream driver issue
amd/xdna-driver#1605). The NPU also falls out of runtime suspend: the first
request after 5 s idle costs ~110 ms.

## 7. Testing method

The doctrine is one sentence (`docs/internal/testing.md`): "Run the
smallest check that covers the change; correctness and model-owned quality
limits must pass before performance results count." Around it:

- **Hosted CI** (`nix flake check` on Ubuntu, 25-minute limit): formatting,
  docs checks, dependency inventory, server-command checks, the CPU
  contract suite. It does **not** build ROCm, download weights, or run model
  oracles — GPU checks run locally or on the project's own **Devlab** Strix
  Halo machines (dossier 03).
- **CTest labels** classify tests (`cpu`, model/subsystem, cost labels like
  `slow`, `external-model`); cheap host contracts join `gufo_pr_targets`
  only if they belong in every PR.
- **Skips are honest:** "A missing-model skip is not a quality pass" (root
  `AGENTS.md`); skips stay visible in output; hosted flake check explicitly
  excludes the static-analysis check, three H3 qualification packages, and
  six `h3-qualification` CTest suites, which run only when invoked.
- **The matched-token method** for numerical work (testing.md) — the same
  discipline as teacher-forcing: tokenize once, feed teacher and candidate
  the same predetermined history, compare full next-token distributions at
  each position *before* appending; metrics are non-finite counts,
  normalized-logit error, KL divergence, teacher-token NLL/perplexity,
  top-1 agreement, top-k overlap. On a discrepancy, capture the earliest
  changed boundary (embedding, normalization, attention, recurrent state,
  routed expert, layer output, LM head), preserve the failing input, and
  add a focused reproducer before fixing. **"Do not loosen tolerances or
  silently replace goldens to admit a change."** Golden artifacts record
  immutable model and oracle revisions, file hashes, tokenizer/template
  identity, prompt/token-stream hashes, dtypes, parameters, and schema
  version; large tensor/logit dumps stay outside Git.
- **Reference honesty:** prefer hand-checkable analytic fixtures or the
  source checkpoint in a pinned official runtime. "A promoted Gufo build is
  a regression reference; agreement with it alone does not establish
  upstream correctness." Checkpoint storage type is recorded separately
  from compute/accumulation precision; unchanged-arithmetic refactors must
  retain exact boundaries; reassociated kernels need declared numerical
  limits plus model-level checks; quantization is judged against the
  full-quality teacher.
- **Functional suites** (`tests/functional/README.md`): isolated loopback
  production servers, real HTTP. Named contract examples: ASR English WER
  ≤ 0.15 with exact greedy replay and malformed-WAV recovery; image —
  OpenAI SDK generation must equal the sdapi `txt2img` output **pixel for
  pixel** and replay identically; embedding smoke vs full suites with
  independent reference vectors. The text runner replays coding-agent
  sessions (`pi_agent.py`, `agent_long.py`, `agent_catalog.py`) and a large
  family of cache suites (`cache_edits.py`, `cache_persist.py`,
  `cache_shared_prefix.py`, `cache_disk_faults*`, …) — the cache is tested
  as a product surface, not an implementation detail.

## 8. Benchmarking method

`docs/benchmarks.md` (public) + `docs/internal/benchmarks.md`:

- Every published number comes from a **release-mode build on Strix Halo
  128 GB**, dated. Workloads: **pp** = prompt processing on a 2,048-token
  prompt; **tg** = decode of 128 generated tokens, thinking off, greedy;
  concurrency rows sum decode across simultaneous requests; depth rows
  start from a long conversation already in context.
- Measurements go **through the HTTP server as a client would see them**,
  and the same workload is repeated on the model's reference project
  (llama.cpp / ds4) on the same machine; a comparison the reference cannot
  run is recorded **N/A**; unfinished is **TODO**. Numbers are never
  published without the reference column.
- **Timing law** (root `AGENTS.md`): correctness and expected prefill/cache
  work are strict; timings are mandatory per request and per phase at 5%
  and 10 ms, and are **never averaged across requests**; run once,
  investigate flags, compare against main or a PR only for affected
  histories; fix confirmed regressions before publishing; noisy evidence
  "stays visibly inconclusive and unqualified — do not widen margins."
- The shipped `benchmark-model` agent skill (30 KB) operationalizes this:
  establish model/paths/time budget from the conversation first; prefer one
  warmed sample per point and repeat only to investigate a concrete
  discrepancy; record the ACPI platform profile (Balanced vs Performance
  "differ materially with identical binaries") and starting CPU/GPU
  temperatures; drop page cache properly for cold runs (privileged drop or
  `POSIX_FADV_DONTNEED` on every target/sidecar, verified with `mincore`);
  never silently compare a native timing scope with whole-request HTTP wall
  time.
- Serving benchmarks keep distinct numbers distinct: server-stage
  prefill/decode throughput, scheduler/client TTFT, token ITL, whole-request
  latency, aggregate concurrency — "whole-request throughput is not a
  substitute for decode timings." Reports exclude endpoint hosts, prompts,
  generated text, model paths, raw token IDs, and timestamps; the canonical
  machine fingerprint excludes hostnames, usernames, secrets, and private
  paths.
- Retention: checked-in JSON keeps fixtures, provenance, calibration, and
  bounded summaries; raw samples, profiler traces, tuning databases, and
  full-logit captures stay in ignored `artifacts/` — except independent
  reference data a maintained correctness test needs.

## 9. Formatting, linting, and static analysis

- **C++:** `.clang-format` — Google style, C++20, 2-space indent, **80
  columns**, includes regrouped and sorted. The pre-commit gate is a single
  documented command (`nix shell --inputs-from . nixpkgs#clang-tools -c
  python3 tools/ci/check-format.py`). `.clang-tidy` runs a deliberately
  narrow correctness set (clang-analyzer + named bugprone checks) with
  `WarningsAsErrors: '*'` over `src/`; the broader style/performance audit
  is an explicit `static-analysis` check, not hosted CI — the file's own
  comment: "Block on correctness defects; the broader style/performance
  audit is opt-in."
- **Rust:** rustfmt + clippy at `-D warnings`, in the pinned toolchain.
- **Docs:** `tools/ci/check-docs.py` enforces the documentation constitution
  (dossier 04): title/summary shape, index membership, line budgets, the
  filler-word ban list, no issue numbers in public pages, figure rules.
- **Everything else has a checker:** dependencies, extension API records,
  extension isolation, target/link graph, PR title, Rust workspace,
  kernel resources — seventeen scripts in `tools/ci/`, most with their own
  tests.

## 10. Dependency discipline

- `THIRD_PARTY_NOTICES.md` is a pinned inventory: every direct dependency,
  adapted-code source, and acknowledged optimization reference with its
  relationship, SPDX license, **pinned revision**, and upstream location —
  from ROCm components and ICU down to individual Rust crates and the
  adapted kernels' exact llama.cpp commits. `licenses/` holds 25 license
  texts. CMake installs `LICENSE`, `NOTICE`, and the inventory under
  `share/licenses/gufo` with every package.
- Adding a dependency means recording it in the notices file;
  `check-dependencies.py` validates license/version/source records. The
  notices file also pins the Nixpkgs revision and warns that non-Nix builds
  "must retain the notices of the versions they actually distribute."
- Model files are dependencies too: pinned by size + SHA-256 per file
  (`models.lock.json`), fetched from Hugging Face with at most an
  `HF_TOKEN` that is "sent only to HF, never to redirect targets."

## Sources

- Tree at `800ce328`: `AGENTS.md` (root, `src/core/rust/`,
  `src/families/qwen/`, `src/models/qwen/`); `docs/internal/development.md`,
  `testing.md`, `benchmarks.md`, `performance.md`, `ci.md`, `npu.md`;
  `docs/benchmarks.md`, `docs/install.md`; `.agents/skills/benchmark-model/
  SKILL.md`, `.agents/skills/optimize-kernel/SKILL.md`; `Cargo.toml`,
  `rust-toolchain.toml`, `vcpkg.json`, `CMakePresets.json`, `flake.nix`,
  `.clang-format`, `.clang-tidy`, `THIRD_PARTY_NOTICES.md`, `licenses/`;
  `tests/functional/README.md`; `tools/ci/` listing.
- GitHub languages API + `git ls-files` counts, 2026-11-15.
