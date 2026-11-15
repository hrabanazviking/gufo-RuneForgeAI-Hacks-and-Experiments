# 07 — Writing Gufo-Grade C++20: The Practical Manual

This dossier is the heart of the mastery commission: not a description
of the tree but the craft itself — for each facility Gufo leans on,
what it is, why Gufo uses it that way, the pitfalls the project's own
rules and gates exist to catch, and the checklists for writing a new
component, a new test, and a public header. All counts are at
`800ce328` (dossiers 01–06).

## 1. The mental model first

Gufo's C++20 rests on five convictions. Hold them before the details:

1. **The header is the specification.** If a reader cannot predict
   the function from its declaration plus its comments, the function
   is wrong — not the reader.
2. **Contracts are types.** Statuses are enums, errors are classes,
   buffers are spans, paths are paths, times are durations. A raw
   integer or raw pointer at a boundary is an undocumented decision.
3. **Failure is typed and located.** Exceptions for unwinding, status
   enums for branching, file/line stamps where foreign code fails.
4. **Ownership is the architecture.** Who owns a thing determines
   whether it is unique, shared, pooled, or a view — and the
   pointer census is the design diagram.
5. **The build is a member of the team.** Format, tidy, the link
   graph, the isolation ratchets, the assertion mode — the rules are
   enforced by tools so that review time goes to ideas.

## 2. Facility explainers — the Gufo way to use each one

### 2.1 `std::span` — the buffer contract (2,550 uses)

*What it is.* A non-owning view over a contiguous sequence:
`{pointer, size}` with bounds-checked `operator[]` in debug and
iterator support, constructible from arrays, vectors, C arrays, and
`{ptr, n}`. `std::span<const std::byte>` is a read-only byte buffer;
`std::span<float>` is a mutable sample buffer.

*Why Gufo uses it.* Every byte-input in the codebase — decoded
audio, GGUF reads, cache transfers, tokenizer input — is a span. The
old alternatives are all worse: `(const void*, size_t)` splits one
fact into two parameters that can disagree; `const std::vector<T>&`
forces an owning container on callers; raw pointers have no length
at all. A span parameter *is* the length contract.

*Pitfalls, and how the tree guards them.*
- **Dangling spans** are the style's failure mode — which is why
  clang-tidy's `bugprone-dangling-handle` is in the gate set
  (dossier 01 §3). A span must never outlive its storage; Gufo's
  discipline is that spans cross *calls*, never *ownership* — if a
  callee must keep the data, it copies into a `vector` or takes
  ownership explicitly.
- **Contiguity is assumed, not checked**: a span of a non-contiguous
  structure is a lie. The tree only builds spans from contiguous
  storage.
- **Const-correctness matters**: `span<const std::byte>` for input,
  `span<std::byte>` or `span<T>` for output. Never `span<const T>`
  where the callee must write.

*Gufo's rule of thumb.* A function that reads bytes takes
`std::span<const std::byte>`; one that reads elements takes
`std::span<const T>`; one that fills takes `std::span<T>`; one that
stores takes `std::vector<T>` or an owner — never a span.

### 2.2 `std::string_view` — text without ownership (2,742 uses)

*What it is.* A `{pointer, length}` view over characters, with the
string algorithms. It is not null-terminated by guarantee — that is
its whole point and its whole danger.

*Why Gufo uses it.* Every read-only text parameter, every key, every
tokenizer input. Paired with `std::filesystem::path` for paths and
`std::string` for stored text, it makes the ownership question
answerable at a glance: view = borrowed, `std::string` = owned.

*Pitfalls.* A `string_view` over a temporary dies at the semicolon;
Gufo keeps them as parameters and locals, never as members of
long-lived objects (the `bugprone-dangling-handle` gate watches).
Never pass a `string_view` to a C function expecting a NUL-terminated
string without materializing it — the tree's C seams (Rust headers,
OS leaves) receive `std::string` or `c_str()` conversions, never a
bare view. And never store one: a struct field that is a view is a
dangling bug waiting for a caller to change.

### 2.3 `constexpr` and `if constexpr` — compile-time proof (4,442 / 559)

*What they are.* `constexpr` makes a function or variable evaluable
at compile time; `if constexpr` discards the untaken branch at
compile time, so the dead branch need not even be well-formed for
the instantiation.

