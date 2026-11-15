# 05 — Concurrency and Memory: Threads, Cancellation, Atomics, Pools

Sources: concurrency census (method in `00-INDEX.md`),
`src/cache/slot.hpp/.cpp`, `src/sched/policy.hpp`,
`src/cli/serve/text_model_runner.hpp`, `src/core/hip/`
(`transfer_pool.hpp`, `committed_backing.hpp`, `managed_alloc.hpp`,
`heap_placement.hpp`, `admission_memory.hpp`), `CMakeLists.txt`
(OpenMP at line 373). Tree at `800ce328`.

## 1. The threading model — threads with owners, not a thread pool

Gufo's concurrency is **structural**: each subsystem that needs a
thread owns exactly one, as a member, with a named job.

- The type specimen is the cache slot worker (`src/cache/slot.cpp:
  789–797`): a `std::jthread worker_` member is started with a lambda
  that captures the shared state object and receives the thread's
  stop token — `[state = state_](std::stop_token stop) {
  state->RunIdle(stop); }` — and shutdown is `worker_.request_stop()`
  followed by the jthread's implicit join on destruction. No detach,
  no manual join bookkeeping, no leaked lifetime: the jthread *is*
  the RAII wrapper for the thread.
- Census: `std::jthread` 71 vs `std::thread` 53 (whole tree). jthread
  is the default for owned workers (cache disk/streaming, the HTTP
  server in `src/cli/serve/http_server.cpp`); plain `std::thread`
  survives where a thread is handed off or in adapted/test code.
- The serving tier's concurrency lives in `src/cli/serve/`: the
  `TextRunnerPool` (`text_model_runner.hpp:58`) owns runner instances
  and the `text_generation_scheduler` assigns work; the *policy* of
  that assignment is not in the threaded code at all — it is
  `gufo_sched`'s pure `Policy` class over `WorkQueues`/`PrefillWork`/
  `DecodeWork` structs (`src/sched/policy.hpp`). The architectural
  split is the lesson: **threaded machinery executes; a pure,
  thread-free library decides** — and only the machinery needs
  synchronization.
- Synchronization census (whole tree): `std::mutex` 196,
  `std::lock_guard` 307 (the default guard — scope-bound locking),
  `std::unique_lock` 84 (where condition variables or deferred
  locking require it), `std::scoped_lock` 3, `std::condition_variable`
  35, `std::future`/`promise`/`async` 124 (request/reply at server
  seams), `std::barrier` 12, `std::latch` 8, semaphores 27 (bounded
  queues and admission). OpenMP exists but is a footnote:
  `find_package(OpenMP)` and 9 `#pragma omp` sites, for NPU host-side
  parallel-for work — data parallelism on the host is otherwise
  expressed as explicit worker threads or left to the GPU.

## 2. Cancellation — stop tokens plumbed as parameters

Cancellation is a **value that flows through signatures**, not a
global flag:

