# 01 — The Dialect: The Exact C++20 Gufo Speaks

Sources: root `CMakeLists.txt`, `CMakePresets.json`, `.clang-format`,
`.clang-tidy`, `cmake/sdk/CMakeLists.txt`, `cmake/GufoExtension.cmake`,
per-model `extension.cmake` files, and the feature census (method in
`00-INDEX.md`). Tree at `800ce328`.

## 1. The standard level, stated in build law

```cmake
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
```

(`CMakeLists.txt:24–26`.) Three decisions are packed into those lines:

- **C++20, exactly.** Not "at least 20", not a per-target minimum: the
  project-level variable plus `target_compile_features(... cxx_std_20)`
  repeated at the boundaries that must not drift — the extension SDK
  (`cmake/sdk/CMakeLists.txt:21–23,103`), the extension builder
  (`cmake/GufoExtension.cmake:574,1041`), the NPU library
  (`src/core/npu/CMakeLists.txt:10,27`), the extension runtime
  (`src/ext/CMakeLists.txt:6,39`), and the extension test fixture
  (`tests/extensions/fixture/CMakeLists.txt:8–9`). An extension author
  cannot accidentally build against a different dialect: the SDK
  states the same three lines.
- **Required, not best-effort.** `STANDARD_REQUIRED ON` makes a
  compiler without C++20 a configure error, not a silent downgrade.
- **No GNU extensions.** `EXTENSIONS OFF` selects strict `-std=c++20`
  rather than `-std=gnu++20`. The codebase may not lean on GNU-only
  language extensions; what it writes is ISO C++20 plus named library
  and platform facilities. (C is the deliberate exception:
  `CMAKE_C_STANDARD 11` with `EXTENSIONS ON`, `CMakeLists.txt:21–23`,
  because the C in the tree is vendored ancestry.)

Compilers: the pinned Nix toolchain builds with **GCC 16.2** (deep-study
dossier 02); clang drives formatting and tidy; Windows builds use the
MSVC frontend or clang-cl, which the CMake handles explicitly — warning
flags branch on `CMAKE_CXX_COMPILER_FRONTEND_VARIANT` because
"clang-cl interprets -Wall as /Wall" (`CMakeLists.txt:220–225`).
Portability of the dialect is thus a build-system concern, handled in
exactly one place, never in source `#ifdef` thickets — with one carved
exception: Windows compile definitions `NOMINMAX WIN32_LEAN_AND_MEAN
PSAPI_VERSION=2` are declared before any subdirectory so `windows.h`
can never poison `std::min`/`std::max` (`CMakeLists.txt:10–15`).

## 2. Warning law

Warnings are **on by default and identical everywhere**:

- Option `GUFO_ENABLE_WARNINGS` defaults ON (`CMakeLists.txt:216`).
- GNU/Clang: `-Wall -Wextra -Wpedantic`. MSVC frontend: `/W4`.
- The same flags are re-imposed on extension targets
  (`cmake/GufoExtension.cmake:583–593`), the SDK
  (`cmake/sdk/CMakeLists.txt:83–85`), and the fixture — an extension
  cannot quietly compile dirtier than the host.
- Compilation does **not** use `-Werror`. The warnings-as-errors teeth
  live in exactly one place: clang-tidy (section 3). A warning is
  therefore a strong signal reviewed by humans and the tidy gate, not
  a build veto — a deliberate calibration for a codebase that compiles
  the same sources under GCC, Clang, clang-cl, and MSVC.

## 3. Format and tidy law

`.clang-format` is short enough to quote in substance: **Google style,
`Standard: c++20`, 2-space indent, no tabs, 80-column limit**,
`AccessModifierOffset: -2` (access labels outdented one level from the
Google default), short functions allowed on one line only when inline,
short ifs/loops never collapsed, includes **regrouped and sorted
case-sensitively**, comments reflowed, pointers bound to the type
(`int* p`, `DerivePointerAlignment: false`, `PointerAlignment: Left`),
no space after the `template` keyword, namespace closing comments
fixed, and **no namespace indentation** (`NamespaceIndentation: None`)
— the last is why Gufo headers read flat inside `namespace gufo::… {`.

