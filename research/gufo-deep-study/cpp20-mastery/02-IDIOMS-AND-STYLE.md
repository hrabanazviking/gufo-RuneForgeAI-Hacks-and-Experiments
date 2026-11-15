# 02 — Idioms and Style: The Visible Grammar of Gufo's C++

Sources: exemplar headers and sources read in full at `800ce328`
(`src/core/audio.hpp`, `src/core/hip/hip_utils.hpp`,
`src/cache/slot.hpp/.cpp`, `src/ext/text.hpp`,
`tests/core/admission_memory_test.cpp`), namespace and idiom censuses
(method in `00-INDEX.md`), `.clang-format`.

## 1. Naming — one system, no exceptions worth counting

| Thing | Convention | Evidence |
| --- | --- | --- |
| Namespaces | `gufo::<area>`, lowercase, nested C++17 syntax | `gufo::models::qwen38_27b`, `gufo::hip`, `gufo::server`, `gufo::cache`, `gufo::platform`, `gufo::core`, `gufo::ext`, `gufo::cli`, `gufo::diagnostics`, `gufo::sampling`, `gufo::speculative`, `gufo::npu`, `gufo::eval` (census of `namespace` lines) |
| Classes, structs, enums | PascalCase | `DecodedAudio`, `TextModelRunner`, `CommittedBackingPool` |
| Functions (free and member) | PascalCase | `DecodeAudio`, `DownmixMono`, `AdmissionFreeBytes`, `Pin`, `RunIdle` |
| Enumerators | `kPascalCase` | `AudioStatus::kUnrecognized`, `RenameResult::kRenamed`, `DeviceProbeStatus::kUsable` |
| Constants | `kPascalCase` | `kAdmissionHostMarginBytes`; test-local `kGiB`, `kMargin` |
| Local variables, parameters | snake_case | `budget_bytes`, `should_stop`, `vector_index` |
| Data members | snake_case with trailing underscore | `status_`, `worker_`, `state_` |
| Files | snake_case, `.hpp`/`.cpp` pairs | `admission_memory.hpp`, `text_generation_scheduler.cpp`; `.h` reserved for C (the Rust seam headers and vendored C) |
| Macros | SCREAMING_SNAKE with project prefix | `HIP_CHECK`, `HIPBLAS_CHECK`, `GUFO_*` |
| Include guards | `GUFO_<PATH>_<NAME>_HPP_` | `GUFO_CORE_AUDIO_HPP_`, `GUFO_CORE_HIP_HIP_UTILS_HPP_` |

Two consequences follow. First, **case carries category**: in a Gufo
file you can tell a type from a function from a constant from a member
without any declaration in sight. Second, the free-function style is
real: pure operations are namespace-scope PascalCase functions
(`DecodeAudio`, `ExtractQwenConfig` — a `library.json` purpose note
records that the free function *replaced* a `GgufReader::ExtractModelConfig`
method), and classes appear where state or an interface genuinely
exists. This is not an everything-is-an-object codebase.

## 2. Headers — guards, forwarding shells, and include discipline

- **Production headers use classic include guards**, path-derived:
  333 files under `src/` match `#ifndef GUFO_…`; 93 `src/` headers use
  `#pragma once` (concentrated in newer component subtrees). Guards are
  the house default; the guard name *is* the path, so a mis-pasted
  guard is visible in review.
- **Public headers are forwarding shells.** Every one of the 62 files
  under `include/gufo/` uses `#pragma once`, and the extension API
  headers are three lines: `#pragma once`, a blank line, and
  `#include "src/ext/text.hpp"` (`include/gufo/ext/text.hpp`). The
  public surface is a *view* over `src/` declarations — the contract
  lives in one place, the published path in another, and the
  `SURFACE` closure file plus `check-extension-api.py` police the
  boundary (dossier 03).
- **Include order is machine-enforced**: `.clang-format` sets
  `SortIncludes: CaseSensitive` with `IncludeBlocks: Regroup`. The
  exemplar shape (`src/core/audio.hpp`) is: own-header guard, then
  system headers sorted (`<cstddef>`, `<cstdint>`, `<functional>`,
  `<span>`, `<stdexcept>`, `<vector>`), then project headers. HIP
  headers, when present, sit in their own block before the standard
  ones (`recurrent_state.hpp`: `<hip/hip_bfloat16.h>`,
  `<hip/hip_runtime.h>`, blank, `<concepts>`, `<cstddef>`).
- **Include-what-you-use is cultural**: headers include the facilities
  they name (`<span>` for `std::span`, `<stdexcept>` for the exception
  base) rather than relying on transitive includes — visible in every
  exemplar header.
- Conditional compilation of HIP is by `#if defined(ENGINE_ENABLE_HIP)`
  wrapping whole header bodies (`hip_utils.hpp`), so a host-only
  translation unit sees an empty, harmless header instead of a
  configuration error.

## 3. The header as contract — comment style

The single most recognizable Gufo idiom is that **headers carry the
contract in prose**. `src/core/audio.hpp` is the type specimen:

