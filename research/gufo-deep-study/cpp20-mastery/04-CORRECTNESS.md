# 04 — Correctness: Errors, Assertions, Sanitizers, and Numbers

Sources: error-vocabulary census (method in `00-INDEX.md`),
`src/core/audio.hpp`, `src/core/hip/hip_utils.hpp`,
`src/cache/completion.hpp`, `src/cli/serve/text_generation_backend.hpp`,
root `CMakeLists.txt` (assertion blocks at lines 43–45, 298, 448–458,
613–615), `src/cache/CMakeLists.txt`, `src/sched/CMakeLists.txt`,
`CMakePresets.json`, `docs/internal/testing.md` (via deep-study
dossier 02). Tree at `800ce328`.

## 1. The dual error system

Gufo has two error vocabularies, and knowing which one a function
speaks is the first correctness skill the codebase teaches.

### 1.1 Status enums — for outcomes callers branch on

Dozens of small domain enums, all with the same shape:

```cpp
enum class AudioStatus : std::uint8_t { kUnrecognized, kMalformedHeader, … };
enum class TransferResult : std::uint8_t { … };        // src/cache/completion.hpp
enum class DiskRetireResult { kRetired, kMissing, kPinned, kBusy };  // src/cache/disk.hpp
enum class TextGenerationErrorCode : std::uint8_t { … };  // src/cli/serve/text_generation_backend.hpp
enum class RenameResult { kRenamed, kTargetExists, kFailed };  // src/core/platform/fs.hpp
enum class EmbeddingStatus { … };                      // src/ext/embeddings.hpp
enum class DeviceProbeStatus { kUsable, kPending, kLost };  // src/ext/device_probe.hpp
```

The grammar: `enum class`, usually a fixed `std::uint8_t` underlying
type when the value crosses a boundary or is stored, `k`-prefixed
enumerators, and a name that says *whose* status it is. These are
returned by value from operations whose failure is a normal,
branch-worthy outcome — a disk retire that finds the entry pinned, a
transfer that completes partially, a decode that rejects its input.
They pair with `std::optional` (771 whole-tree occurrences) for the
"succeeded or nothing" case that needs no reason.

### 1.2 Exceptions — for host-code failure

Exceptions are fully enabled (no `-fno-exceptions` anywhere in the
build) and heavily used: 2,008 `throw` tokens in production scope,
450 `try`, 503 `catch`. The distribution is a map of where failure is
exceptional rather than branchy: `src/models` 876, `src/cli` 450,
`src/core` 338, `src/cache` 189, `src/ext` 29, `src/families` 14,
`src/sched` 5 (the pure policy library barely throws — it returns
decisions), `src/eval` 9.

The thrown vocabulary is the standard hierarchy, used semantically:

| Type | Occurrences (src) | Role |
| --- | --- | --- |
| `std::invalid_argument` | 791 | contract violations by the caller — bad options, impossible sizes, zero channels |
| `std::runtime_error` | 620 | environment and load failures — files, devices, formats |
| `std::logic_error` | 204 | internal invariants detected at run time |
| `std::out_of_range` | 23 | indexed access violations |
| `std::system_error` | 21 | OS-facing failures at the platform seam |
| `std::bad_alloc` | 30 | mostly caught/rethrown context, not thrown by hand |

On top of that, components define **their own exception class when
callers need to react programmatically**, always derived from
`std::runtime_error`, always named for the component: `AudioError`
(`src/core/audio.hpp:69`), `DiskDependencyError`, `LibraryError`,
`ImageResourceError`, and per-component plain `Error` inside the
component's namespace (two instances found). Header comments state
the throws contract function by function ("Throws AudioError",
"Throws std::invalid_argument when channels is 0…").

### 1.3 The bridge — exceptions that carry their status

The two vocabularies meet in one idiom, shown complete in
`src/core/audio.hpp`: the decoder's rejection reasons are the
`AudioStatus` enum; the exception thrown for every rejection is
`AudioError`, which *carries* the status:

```cpp
class AudioError : public std::runtime_error {
public:
  explicit AudioError(AudioStatus status);
  [[nodiscard]] AudioStatus status() const noexcept { return status_; }
private:
  AudioStatus status_;
};
```

The header explains why: "`what()` describes the status in English;
callers that keep their own wording map `status()`." Machines branch
on the enum; humans read the message; control flow uses the
exception. The same pattern — value vocabulary for branching,
exception for unwinding, one type that binds them — recurs at the
FFI seam (Rust distinguishes 400-class client errors from 500-class
internal failures, deep-study dossier 02) and at the HTTP tier, where
`TextGenerationErrorCode` maps internal outcomes to API responses.

### 1.4 Foreign error codes are translated exactly once

- **HIP**: `HIP_CHECK(call)` (222 uses) evaluates the call, and on
  non-success throws `std::runtime_error` whose message is built as
  `"HIP error in " __FILE__ ":" line " (" #call "): " +
  hipGetErrorString(err)` — the macro stringizes the call and stamps
  the source location. `HIPBLAS_CHECK` (22) does the same for
  hipBLAS statuses. Adapted islands keep their own dialects:
  `GGML_ASSERT` (58) in ggml-derived code, `DS4_HIP_CHECK` (15) in
  the DS4-derived kernels.
- **Cleanup never throws**: destructors and cleanup paths use the
  `noexcept` `LogCleanupError` overloads, which print to stderr —
  "Cleanup must not throw while another GPU failure is unwinding
  the request" (`hip_utils.hpp:13`). This is the codebase's
  destructor discipline stated in one comment: unwinding paths log,
  they do not fail.
