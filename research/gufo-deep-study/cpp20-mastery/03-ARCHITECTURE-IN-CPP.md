# 03 — Architecture in C++: Targets, Gates, Seams, and Walls

Sources: root `CMakeLists.txt` (target definitions and comments),
`cmake/TargetGraph.cmake`, `cmake/Checks.cmake`,
`tools/ci/check-extension-isolation.py`, `library.json` manifests,
`include/gufo/ext/` + `src/ext/`, `src/core/*/include/gufo/*.h`,
`src/core/hip/`, per-model `extension.cmake` files. Tree at `800ce328`.

## 1. The target map — architecture you can link against

Gufo's architecture is not a diagram; it is the CMake target graph.
The load-bearing targets, in dependency order:

- **`gufo_platform`** — the OS leaves (`src/core/platform/`): files,
  pages, sockets, mapped files, locks, signals. The *only* place
  `_WIN32`/`windows.h` may appear outside vendored code (root
  `AGENTS.md`; dossier 02 of the deep study). POSIX code moves into a
  leaf verbatim when it gains a Windows counterpart; per-OS splits are
  `<leaf>_posix.cpp`/`<leaf>_windows.cpp` selected in CMake.
- **`gufo_cache`** — the continuation cache as a standalone library:
  `completion, identity, ledger, checkpoint, prefix_index, slot,
  retention, disk, disk_catalog, streaming` (`src/cache/CMakeLists.txt`).
  It links only `Threads` and `gufo_platform`. **`gufo_cache_hip`** adds
  the device side (`committed_backing`, `component_cache_resources`,
  `snapshot_copy.hip`, `staging`, `transfer_pool`).
- **`gufo_sched`** — text scheduling *policy* as one translation unit
  (`policy.cpp`): "it builds without serving, model or HIP code;
  tests/sched checks that boundary" (`src/sched/CMakeLists.txt`). The
  policy is pure data-in/data-out (`Policy` over `WorkQueues`,
  `PrefillWork`, `DecodeWork` structs) — testable without a server.
- **`gufo_core`** — GGUF loading, sampling, quantization, JSON,
  diagnostics, HIP helpers; **`gufo_hip_host`** — the ROCr/HIP host
  runtime seam; **`gufo_logging`**.
- **`gufo_ext_runtime`** (+ interface targets `gufo_ext_core`,
  `gufo_ext_cache`, `gufo_ext_hip`) — the extension runtime: the
  versioned C++ interface layer through which models execute.
- **`gufo_serving`** — scheduler, runner pool, component text cache,
  inference backend (`src/cli/serve/…`), extracted from the executable
  in "RFC step 6" so the boundary is a library, not a folder.
- **`gufo_http`** — the HTTP API tier; **`gufo_llm_cli`** — bench/
  prompt/provider glue; **`gufo_compare`** (`src/testing/compare`) —
  the logit comparator used by quality tests; **`gufo_eval`**;
  **`gufo_test_support`** — test-only wrapping of HTTP/serving
  fixtures "so tests stop reaching src/cli/ directly", excluded from
  production and installation (`CMakeLists.txt:620–627`).