- Every enum gets a lead comment naming its role ("Why DecodeAudio
  rejected an input"), and **every enumerator gets its own full
  contract comment** — conditions, edge cases, what the caller may
  conclude (`kTruncated`: "The data ends early, a packet fails to
  decode, or fewer frames decode than the container declares").
- Every struct field is commented with its semantics and units
  (`max_seconds{30}` — and the comment says what "longer" means).
- Every function documents its throws, its cancellation behavior, and
  its quantitative behavior, including measured performance where it
  is part of the contract ("30 s from 192 kHz to 16 kHz takes about
  10 ms on Strix Halo", in `Resample`'s comment).
- Aggregates use **in-class member initializers** so a default-constructed
  options struct is already the sane configuration
  (`AudioLimits::max_channels{8}`), which is what makes the designated-
  initializer call style safe (dossier 07).

Comments elsewhere follow the same rule the docs constitution imposes
on prose (deep-study dossier 04): plain, exact, present-tense, no
history. Code comments explain contracts and non-obvious constraints
("Cleanup must not throw while another GPU failure is unwinding the
request", `hip_utils.hpp:13`), never narrate the obvious.

## 4. Ownership — shared where sessions live, unique where models live

Whole-tree counts: `std::shared_ptr` 954, `std::unique_ptr` 733,
`std::weak_ptr` 9, `std::make_shared` 499, `std::make_unique` 248,
raw `new` 82 (whole tree, most in adapted code and tests). The split
by territory is the idiom:

| Territory | shared | unique | Reading |
| --- | --- | --- | --- |
| `src/cache` | 114 | 23 | cache state is co-owned by sessions, workers, and the disk tier — shared ownership is the model |
| `src/cli` (incl. serving) | 201 | 72 | runners and backends are shared across scheduler, HTTP, and cache handles |
| `src/core` | 114 | 61 | mixed: shared for runtime objects, unique for owned resources |
| `src/models` | 258 | 388 | model internals prefer unique ownership; shared appears at runner boundaries |
| `src/ext` | 18 | 16 | balanced at the interface layer |

Rules a reader can extract:

- **Allocation goes through `make_unique`/`make_shared`** — raw `new`
  is not a production idiom.
- **`weak_ptr` is nearly absent (9)** — cycles are avoided by design
  (owner trees and explicit state objects, e.g. the cache slot's
  `state_` shared pointer captured by its worker lambda) rather than
  broken after the fact.
- **Copy/move is declared, never assumed**: 516 `= delete` and 327
  `= default` in production scope. Resource classes delete copying;
  value types default their comparisons (30 defaulted
  `operator==`/`<=>`).
- **Views are the parameter idiom**: `std::span<const T>` for buffers,
  `std::string_view` for text, `const T&` for structs — ownership
  transfers are the marked exception (`std::unique_ptr` by value,
  `std::shared_ptr` where co-ownership is the design). The tidy gate's
  chosen checks (`bugprone-dangling-handle`, `bugprone-use-after-move`)
  exist precisely because this view-heavy style's failure modes are
  dangling views and moved-from handles.
- **RAII wraps every OS/GPU resource**: platform leaves expose classes
  like `platform::FileLock` and `ShutdownSignalGuard`
  (`src/core/platform/`), HIP host code wraps allocations and transfer
  pools (`src/core/hip/managed_alloc.hpp`, `transfer_pool.hpp`,
  `committed_backing.hpp`), and destructors on interface classes are
  explicitly `virtual ~X() = default` (`src/ext/text.hpp:46,437`).

## 5. Function-shape idioms

- **`[[nodiscard]]` is punctuation** (2,153 production occurrences):
  if a function returns a value, ignoring it is a compile error by
  default — including virtual interface methods
  (`[[nodiscard]] virtual TextRunnerDescriptor Descriptor() const = 0`).
- **Const-correctness is total** in exemplars: accessors are `const`
  and often `noexcept` (`AudioStatus status() const noexcept`),
  parameters are `const&`/`const` views, and `const_cast` is nearly
  absent (43 whole-tree).
- **Overload sets are small and semantic**; where behavior differs by
  policy, the tree prefers separate named functions or an options
  aggregate over flag parameters.
- **Options aggregates + designated initializers** are the
  configuration idiom: `PolicyOptions`, `AudioLimits`, `GpuLocalBudget`
  — filled at call sites as `GpuLocalBudget{.budget_bytes = 104 * kGiB,
  .usage_bytes = 81 * kGiB}` (visible throughout the tests), with
  in-class defaults making partial specification safe.
- **Callbacks are `std::function` at API seams** (283 whole-tree) —
  e.g. DecodeAudio's `const std::function<bool()>& should_stop` — and
  lambdas at call sites; deeper in the machinery, cancellation is a
  `std::stop_token` parameter instead (dossier 05). Virtual interfaces
  with defaulted no-op hooks handle optional capabilities
  (`virtual void SetCancellationCheck(const CancellationCheck&) {}`,
  `src/ext/text.hpp:278`).
- **Numbers are fixed-width**: `std::uint8_t` underlies status enums;
  `std::uint64_t` carries byte counts; sizes are `std::size_t`;
  `int` appears mainly at C and OS boundaries. `static_cast` (8,332)
  is the conversion idiom; `reinterpret_cast` (1,264) concentrates at
  byte/kernel boundaries; C-style casts are not the style.
- **String building** is `std::string` concatenation and
  `std::to_string` for numbers (HIP_CHECK builds its message exactly
  this way); stream formatting (`ostringstream`, 109) appears where
  structured text is assembled; there is no format library (dossier 01).

## 6. What the style adds up to

Read three Gufo headers and the grammar is unmistakable: guards named
for paths, flat `gufo::` namespaces, PascalCase operations, k-prefixed
enumerators with a contract comment each, span/string_view parameters,
`[[nodiscard]]` on everything, exceptions named per component, and
prose that states units, limits, and measured costs. The style's
purpose is the project's purpose: a reader — human or agent — should
be able to predict behavior from the header alone, because in this
codebase the header *is* the specification the tests enforce.