- Functions that can block or run long take a trailing
  `std::stop_token` parameter — the cache's `BorrowedRows::Pin(
  std::stop_token stop)` (`src/cache/slot.cpp:556`) and its sibling
  entry points in `slot.hpp` take the token alongside the work
  arguments, so a caller passes its own token down the call chain.
- Workers poll the token in their loops (`RunIdle(std::stop_token
  cancelled)`, `slot.cpp:247`) and the token's owner calls
  `request_stop()` at teardown; `std::stop_source` (11) and
  `std::stop_callback` appear where cancellation must be *produced*
  or observed rather than merely received.
- At API layers that cannot carry a token, the same idea appears as
  a callback: `DecodeAudio`'s `should_stop` (`std::function<bool()>`)
  is polled between packets, and its contract documents the mapping
  ("should_stop returned true" is `AudioStatus::kStopped`); the
  extension interface uses a settable `CancellationCheck` hook
  (`src/ext/text.hpp:278`). Three surface forms — token, callback,
  hook — one semantic: cooperative, polled, never forced.

## 3. Atomics — explicit orders, relaxed first, seq_cst never spelled

268 `std::atomic` occurrences and 290 `memory_order` tokens in
production scope, distributed:

| Order | Count | Share |
| --- | --- | --- |
| `memory_order_relaxed` | 131 | ~49% |
| `memory_order_acquire` | 68 | ~25% |
| `memory_order_release` | 53 | ~20% |
| `memory_order_acq_rel` | 15 | ~6% |
| `memory_order_seq_cst` | **0 spelled** | — |

The discipline is legible: every atomic operation that matters
*names* its order; the default sequential-consistency crutch is
never invoked by name; and the center of gravity is relaxed —
counters, statistics, admission tallies, and state flags whose
correctness comes from the surrounding mutex/queue structure, with
acquire/release pairs where a publication actually happens. A reader
auditing a Gufo atomic asks "what does this order buy?" because the
codebase guarantees the question has an answer. (Where plain atomic
operations rely on default ordering the census cannot see intent;
the spelled-order culture is the measurable fact.)

## 4. Time — monotonic or it didn't happen

`std::chrono` appears 805 times (whole tree) with a clock census that
is a policy in itself: `steady_clock` 247, `system_clock` 13,
`high_resolution_clock` 4. Durations, deadlines, timeouts, and every
measured interval use the monotonic clock; wall time appears only
where a timestamp must face the user or the disk format. Durations
are typed (`std::chrono` durations, never raw millisecond integers at
boundaries) — the same units-in-types discipline as byte counts in
`std::uint64_t` and statuses in enums.

## 5. Memory — pools and arenas with names, no pmr

- **`std::pmr`: 0 occurrences.** Polymorphic allocators were
  considered by the standard and declined by this codebase; allocation
  strategy is expressed as *named owner types*, not allocator
  parameters threaded through containers.
- The named types: `TransferPool` and `CommittedBackingPool`
  (`src/core/hip/`) pool GPU transfer buffers and committed cache
  backing — the two resources whose reuse patterns dominate serving
  cost; `TextRunnerPool` pools runner instances; the NPU has a
  `SharePool` (`src/core/npu/host_ops.hpp`); the Qwen HIP executor
  has an explicit `arena` (`src/models/qwen/hip/arena.cpp`, whose
  unsigned-size helpers carry the tree's `requires(std::is_unsigned_v
  <T>)` clauses). HIP allocation itself is wrapped
  (`managed_alloc.hpp`, `heap_placement.hpp`, `host_allocations.*`)
  so device memory has C++ owners with destructors, and *admission*
  is a computed decision, not an allocation failure:
  `admission_memory.hpp` computes free bytes against a GPU-local
  budget and a host-RAM margin (`kAdmissionHostMarginBytes` = 5.5 GiB)
  before work is accepted — the function its compile-time test
  exercises (dossier 06).
- Containers are the standard ones, unhidden: `std::vector` 6,470,
  `std::string` 10,157, `std::array` 1,185, `std::map` 118,
  `std::unordered_map` 73 (whole tree) — with `std::span` views over
  them at boundaries instead of iterator pairs.

## 6. Cache/session state at the C++ level

The continuation cache (`gufo_cache`) is where the concurrency and
memory idioms converge, and its file list is its architecture:
`identity` (what a continuation *is* — provenance-keyed, per the
deep study), `slot` (the resident-state slots and their idle worker),
`ledger` (the accounting), `checkpoint` (learned restore points),
`prefix_index` (shared-prefix lookup), `retention` (what may stay),
`disk` + `disk_catalog` (the spill tier), `streaming` (movement
between tiers), `completion` (transfer outcomes as `TransferResult`).
State that outlives a request is held in shared-ownership objects
(the cache's 114-to-23 shared-to-unique ratio, dossier 02) precisely
because sessions, the idle worker, and the disk tier legitimately
co-own it; state that does not is unique-owned inside models. The
C++ lesson generalizes: **ownership topology follows session
topology** — the smart-pointer census is the architecture diagram
drawn by the compiler.

## 7. The summary

Threads are owned members with stop tokens, not a pool; cancellation
is a parameter, not a flag; atomics always name their order and lean
relaxed; time is monotonic and typed; memory strategy is named pool
and arena types with computed admission, never allocator plumbing.
Concurrency in Gufo is deliberately *boring* — every mechanism is the
one a reviewer can hold in their head — because the interesting
problems (which state may be shared, which prefix may be reused) are
solved in the data structures, not in the synchronization.
