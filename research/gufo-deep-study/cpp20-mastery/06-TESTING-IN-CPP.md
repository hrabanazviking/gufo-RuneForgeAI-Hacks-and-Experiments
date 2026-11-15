# 06 — Testing in C++: No Framework, Compile-Time Proofs, Oracles

Sources: `tests/core/admission_memory_test.cpp` (read in full),
`cmake/Checks.cmake`, `cmake/PlatformTests.cmake`, `tests/cache/
CMakeLists.txt`, root `CMakeLists.txt` (test registration and the
`-UNDEBUG` blocks), `tests/support/`, `src/testing/compare/`,
`docs/internal/testing.md` (via deep-study dossier 02). Tree at
`800ce328`.

## 1. The framework is: there is no framework

No GoogleTest, no Catch2, no doctest — no test-framework dependency
exists anywhere in the build. The census fact: **241 of 262 test
`.cpp` files define their own `int main()`**. A Gufo test is a
program; CTest runs it; exit status is the verdict. The harness
inside each file is a local helper in an anonymous namespace:

```cpp
namespace {
void Expect(bool condition, const char* message) {
  if (condition)
    return;
  std::cerr << message << '\n';
  std::abort();
}
}  // namespace
```

(`tests/core/admission_memory_test.cpp`.) `Expect` takes a
human-readable failure message — every assertion in the file reads as
a sentence about the contract ("without a budget HIP's free bytes
stand", "a budget under its usage adds nothing"). Failure prints the
sentence and aborts; there is no test-case registry, no fixture
class hierarchy, no macro vocabulary to learn. Shared needs are met
by a small support library instead: `gufo_test_support`
(`tests/support/test_support.cpp`, `layered_prefill_conformance.*`)
wraps HTTP and serving fixtures "so tests stop reaching src/cli/
directly", plus header helpers (`temporary_directory.hpp`,
`model_api_test_support.hpp`, `continuation_identity.hpp`).

## 2. Compile-time tests — the constexpr half of the suite

The distinctive Gufo move is how much testing happens *before*
`main()`:

- Production functions that can be `constexpr` are (dossier 01:
  4,442 `constexpr` occurrences), and tests evaluate them at compile
  time. `admission_memory_test.cpp` builds its fixtures as
  `constexpr GpuLocalBudget kRoomy{.budget_bytes = 104 * kGiB,
  .usage_bytes = 81 * kGiB}` — designated initializers again — and
  pins contract constants with `static_assert(kMargin == 5 * kGiB +
  kGiB / 2)` where `kMargin` is the production
  `kAdmissionHostMarginBytes`.
- The test's comments carry the *provenance* of its cases: the roomy
  budget is "as measured when a 262144-token Flash-Next session was
  refused on a Strix Halo" — a field incident, frozen into a
  compile-time fixture. Edge cases are the wraparound family: budget
  under usage, budget equal to usage, RAM at the margin — each with
  its Expect sentence.
- Runtime `Expect` then re-checks the same values through the
  compiled function, so a `constexpr` regression fails the build and
  a codegen/linkage regression fails the run.

This is why `assert(` counts 4,454 in tests against 27 in production:
between `static_assert`, `Expect`, and `assert`, the test tree is
where assertion lives in this codebase (and `BUILD_TESTING=ON`'s
global `-UNDEBUG` keeps every one of them live at full optimization,
dossier 04).

## 3. Registration — add_test, labels, timeouts, and the PR subset

- Tests register with plain `add_test(NAME <name> COMMAND <name>)`
  and `set_tests_properties(... PROPERTIES LABELS "cpu;cache"
  TIMEOUT 30)` — labels classify by tier and subsystem (`cpu`, `hip;
  gpu;gfx1151`, model names, `slow`, `external-model`, `quality`),
  timeouts are per-test and short (30–60 s in the cache suite).
  Model tests may register from the model's own directory through
  helper functions (`gufo_qwen3_asr_register_tests()` in the root
  CMake) — tests live with their model, like everything else.