*Why Gufo uses them this way.* Two separate reasons: (a) pure
arithmetic — admission budgets, sizes, masks — is `constexpr` so
tests can `static_assert` it (dossier 06); (b) `if constexpr` is
the tree's replacement for preprocessor conditionals and SFINAE in
numeric templates (`if constexpr (std::same_as<StateT, float>)` in
`recurrent_state.hpp`), keeping type-based branches inside the
language where the compiler checks them.

*Pitfalls.* `constexpr` functions must be side-effect-free and
their inputs must be literal types — reaching for a container or a
mutex inside one is a compile error, which is the point. `if
constexpr` discards the branch *per instantiation*: a template
whose dead branch is wrong for one type is only wrong if that type
is instantiated — the tree's answer is to instantiate the matrix
in tests (the DFlash and arena templates are exercised with the
unsigned types their `requires` clauses admit). And `constexpr` is
not `consteval` (1 use in the whole tree): Gufo wants compile-time
*evaluation where possible*, not compile-time *obligation* — a
function that can run at compile time must also run at run time,
because real inputs arrive at run time.

### 2.4 `[[nodiscard]]` — the two-thousand-fold habit (2,302 uses)

*What it is.* An attribute on a function (or type) that makes
discarding the return value a warning — here, effectively an error
wherever warnings are taken seriously.

*Why Gufo uses it everywhere.* Because the dual error system
(dossier 04) makes return values load-bearing: a status enum ignored
is a failure swallowed; an option struct ignored is a configuration
lost; a resource handle ignored is a leak. `[[nodiscard]]` on
*virtual interface methods* (`[[nodiscard]] virtual
TextRunnerDescriptor Descriptor() const = 0`) is the deepest
expression: implementers cannot silently weaken the contract.

*Pitfall.* Applied indiscriminately it breeds `static_cast<void>`
noise. Gufo's answer is that it is not indiscriminate: it marks
value-returning functions whose result is the point of the call —
and for the rare call where discarding is right, an explicit cast
or a `void` overload says so in the open.

### 2.5 Designated initializers — configuration as prose (≥240 src uses)

*What they are.* C++20's `Type{.field = value, ...}` — fields named
at the construction site, in any order, with the rest filled from
in-class defaults.

*Why Gufo uses them.* They are the configuration idiom: option
structs are aggregates with in-class member initializers
(`AudioLimits::max_channels{8}`), and call sites read as prose —
`GpuLocalBudget{.budget_bytes = 104 * kGiB, .usage_bytes = 81 *
kGiB}`. No positional confusion (is the third field the timeout or
the limit?), no builder class, no out-parameter soup. A partial
specification is safe because defaults are declared on the type,
not in the caller's head.

*Pitfalls.* Only aggregates qualify: no user-declared constructors,
no private members, no virtual functions — if a config struct
grows a constructor, every designated initializer breaks at once,
which is a *feature*: it forces the growth to be a reviewed design
change. Order must match declaration order in C++20 (unlike C) —
Gufo's 80-column formatter and the field-name-first style keep this
visible. And designated initializers name *public* fields: any
invariant that must hold between fields belongs in a validating
function or a real class, not in an aggregate.

### 2.6 `requires` clauses and the one concept — fences, rationed

*What they are.* A `requires` clause constrains a template:
`template<typename T> requires std::is_unsigned_v<T> void f(T);`
— the template simply does not participate for other types. A
concept names a reusable constraint set.

*Why Gufo uses them sparingly.* The tree's numeric templates are
narrow (unsigned sizes, integral CLI arguments, float/bf16 state
elements) and the fence belongs next to the template, where a
misuse is a clear compile error instead of a page of instantiation
noise. But the project keeps exactly **one** named concept because
most of its templates are not generic enough to need reusable
constraints — the temptation to build a concept library is exactly
the abstraction-for-its-own-sake the project refuses. The `enable_if`
extinction (1 occurrence) is the same judgment in the other
direction: the old SFINAE machinery is dead weight once `requires`
exists.

*Pitfalls.* A constraint that is too tight silently removes
overloads and produces confusing errors elsewhere — the tree's
clauses are single trait predicates (`std::is_unsigned_v<T>`,
`std::is_integral_v<T> && !std::is_same_v<T, bool>`), never
compositions. And a constraint must be *tested*: instantiate the
admitted types in tests, and if a type should be rejected, assert
the rejection exists — the tree's discipline is that a fence without
a test is decoration.