`.clang-tidy` is deliberately narrow, and its header comment is the
policy: *"Block on correctness defects; the broader style/performance
audit is opt-in."* The enabled set is `-*` plus `clang-analyzer-*` and
six named bugprone checks: `bugprone-use-after-move`,
`bugprone-dangling-handle`, `bugprone-sizeof-expression`,
`bugprone-suspicious-memset-usage`,
`bugprone-undefined-memory-manipulation`,
`bugprone-suspicious-string-compare`. `WarningsAsErrors: '*'`,
`HeaderFilterRegex: 'src/.*'`, `FormatStyle: file`. Read the selection
as a fingerprint of what this codebase fears: use-after-move and
dangling handles (a view-heavy codebase's real risks — dossier 02),
memory-manipulation slips, and string-compare mistakes. Style is
clang-format's job; tidy is a correctness gate only.

## 4. Presets: the dialect under different build modes

`CMakePresets.json` defines the working configurations; the dialect
(standard, warnings) is constant across all of them — only build type,
HIP, testing, tools, and sanitizers vary:

| Preset | Build type | HIP | Testing | Notes |
| --- | --- | --- | --- | --- |
| `release` | RelWithDebInfo | on | off | the shipped configuration |
| `gpu-test` | RelWithDebInfo | on | on | + tools; assertions live (dossier 04) |
| `cpu-test` | RelWithDebInfo | off | on | hosted-CI shape; drives build preset `pr` |
| `cpu-sanitizer` | Debug | off | on | + `GUFO_ENABLE_SANITIZERS=ON` |
| `windows-release` | RelWithDebInfo | on | off | vcpkg toolchain |
| `windows-cpu-test` | RelWithDebInfo | off | on | |

Test presets select by label and model: `gpu-fast` (excludes `slow`
and `external-model`), `gpu-full`, `deepseek-gpu`,
`qwen-gpu-kernel-oracle`, `cpu-sanitizer`, `cpu-test`. The default
build type when none is chosen is forced to RelWithDebInfo
(`CMakeLists.txt:17–19`) — there is no casual Debug or bare Release
in this project's life; debug information is always present, and
"release" means RelWithDebInfo with `BUILD_TESTING=OFF`.

## 5. The feature census

Whole-tree occurrence counts (production-scope figure in parentheses
where the split was measured). "Occurrences" are token counts per the
method in `00-INDEX.md`.

### 5.1 The load-bearing facilities

| Facility | Count | Reading |
| --- | --- | --- |
| `constexpr` | 4,442 | the tree's favorite keyword after the basics; compile-time evaluation is a primary design tool |
| `if constexpr` | 559 (src) | type- and config-based branching without preprocessor or SFINAE |
| `std::string_view` | 2,742 (1,931 src) | the default read-only string parameter |
| `std::span` | 2,550 (1,924 src) | the default buffer parameter; `std::span<const std::byte>` is the byte-input idiom |
| `[[nodiscard]]` | 2,302 (2,153 src) | applied to nearly every value-returning function, including virtual interface methods |
| `std::filesystem` | 1,007 | paths are `std::filesystem::path`, never raw strings, at API boundaries |
| `std::chrono` | 805 | durations and time points are typed, with a monotonic-clock culture (dossier 05) |
| `std::optional` | 771 | the "maybe" return; pairs with status enums for richer failure |
| designated initializers | ≥240 src / ≥613 tests (brace-dot lower bound) | option/config structs are aggregates filled by field name |
| `= delete` | 516 (src) | copy/move control is declared, not assumed |
| `= default` | 327 (src) | special members and comparisons defaulted explicitly |
| defaulted comparisons | 30 (src) | `operator==`/`operator<=>` defaulted where value equality is the contract |
| `std::bit_cast` | 154 | bit reinterpretation goes through `bit_cast`, not union punning or `memcpy` tricks (though `memcpy` itself appears 320 times for bulk byte movement) |
| `enum class` | 138 (vs 5 plain `enum`) | unscoped enums are effectively banned by practice |

### 5.2 Concurrency facilities (detail in dossier 05)

`std::jthread` 71, `std::stop_token`/`stop_source`/`stop_callback`
tokens 33 fully qualified in production scope (~69 `stop_token`
mentions), `std::atomic` 268, explicit `memory_order` 290
(`relaxed` 131, `acquire` 68, `release` 53, `acq_rel` 15,
`seq_cst` **0 spelled**), `std::barrier` 12, `std::latch` 8,
semaphores 27, `std::thread` 53, `std::mutex` 196, `std::lock_guard`
307, `std::unique_lock` 84, `std::scoped_lock` 3,
`std::condition_variable` 35, futures/promises/`std::async` 124.

### 5.3 Constraints — present, but rationed

C++20 concepts are the dialect's most surprising datum:

- Exactly **one named concept** exists in the whole tree:
  `QwenRecurrentStateElement` in
  `src/families/qwen/hip_common/recurrent_state.hpp:31–33` —
  `template<typename T> concept QwenRecurrentStateElement =
  std::same_as<T, float> || std::same_as<T, hip_bfloat16>;` —
  constraining a device-side state element type to the two precisions
  the recurrent kernels support, consumed by an abbreviated function
  template (`template<QwenRecurrentStateElement StateT>`).
- Beyond it, constraints appear as **trailing `requires` clauses with
  trait predicates**, in a handful of numeric templates:
  `src/cli/arg_parser.hpp:376,444` (`requires std::is_integral_v<T> &&
  (!std::is_same_v<T, bool>)`), `src/core/speculative/
  speculative_verifier.cpp:26,40`, `src/models/qwen/hip/arena.cpp:
  58,71`, `src/models/qwen/hip/dflash/backend.cpp` and
  `executor.cpp` (all `requires(std::is_unsigned_v<T>)`).
- `std::enable_if` survives in exactly **1** production occurrence.
  SFINAE is extinct here; where a template must be fenced, a
  `requires` clause does it — but the project's instinct is to fence
  rarely and overload or specialize plainly instead. (The raw
  `requires` token count, 309, is mostly the English word in comments
  and error strings; the code-shaped census above is the true one.)

### 5.4 Ranges: algorithms yes, pipelines no

`std::ranges` appears 518 times, and the distribution is the story:
`ranges::find` 98, `any_of` 65, `sort` 38, `all_of` 27, `equal` 26,
`none_of` 23, `find_if` 19, `copy` 15, `fill` 14, `transform` 10 —
**constrained algorithms called on whole containers**.
`std::views` appears **0** times: no lazy view pipelines, no
`views::filter | views::transform` chains anywhere in the tree. The
codebase takes from ranges exactly the part that removes iterator-pair
boilerplate and projection-less mistakes, and declines the part that
hides work behind adaptors — consistent with a performance codebase
that wants every loop's cost visible (and with `std::span` doing the
"subrange" job explicitly).