- **The PR gate is a curated list, not the whole suite**:
  `cmake/Checks.cmake` defines `gufo_pr_targets` (~120 targets: the
  cache family, sched policy, extension runtime, the Rust-component
  caller tests, platform leaves, serving contracts) plus a
  `# BEGIN/END GENERATED MODEL PR TARGETS` section maintained by
  tooling, and the `check-pr` custom target depends on the `gufo`
  binary plus exactly those. Its header comment is the doctrine:
  "adding a model oracle must not make every PR expensive."
- Test presets then select by label for wider runs (`gpu-fast`,
  `gpu-full`, model-specific oracle presets), and hosted CI runs the
  CPU/repository selection via `nix flake check` (deep-study
  dossier 02 §7).

## 4. Oracle style — independence is the whole point

The C++ test culture's core rule (from the Qwen family rulebook,
deep-study dossier 04): **expected results must not be derived solely
from the constants they validate**. In practice:

- **Analytic fixtures**: hand-checkable inputs whose outputs are
  known by construction (the admission arithmetic above; sampling and
  dequantization tests in the PR list — `logit_sampler_test`,
  `ggml_dequant_test`, `sampling_test`).
- **Frozen independent references**: when a component is ported (the
  Rust migrations), the *previous* implementation is frozen into the
  test tree as the oracle — `tests/cli/multipart_reference.cpp` holds
  the three 0.33.0 parsers the Rust multipart port is compared
  against, with form fixtures captured from real clients (curl,
  Python requests, Node.js, Go). After a port ships and expected-
  result tests replace the comparison, the frozen oracle is retired
  — recorded, not left to rot.
- **The comparator library**: numerical model tests share
  `src/testing/compare/logit_comparator.*` (`gufo_compare`) — the
  matched-token distribution comparison of dossier 04 §5 — instead
  of each test inventing its own tolerance math.
- **Fault injection as tests**: `device_loss_faults` and
  `cache_disk_faults` are shared libraries `LD_PRELOAD`ed into real
  processes to interpose `fsync` and simulate device loss
  (`CMakeLists.txt:630–650`) — failure behavior is tested against
  the *unmodified* server binary, not a mock.
- **Functional tests** (Python-driven, dossier 02 of the deep study)
  sit above the C++ layer: real loopback servers, real HTTP,
  replayed coding-agent sessions. The C++ tests' job is contracts;
  the functional suites' job is behavior.

## 5. What a Gufo-grade test looks like — the checklist form

Distilled from the exemplars:

1. One test program per component contract, named `<component>_test`,
   with its own `main()` and a local `Expect` (or the support
   library's fixtures when HTTP/serving is involved).
2. Fixtures are `constexpr` where the code under test allows it;
   contract constants are pinned with `static_assert`.
3. Every check carries a sentence-length message stating the contract
   in the project's plain voice.
4. Cases come from the contract's edges and from field incidents,
   with provenance comments — not from the implementation's shape.
5. Expected values are independent: analytic, hand-computed, frozen
   from a prior implementation, or produced by the pinned reference
   runtime — never copied from the code under test.
6. Registration is one `add_test` + labels + a timeout; PR-gate
   membership is a deliberate addition to `cmake/Checks.cmake`, not
   a default.
7. Skips are honest: a test that cannot run (missing model, missing
   device) reports a skip that stays visible — "a missing-model skip
   is not a quality pass" (root `AGENTS.md`).

## 6. Why this style fits this codebase

A framework would give Gufo registration and reporting it already
gets from CTest, at the price of a dependency and a macro dialect.
The framework-free style keeps every test a readable program whose
failure message is a contract sentence, keeps compile-time proof a
first-class citizen (frameworks are runtime machines), and keeps the
test tree's bulk — half the repository — free of anything but the
code under test, the fixtures, and the oracles. It is the same
decision as the dialect itself (dossier 01): adopt exactly the
machinery that pays, in the open, and no more.