- **Boundaries that cannot throw** (the Rust C ABI) convert to
  status values on the far side and back (dossier 03 §4).

## 2. The assertion policy — a build-mode contract

Raw `assert(` is nearly absent from production code: **27 occurrences
in production scope against 4,454 in tests**. Production invariants
are expressed as exceptions (§1.2's `logic_error`/`invalid_argument`)
or as status returns — things that survive release builds. Assertions
are the *test* build's weapon, and the build system makes that
precise:

- The shipped configuration is RelWithDebInfo, which defines
  `NDEBUG` — production asserts are compiled out.
- `BUILD_TESTING=ON` adds a **global `-UNDEBUG`** (`/UNDEBUG` on MSVC)
  at `CMakeLists.txt:613–615`, under the comment "Test assertions
  remain active when model code uses production optimization." Every
  target in a test build therefore runs with live assertions at full
  optimization — the test binary tests the *same arithmetic* the
  release binary ships, with the safety net on.
- Targets defined *before* that block in the root file, or in
  subdirectories processed earlier, carry their own explicit
  `-UNDEBUG` under `BUILD_TESTING`: `gufo_cache`
  (`src/cache/CMakeLists.txt:5–8`, which also defines
  `GUFO_CACHE_TESTING`), `gufo_sched` (`src/sched/CMakeLists.txt:5–7`),
  `gufo_cache_hip` (`CMakeLists.txt:298`), `gufo_serving`
  (`CMakeLists.txt:452–458`). The `gufo_serving` comment is candid
  about the trade: the executable's own objects once carried
  production `NDEBUG` while test binaries re-compiled the sources
  with assertions; one library can only pick one, so test builds now
  assert in the `gufo` binary too — "Production (BUILD_TESTING=OFF)
  is unchanged."
- The Rust workspace mirrors the policy: CMake's `checked` Cargo
  profile (assertions + overflow checks) is used when
  `BUILD_TESTING=ON`; shipped builds leave them off (deep-study
  dossier 02 §3). And the internal testing doc's warning completes
  the contract: performance must be qualified on a
  `BUILD_TESTING=OFF` artifact, because test-preset binaries keep
  assertions inside the serving sources.

## 3. Sanitizer discipline

- One option, `GUFO_ENABLE_SANITIZERS` (default OFF), adds
  `-fsanitize=address,undefined -fno-omit-frame-pointer` to compile
  and link for GNU/Clang (`CMakeLists.txt:228–232`); the extension
  builder and SDK replicate it so extensions are instrumented
  consistently (`cmake/GufoExtension.cmake:596–599`).
- The `cpu-sanitizer` preset is the canonical run: Debug +
  `BUILD_TESTING=ON` + sanitizers on + HIP off — host memory and UB
  diagnostics on the CPU tree (`CMakePresets.json`; testing doc's
  command sequence).
- The exception that proves understanding: the two fault-injection
  libraries (`device_loss_faults`, `cache_disk_faults`) are built
  with `-fno-sanitize=all` even in sanitizer builds, because they are
  `LD_PRELOAD`ed into *uninstrumented* processes where "a sanitized
  library aborts there with 'ASan runtime does not come first'"
  (`CMakeLists.txt:644–650`).
- The C++ sanitizer preset does not instrument the Rust library; the
  Rust side runs its dev profile under the C++ sanitizer preset and
  its own gates under Nix (deep-study dossier 02).

## 4. Static correctness gates

Beyond tidy (dossier 01 §3), correctness is guarded by the checkers
that fit this codebase's risks: `check-kernel-resources.py` gates
kernel register/resource budgets; the extension-API checker gates
public-contract drift; the dependency checker gates licensing and
pinning. The through-line: a correctness property that can be
mechanized is mechanized, and the rest is carried by the header
contracts and the test style (dossier 06).

## 5. Numerical correctness — declared limits, matched tokens

Kernel and quantization work follows the rule that a numerical claim
is a *declared* claim (testing doc, via deep-study dossier 02):

- Unchanged-arithmetic refactors must retain **exact** boundaries.
- Reassociated kernels need **declared numerical limits** plus
  model-level checks; quantization is judged against the full-quality
  teacher with distribution, perplexity, and capability gates.
- The comparison method is matched-token: tokenize once, feed teacher
  and candidate the same predetermined history, compare full
  next-token distributions per position (non-finite counts,
  normalized-logit error, KL, teacher-token NLL, top-1 agreement,
  top-k overlap) — implemented for tests by `src/testing/compare/
  logit_comparator.*`. On discrepancy: capture the earliest changed
  boundary, preserve the failing input, add a focused reproducer
  before fixing. **Tolerances are never loosened and goldens never
  silently replaced to admit a change.**
- Golden artifacts record model and oracle revisions, file hashes,
  tokenizer/template identity, prompt/token-stream hashes, dtypes,
  parameters, schema version; checkpoint *storage* type is recorded
  separately from compute/accumulation precision — the distinction
  the `std::bit_cast` idiom (154 uses) serves at code level: bit
  reinterpretation is explicit, named, and testable.

## 6. The correctness worldview

Failure in Gufo is *typed, located, and priced*: typed by the dual
vocabulary (status for branching, exceptions for unwinding, one
binding type where both are needed), located by file/line-stamping
macros at foreign seams, and priced by a build system that decides —
globally, explicitly, in comments — exactly which checks are live in
which artifact. Nothing about correctness is left to a programmer
remembering to be careful.
