# 00 — Index: The Gufo C++20 Mastery Corpus

This corpus is a measured study of one codebase's C++: the dialect of
C++20 that `gufo-org/gufo` is actually written in at
`800ce3280201e94104cfff9d310837ab6a6f3d95` (v0.34.0), studied 2026-11-15.
It is the C++ companion to the Gufo deep study banked beside it
(`research/gufo-deep-study/00–05`): that corpus describes the project;
this one dissects its language — feature by feature, idiom by idiom —
and ends with a practical manual for writing code the Gufo way.

## Reading order

- `01-THE-DIALECT.md` — the exact standard level, the compiler and
  lint law, and the feature census: what C++20 facilities the tree
  uses, how much, where — and what it conspicuously refuses.
- `02-IDIOMS-AND-STYLE.md` — the visible grammar: naming, headers,
  namespaces, ownership, view types, formatting of code and comments.
- `03-ARCHITECTURE-IN-CPP.md` — how the language carries the
  architecture: CMake targets, the link-graph and include gates, the
  extension interface surface, the Rust C-ABI seam, the HIP wall.
- `04-CORRECTNESS.md` — the error vocabulary end to end (status enums,
  typed exceptions, HIP check macros), the assertion policy, sanitizer
  discipline, and how numerical limits are declared.
- `05-CONCURRENCY-AND-MEMORY.md` — threads, cancellation, atomics and
  their memory orders, clocks, pools and arenas, cache state structures.
- `06-TESTING-IN-CPP.md` — the framework-free test style, compile-time
  tests, oracle fixtures, CTest registration and labels.
- `07-WRITING-GUFO-GRADE-CPP20.md` — the manual: deep explainers for
  each major facility as Gufo uses it, pitfalls, and checklists for a
  new component, a new test, and a public header.

## Method

Nothing here is guessed. Every count comes from a scripted census of
the tree at the HEAD above (grep-based occurrence counts over the C++
family: `.cpp`, `.hpp`, `.h`, `.hip`), cross-checked by reading the
build files and exemplar sources in full. Two scopes are used and
always named:

- **Production scope** — `src/` + `include/`: 906 C++-family files.
- **Whole tree** — production + `tests/` + `examples/`: 1,208 files
  (844 in `src/`, 62 in `include/`, 301 in `tests/`, 1 in `examples/`).

Occurrence counts count tokens, not call sites in the semantic sense;
where a raw pattern is known to over- or under-count (the English word
"requires" in prose, `delete` inside `= delete`), the dossier says so
and gives the corrected reading. Exemplar paths are given for every
major claim so any statement can be re-verified against the tree.

## Headline findings

- Strict ISO C++20: `CMAKE_CXX_STANDARD 20`, `REQUIRED ON`,
  `EXTENSIONS OFF` — in the root build, the extension SDK, and the
  test fixture alike. C is C11 with extensions on, for vendored code.
- The dialect is **library-first**: the facilities that dominate are
  `std::span` (2,550 whole-tree occurrences), `std::string_view`
  (2,742), `[[nodiscard]]` (2,302), `constexpr` (4,442), `std::filesystem`
  (1,007), `std::chrono` (805), `std::bit_cast` (154). The headline
  *language* novelties of C++20 are used with restraint or not at all:
  exactly **one named concept**, **zero coroutines**, **zero modules**,
  **zero `std::expected`**, **zero `std::format`**, **zero `char8_t`**,
  **zero `std::source_location`**, **zero `[[likely]]`/`[[unlikely]]`**.
- Error handling is a **dual system**: typed exceptions derived from
  `std::runtime_error` for host-code failure (2,008 `throw` tokens in
  production scope), and small fixed-underlying-type status enums
  (`enum class AudioStatus : std::uint8_t`, k-prefixed enumerators)
  where callers branch on the outcome — the two are bridged by
  exception types that carry their status enum.
- Assertions are a **build-mode contract**, not a habit: production
  code contains almost no raw `assert(` (27 in production scope);
  tests contain 4,454. `BUILD_TESTING=ON` flips the whole tree to
  assertions-live via `-UNDEBUG` even at RelWithDebInfo optimization;
  shipped builds keep `NDEBUG`.
- Architecture is enforced *in* the language and build: manifest-
  declared library targets, a CMake-emitted link graph with a gate
  test, include-isolation ratchets, and public headers that are
  three-line forwarding shells over `src/` declarations.
- Tests use **no framework**: 241 of 262 test `.cpp` files carry their
  own `int main()`, a local `Expect` helper, and heavy compile-time
  evaluation (`static_assert` over `constexpr` fixtures).

## Sources

Upstream tree at `800ce328`: root `CMakeLists.txt`, `CMakePresets.json`,
`.clang-format`, `.clang-tidy`, `cmake/` (Checks, TargetGraph,
GufoExtension, PlatformTests), per-directory `CMakeLists.txt` files,
`library.json` manifests, and the exemplar sources named per dossier.
Census scripts and raw output were retained with the working papers of
this study. Companion evidence: deep-study dossiers 02 and 04.
