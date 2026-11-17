# Campaign State — RuneForgeAI Gufo Hacks

House record for the RuneForgeAI hack line of Gufo. This document
lives **only** on our line. It is never donated (see "House-only
files" below). The line's charter is `RUNEFORGEAI_MAD_DATA_SCIENTIST_GUFO.md`
at the repository root — read it first; it governs everything here.

## Two-track governance (standing policy)

1. **Our line is sovereign.** Branch `yrsa/our-gufo` is the running
   line: the Gufo we build, install, and live with, shaped to
   RuneForgeAI's standards and needs alone, never to please upstream.
   It is also the proving ground where improvements mature under real
   use. Slices land here as clean commits.
2. **Upstream tracking.** The dev clone carries remote `upstream` =
   `https://github.com/gufo-org/gufo.git` (and `fork` = our fork).
   Sync road: `git fetch upstream`, merge upstream into
   `yrsa/our-gufo`, and on our line **our features win conflicts**.
   Repeat as upstream moves; record each sync here.
3. **Donation track (separate, later, no hurry).** A mature
   improvement chosen for donation gets its own branch
   `donate/<feature>` based on upstream's **current** main, with the
   improvement cherry-picked and reshaped to fully comply with
   upstream's standards, protocols, and style — no house-specific
   extras. No PRs are opened until a donation is ready. None exist
   yet: the default-model slice is based on a pinned dev revision
   ahead of upstream main, so a clean donate branch is not yet cheap;
   it waits until the reshaping is worth doing properly.

## House-only files (never on any donate/* branch or upstream PR)

- `RUNEFORGEAI_MAD_DATA_SCIENTIST_GUFO.md` (the charter itself)
- `campaign/STATE.md` (this document)
- `tools/gufo-resident/` house configuration values in the unit
  template (the supervisor code itself is a donation candidate only
  after reshaping; the charter and this doc never are)

**Donation procedure, hard step:** before any `donate/*` branch is
pushed or any upstream PR is opened, verify that the charter and all
house-only files are absent from it.

## Branch map

| Branch | Base | State |
|---|---|---|
| `yrsa/default-model-setting` | pinned dev rev `49380168782f37d3967c3687ea07d7c78d86b3b9` | Phase 1, commit `4f737379` — kept as the slice record |
| `yrsa/our-gufo` | `yrsa/default-model-setting` | **the running line** — Phase 1 + Phase 2 |
| `donate/*` | upstream main (future) | none yet |

Fork main is upstream v0.34.0 (`800ce328`); our line is based on the
newer pinned dev revision the installed build uses, per the
commission. README.md is untouched on every branch, always.

## Phase 1 — default-model setting, the Ollama way (banked)

- New header-only helper `src/cli/model_env.hpp`: `GUFO_MODELS_DIR`
  resolves bare model names passed to `-m`; `GUFO_DEFAULT_MODEL`
  supplies the model when `-m` is absent (absolute path, or name
  resolved under the models dir); an unresolvable default fails with
  a clear named error; explicit `-m` always overrides; neither
  variable set = zero behavior change. Hooks in prompt/chat (shared
  parser), bench, and serve (llm branch only).
- `gufo diagnose` gained a `model_defaults` check reporting the
  effective models dir, default model, resolved path, and existence
  (PASS when unset or resolvable, WARN when set-but-missing).
- Documented in `docs/CLI.md` ("Model selection"). Diff: 169
  insertions, 0 deletions, 6 files. clang-format clean;
  `tools/ci/check-docs.py` passed.
- Verified end-to-end against the rebuilt binary (full matrix: no
  vars legacy behavior; absolute default; name-only default under
  models dir; bogus default named error exit 2; `-m` override both
  ways; diagnose in all three states; gemma4 extension intact; Qwen
  template-pin behavior unchanged; bench pp2048 2981.80 t/s, tg128
  42.69 t/s under default env; serve answered `/v1/models` and a chat
  completion with the SSD default).
- Installed: nix profile on purpleraider now carries
  `/nix/store/cval4yddk750p012ipx4clcyxrhpn7lb-gufo-0-unstable-4f73737`
  (`gufo version development (4f73737)`).
- Persistent env on purpleraider: `GUFO_MODELS_DIR=/home/volmarr/models/gufo`
  and `GUFO_DEFAULT_MODEL=gemma-4-26B-A4B-it-heretic.Q8_0.gguf` in both
  `~/.config/environment.d/10-gufo.conf` and `~/.profile`. Bare
  `gufo prompt` proven with only those values in play (Paris, ~4.2 s
  load); the `~/.local/bin/gufo-gemma` launchers still work.

## Phase 2 — resident Ollama-mannered service (banked)

Design: one stdlib-only Python supervisor
(`tools/gufo-resident/gufo_supervisor.py`) owns the public surface
and the lifecycle; `gufo serve llm` runs as its private child on a
loopback port. The engine already spoke the full OpenAI surface, so
the supervisor fills exactly the gaps: the Ollama API, the lifecycle,
and the discipline below. Full operator documentation:
`tools/gufo-resident/README.md`.

- **Lifecycle.** No model at startup. First inference loads the
  default model (SSD, ~4.2 s). `keep_alive: 0` unloads immediately;
  20-minute idle unload (`GUFO_IDLE_UNLOAD=1200`); 30-minute
  residency ceiling refreshed by activity (`GUFO_KEEP_ALIVE=1800`);
  per-request `keep_alive` honored up to the ceiling; `-1` pins.
  Never unloads mid-generation. Timeouts are env-configurable.
- **API.** `/api/generate`, `/api/chat` (streaming NDJSON +
  blocking), `/api/tags`, `/api/ps`, `/api/show` (real GGUF metadata
  via a small built-in reader), `/api/version`, `/api/embed`
  (friendly 501 — text model), `/v1/models` (answered unloaded),
  `/v1/chat/completions`, `/v1/completions` (proxied). Models by
  name via the Phase 1 env settings.
- **Character prompt + Memory Forge lessons.** Pinned system prompt
  (`GUFO_SYSTEM_PROMPT` / `_FILE`) always first, never trimmed.
  Over-budget prompts drop the oldest middle messages, keep the
  pinned head + recent tail, and log the trim with counts — proven
  against the child `--trace`: dropped messages never reached the
  engine. Prefix reuse is the engine's own continuation cache —
  measured live: a repeat prompt reported `cached_tokens: 42` of 42.
  Honest gap: this build exposes no KV-quantization or
  flash-attention serve flags, so there is no q8_0-KV equivalent to
  enable; the continuation-cache RAM budget is capped at 8 GiB
  instead (`--cache-ram-bytes`).
- **Robustness.** 11-case malformed battery (bad JSON, wrong types,
  missing fields, unknown model, oversized body, unknown path,
  embed) — all friendly Ollama-shaped errors, service unharmed.
  Failed load (garbage GGUF) returns a friendly 500, service stays
  up, next call retries. Child SIGKILLed mid-service: reaper marked
  it unloaded within ~1 s, next chat reloaded and answered — no
  restart. Wedged generations are bounded by
  `GUFO_REQUEST_TIMEOUT_S`.
- **Strain + thermal.** Watcher samples amdgpu hwmon temperature
  (resolved by name), load average, MemAvailable every 5 s. Throttle
  at 83 °C / load 1.25×CPUs / MemAvailable ≤ 12 GiB: concurrency 1,
  token cap 1024, `X-Gufo-Throttled: 1` header; auto-release at
  78 °C. Proven with the `GUFO_THERMAL_FILE` test hook (fake 95 °C:
  ENGAGED logged, header present on a live answer; back to 45 °C:
  RELEASED logged) — the machine was not heated for the test.
- **Measured numbers (purpleraider).** Resting supervisor: RSS
  27,232 kB, ~0.3% CPU, no child, no model. First production call:
  5.48 s wall to a complete answer (spawn + ~4.2 s load + decode).
  Warm chat: ~43 tok/s decode class, consistent with Phase 1 bench.
  Test-rig shortened clocks proved the idle rule at 25 s and
  `keep_alive: 0` at once; production runs the real 1200/1800.

## The service (registered, Yrsa-managed)

- Unit: `gufo-resident.service` (system service, enabled at boot,
  authorized by Volmarr's explicit order for this service).
- Runs as user `volmarr`; ExecStart
  `/usr/bin/python3 /home/volmarr/.local/lib/gufo-resident/gufo_supervisor.py`
  (installed copy of the repo file).
- Binds **`127.0.0.1:11435`** (configurable via `GUFO_PORT`). Port
  11434 belongs to the machine's existing Ollama service, which this
  campaign did not touch; 11435 is ours.
- Pinned prompt file: `/home/volmarr/.config/gufo/system-prompt.txt`
  (seeded with a brief Yrsa persona; editable).
- Operate: `sudo systemctl stop|start|restart gufo-resident.service`;
  status `systemctl status gufo-resident.service`; logs
  `journalctl -u gufo-resident.service`.
- One leftover found and removed during Phase 2 verification: a
  `gufo serve` process from the Phase 1 serve test (port 18099) was
  still alive and holding the model; it was killed. Nothing else on
  the machine was touched; no other services were created.

## Verification ledger (where the proof lives)

- Phase 1 matrix + Phase 2 battery were run live against the built
  binaries on purpleraider on 2026-11-17; headline outputs are quoted
  in the campaign report to Volmarr of that date.
- Fork state is the ground truth: `git ls-remote` for
  `yrsa/default-model-setting` and `yrsa/our-gufo`.