- **Families and models** declare themselves: each library directory
  carries a `library.json` manifest — `{schema, name, target, kind,
  purpose, depends}` — e.g. `src/families/qwen/config/library.json`
  declares `gufo_qwen_config`, kind `static`, depends `[]`, and a
  prose `purpose` that is itself a design record ("the free function
  that replaced GgufReader::ExtractModelConfig"). The manifest is the
  unit of architecture review: a new library exists when its manifest
  says what it is for and what it may touch.

## 2. The gates — architecture enforced by tests, not taste

Three mechanisms keep the graph honest, and all three are *tests*:

1. **The link-graph gate.** `cmake/TargetGraph.cmake` makes CMake
   write out every protected target's transitive link closure
   (`gufo_platform, gufo_npu, gufo_logging, gufo_hip_host, gufo_cache,
   gufo_cache_hip, gufo_core, gufo_ext_runtime, gufo_ext_core,
   gufo_ext_cache, gufo_ext_hip`), and the CTest test
   `extension_link_graph_gate` fails if any of them can reach the
   forbidden set `{gufo_serving, gufo_http}` — "nothing below the
   extension runtime may reach the serving or HTTP tiers", including
   through an intermediate library. System libraries are classified
   explicitly so a new OS dependency cannot smuggle an edge.
2. **The include-isolation ratchets.** `tools/ci/
   check-extension-isolation.py` inventories includes lexically and
   enforces one migrated boundary at a time, each named for the RFC
   card that retired it: no `src/core/**` file may include
   `src/models/**` or `src/families/**` headers (Card 06); no
   production source under models/families/cache/sched/ext or the
   public ext headers may include `src/cli/**` (Card 09, the serving
   boundary); no `src/models/**` file may include core/cache/sched
   (Card 11); family manifests must match their actual includes
   (Card 07 — declared-but-unused and used-but-undeclared both fail);
   every target must be *claimed* by a manifest (Card 08). The
   checker's own docstring states the ethic: "no baseline or exception
   silently hides current dependencies" — un-migrated layers are
   report-only until their card lands, then the ratchet closes.
3. **The boundary tests.** `tests/sched` proves `gufo_sched` links
   without serving/HIP; `tests/extensions/fixture` builds an isolated
   extension against only `gufo_ext_runtime` (the
   `ext_runtime_neutral_contracts_test` of the internal testing doc);
   `tests/support/package_boundary_test.py` checks the installed
   package's shape.

The pattern to internalize: **every architectural rule in Gufo has a
named mechanical enforcer**, and the enforcers are ordinary CTest/CI
citizens. Architecture review is reading the gate list.

## 3. The extension surface — C++ interfaces, source-versioned

The public API is **C++ class interfaces**, not a C ABI:

- Declarations live in `src/ext/*.hpp` (`text.hpp` alone is 960 lines);
  `include/gufo/ext/*.hpp` are the three-line forwarding shells
  (dossier 02). The transitive closure of what an extension may see is
  listed in `include/gufo/ext/SURFACE`.
- The interface style is the abstract-class idiom:
  `class TextModelRunner { public: virtual ~TextModelRunner() =
  default; [[nodiscard]] virtual TextRunnerDescriptor Descriptor()
  const = 0; … }` (`src/ext/text.hpp:434–`). Pure virtuals for the
  required contract; **non-pure virtuals with default bodies for
  optional capabilities** (`ToolFormat()`, `ReasoningBudgetTags()`,
  `VocabularySize() { return 0; }`), so adding a capability does not
  break existing implementers. Shared ownership crosses the boundary
  where lifetime is genuinely shared (`std::shared_ptr<const
  sampling::ConstraintVocabulary>`).
- Versioning is **source compatibility, never ABI** (root `AGENTS.md`):
  the API series lives in `include/gufo/ext/api-series.json`
  (`{major: 0, minor: 3, revision_base: 0}` at this HEAD); CMake
  derives the revision from the series plus the count of immutable
  change records under `include/gufo/ext/changes/<major>.<minor>/`;
  any SURFACE-closure change needs the `ext-api` label, a new record,
  and `check-extension-api.py --write`. Pre-1.0, a minor may break;
  revisions are additive.
- Loadable modules exist (the 0.2 change record
  `loadable-extension-modules.md`; 8 `dlopen`/`LoadLibrary` sites),
  discovered via `extension.json` + `extension.cmake` per the template
  in `examples/extension_template/` — but even loadable extensions
  compile against the same source-level interface; the module
  boundary is a build/discovery mechanism, not an ABI promise.

## 4. The Rust seam — the one true C ABI

Where a real C ABI exists, it exists for Rust (deep-study dossier 02
has the Rust-side charter; this is the C++ view):

- Each component lives at `src/core/<name>/` with a hand-maintained C
  header at `src/core/<name>/include/gufo/<name>.h` — at this HEAD:
  `audio_decode.h`, `base64.h`, `http.h`, `png_decode.h`,
  `websocket.h` (plus `wav_decode`, `resample`, and the `ffi`/`rust`
  umbrella crates in the nine-member Cargo workspace). The headers use
  C types only and mirror the Rust `#[repr(C)]` types.
- C++ callers include the C header, call functions that cannot throw
  (the Rust side runs every export under `gufo_ffi::guard`: a panic
  becomes an internal-failure value, partial outputs are discarded),
  and translate results into the C++ vocabulary — status enums and
  exceptions (dossier 04). **C++ never frees Rust allocations**;
  handles are opaque and freed through the owning side.
- The seam's shape is the general rule: at every boundary where two
  failure models meet (C ABI, HIP runtime, OS), a thin translation
  layer converts foreign error codes into the house vocabulary
  exactly once — `HIP_CHECK` for HIP, the FFI headers for Rust, the
  platform leaves for errno/Win32.

## 5. The HIP wall — host C++20 here, device code there

- Device code lives in `.hip` translation units (83 in the census
  scope) and per-model kernel directories (`src/models/<model>/
  kernels/`), compiled by the HIP language support with the
  architecture locked to `gfx1151` (`CMakeLists.txt:137–149`).
- Host code includes HIP headers only under
  `#if defined(ENGINE_ENABLE_HIP)`; `gufo_hip_host` concentrates the
  runtime linkage, and `hip_utils.hpp` shows the pattern: the whole
  header is inert when HIP is off.
- The wall is also a *dialect* wall: the two adapted kernel families
  (DeepSeek V4 Flash, Qwen3.8 Flash-Next) pin `HIP_STANDARD 17` in
  their `extension.cmake` and keep upstream macros and `extern "C"`
  blocks inside their targets (dossier 01 §5.6). Per-source kernel
  compile options are bound to the model's target directory and must
  travel with the kernels (deep-study dossier 04) — code objects must
  come out identical after a move.
- Numerical contracts live with the model (QUALITY.md per model;
  dossier 04 §5), and the host/device split respects the cache's
  needs: `gufo_cache_hip` owns device-side backing, staging, and
  snapshot copies (`snapshot_copy.hip`) behind the same status/
  exception vocabulary as the host cache.

## 6. The lesson

In Gufo, C++ architecture is not expressed in UML or in folder
conventions alone; it is expressed in **target definitions,
manifests, and gate tests that fail the build when the architecture
is violated**. The language-level choices — forwarding headers,
abstract interface classes with defaulted hooks, a single C-ABI seam,
per-target dialect fences — are all in service of that one idea: the
boundaries are real because something mechanical breaks when you
cross them.