### 2.7 `std::bit_cast` — reinterpretation with a name (154 uses)

*What it is.* `std::bit_cast<To>(from)` reinterprets the bits of one
trivially-copyable type as another, at compile time when possible,
with no union and no `memcpy`.

*Why Gufo uses it.* Quantization and checkpoint storage need
bit-level movement between floats and integers; `bit_cast` says so
in one token and is `constexpr`-capable, so it composes with the
compile-time culture. It replaced the two unsafe idioms — union
type-punning (undefined behavior) and `memcpy` of 4 bytes (correct
but opaque).

*Pitfall.* Both types must be trivially copyable and the same size
— the compiler enforces it, which is the feature. `bit_cast` does
*not* change endianness or representation; a float bit pattern
moved to an integer and written to disk is host-endian, and the
tree's golden artifacts record that fact separately from compute
precision (dossier 04 §5).

### 2.8 Ranges algorithms, not pipelines (518 `std::ranges` uses, 0 `std::views`)

*What it is.* `std::ranges::find`, `sort`, `any_of`, `equal` — the
constrained algorithm set, taking whole ranges instead of iterator
pairs, with projection support.

*Why Gufo uses only the algorithm half.* The algorithms remove
iterator-pair boilerplate and the classic end-iterator bug class,
while keeping the loop's cost explicit in the call — the reader sees
a `find` and knows the scan happens here, now, once. Lazy view
pipelines hide work behind adaptors: where a pipeline's cost lives
is a question the reviewer must answer by reading the adaptor chain,
and in a performance codebase that is a real defect. `std::span`
already provides the "subrange" vocabulary explicitly.

*Pitfall.* `ranges::sort` on a range whose elements are views can
sort the views, not the data — the tree's ranges calls sit on owned
containers, not on lazily composed views, which is the same
discipline from the other side.

### 2.9 `std::jthread` and `std::stop_token` — owned threads, cooperative cancellation (71 / ~69)

*What they are.* `std::jthread` is a thread that joins itself on
destruction and owns a `stop_source`; a `std::stop_token` is the
cancellation handle handed to the worker, polled with
`stop_requested()`, with `stop_callback` for cleanup hooks.

*Why Gufo uses them.* They collapse the thread lifecycle into one
RAII object: start it as a member, stop it by `request_stop()`,
joining is the destructor. The cache worker pattern
(`slot.cpp:789–797`) is the canonical shape — a member `std::jthread
worker_`, a lambda capturing shared state and taking the token,
`RunIdle(stop)` polling it. The alternative (raw `std::thread` +
manual join + an atomic bool flag) is three mechanisms and two
invariants; jthread is one of each.

*Pitfalls.* `request_stop()` is cooperative — a worker that never
polls never stops, so the token must be threaded through every
blocking step of the worker's loop (the cache passes it into `Pin`
and the idle runner). A jthread member must be declared *after* the
state it captures (members destroy in reverse declaration order),
or destruction order silently breaks the invariant. And a token is
a value: copying it is fine, but passing it by value into a lambda
that outlives the source is the same lifetime discipline as a span.

### 2.10 Atomics with named orders — relaxed first (290 order tokens, 0 spelled seq_cst)

*What they are.* `std::atomic<T>` with `load`/`store`/
`fetch_add` taking an explicit `std::memory_order`.

*Why Gufo names orders.* An unnamed atomic operation is sequentially
consistent by default — the most expensive and least informative
choice. Naming the order documents the synchronization the author
believes exists: `relaxed` for counters and statistics where no
ordering is needed (131 — the plurality), `acquire`/`release` for
publication pairs (68/53), `acq_rel` for read-modify-write
synchronization (15). The absence of a spelled `seq_cst` is the
tell: sequential consistency is never *claimed* in this codebase.

*Pitfall.* `relaxed` is correct only when no ordering relationship
is required — a flag that publishes a pointer must be a release
store paired with an acquire load, and the codebase's acquire/
release counts cluster exactly at those publication sites. The
discipline for a reviewer: every atomic is read with its order, and
an order that cannot be justified is a defect report, not a style
nit.

### 2.11 `std::filesystem` and `std::chrono` — typed paths and times (1,007 / 805)

*What they are.* `std::filesystem::path` and the chrono duration/
time-point types — values whose type carries their unit and
semantics.