### 5.5 The conspicuous absences

Each of these was counted, not assumed:

- **Coroutines: 0** `co_await`, 0 `co_yield`, 0 `co_return` in the
  entire tree. Asynchrony is threads, queues, and callbacks
  (dossier 05).
- **Modules: 0.** No `.cppm`/`.ixx` files, no `import`, no
  `export module`. Headers and include discipline carry the module
  system's practical load (dossier 02, 03).
- **`std::expected`: 0.** The error system predates and out-argues it:
  exceptions + status enums (dossier 04).
- **`std::format`: 0; `fmt::`: 0.** Formatting is `std::to_string`
  (569), `std::ostringstream` (109), `snprintf` (23), and hand-rolled
  writers; parsing leans on `std::from_chars` (32). No formatting
  library is a dependency at all.
- **`char8_t` / `u8string`: 0.** UTF-8 is `char` + discipline (and ICU
  where real Unicode work happens), not a distinct type.
- **`std::source_location`: 0.** Diagnostics carry `__FILE__`/`__LINE__`
  through macros where needed (HIP_CHECK, dossier 04).
- **`[[likely]]` / `[[unlikely]]`: 0; `[[no_unique_address]]`: 0;
  `constinit`: 0; `consteval`: 1.** The attribute vocabulary actually
  used is `[[nodiscard]]` at industrial scale and almost nothing else.
- **Spaceship:** 5 `<=>` tokens; three-way comparison exists only as
  defaulted operators on value types (part of the 30 defaulted
  comparisons), never as hand-written ordering logic.
- **`std::views`, `std::generator`, `std::print`:** absent as idioms
  (the only `std::print`-shaped hits are `std::printf` in the
  diagnostics CLI).

### 5.6 The HIP dialect split

HIP is a first-class CMake language (`enable_language(HIP)`,
`CMakeLists.txt:149`) with the architecture **hard-locked**:
`CMAKE_HIP_ARCHITECTURES` must be `gfx1151` or configuration fails
(`CMakeLists.txt:137–139`). The root build sets no `CMAKE_HIP_STANDARD`
— device code rides the pinned toolchain's default — with two loud
exceptions: the adapted kernel sets in
`src/models/deepseek_v4_flash/extension.cmake:56–57` and
`src/models/qwen38_flash_next/extension.cmake:59–60` pin
`HIP_STANDARD 17` per target. Those are the llama.cpp/DS4-derived
quantized-kernel islands: they keep their upstream C++17 dialect, their
own check macros (`GGML_ASSERT`, `DS4_HIP_CHECK`), and their own
`extern "C"` blocks (the tree's `extern "C"` count, 245, concentrates
there and at the Rust seam), fenced off from the C++20 host dialect by
target boundaries. The lesson the tree teaches: **dialect purity is
per-target law, and adapted code keeps its native dialect inside its
fence rather than being rewritten into the house style.**

## 6. What kind of C++20 this is — the summary

Gufo's C++20 is a **conservative-modern systems dialect**: strict ISO
level, library facilities adopted aggressively where they remove
boilerplate or encode contracts (`span`, `string_view`, `nodiscard`,
`constexpr`, `filesystem`, `bit_cast`, `jthread`/`stop_token`),
language novelties adopted only where they pay rent immediately
(designated initializers, defaulted comparisons, a whisper of
concepts), and the era's fashionable machinery — coroutines, modules,
views pipelines, `expected`, `format` — declined wholesale. Exceptions
and RTTI are fully enabled (no `-fno-exceptions`/`-fno-rtti` anywhere;
`typeid` is nonetheless unused, 0 occurrences, while `dynamic_cast`
appears 149 times). It reads less like a showcase of C++20 and more
like C++17-era engineering discipline that took C++20's contract-
encoding tools and left its magic on the table.