*Why Gufo uses them.* Because at boundaries, a path that is a
`std::string` can be concatenated, truncated, or compared as text;
a `path` has `parent_path()`, `extension()`, and platform-correct
separators. Because a timeout that is an `int` is 10 of what?
Milliseconds, in one call site and seconds in the next; a
`std::chrono::duration` is self-describing, and the clock census
(`steady_clock` 247, `system_clock` 13) enforces monotonic time for
every measured interval.

*Pitfalls.* `filesystem` operations throw (or take an `error_code`
overload) — Gufo's platform leaves translate those into its status
vocabulary at the seam, and the tree's 21 `std::system_error`
occurrences live there. `steady_clock` durations must never be
converted to wall time; a timestamp for the user goes through
`system_clock` at the presentation layer only.

### 2.12 What the tree declines — and why that is also a decision

Coroutines (0), modules (0), `std::expected` (0), `std::format` (0),
`std::views` (0), `char8_t` (0), `source_location` (0),
`[[likely]]`/`[[unlikely]]` (0). A beyond-PhD mastery includes
knowing what a master *doesn't* reach for: coroutines would trade a
readable thread-and-queue model for a compiler-transformed state
machine whose allocation and suspension points are invisible;
modules would trade a header discipline enforced by include gates
for a build-model change across three compilers; `expected` would
duplicate a dual error system that already works; `format` would
add a dependency to a codebase that formats by `to_string` and
streams; views would hide work. None of these is a verdict on the
facilities — the tree's pinned toolchain (GCC 16.2) supports them
all. It is a verdict on *this* codebase's priorities: legibility,
explicit cost, and mechanical enforceability over expressiveness.

## 3. Checklists

### 3.1 A new component

1. **Place it** in the right territory (`src/core` shared, `src/
   families`/`src/models` per-model, `src/cache`/`src/sched` only if
   it meets their boundary tests) and give it a `library.json`
   manifest with a prose `purpose` and an exact `depends` list.
2. **Declare it in a guarded header** (`GUFO_<PATH>_HPP_`) with
   sorted includes, a flat `gufo::<area>` namespace, and a prose
   contract on every public declaration — throws, units, limits,
   measured costs where they are part of the contract.
3. **Choose the error voice**: status enum (branchable outcomes) or
   typed exception (unwinding failures) — or both, bound in one type
   carrying the status, as `AudioError` does.
4. **Choose ownership**: unique for owned resources, shared only
   where co-ownership is the design, span/view for borrowed data,
   never a view stored, never a raw `new`. Delete copying where the
   resource forbids it; default what is trivially right.
5. **Write the tests first in spirit**: the contract sentences the
   tests will `Expect`, the `constexpr` fixtures that can be
   `static_assert`ed, the analytic or frozen oracle that will judge
   it. A component without an independent oracle is a draft.
6. **Run the gates**: format check, the smallest covering test set,
   the tidy correctness gate, the link-graph and isolation checks if
   it touches a boundary. Stage the new files before any Nix build.

### 3.2 A new test

1. One program per contract, `<component>_test`, own `main()`, local
   `Expect` with sentence messages.
2. Fixtures `constexpr` where the code allows; pin constants with
   `static_assert`; include field incidents as fixtures with
   provenance comments.
3. Expected values independent of the code under test (analytic,
   frozen, reference runtime) — never derived from the constants
   being validated.
4. Register with `add_test` + labels + timeout; argue for PR-gate
   membership in `cmake/Checks.cmake` on cost, not on enthusiasm.
5. Skips that stay visible; a missing-model skip is not a pass.

### 3.3 A public header

1. **Forwarding shell only** (`#pragma once` + include of the real
   declaration in `src/`); the contract lives in one place.
2. **Abstract interface style**: virtual destructor defaulted,
   pure virtuals for the required contract, non-pure virtuals with
   default bodies for optional capabilities, `[[nodiscard]]` on
   value-returning methods.
3. **Source-versioned**: any SURFACE-closure change gets the
   `ext-api` label and a new immutable record under
   `include/gufo/ext/changes/<major>.<minor>/` — descriptive
   filename, contracts changed, compatibility implications, no
   implementation history.
4. **Types at the boundary are stable value types**: fixed-width
   integers, `std::string_view`/`std::span` for data, shared
   ownership only where the lifetime demands it. No ABI promise is
   ever made — source compatibility after rebuilding is the guarantee.
