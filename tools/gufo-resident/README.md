# Gufo Resident — the Ollama-mannered resident service

`gufo_supervisor.py` is a small, dependency-free (Python standard
library only) supervisor that turns our Gufo build into a resident
service in the manner of Ollama:

- It runs at boot and loads **no** model. Resting state is the
  supervisor alone (a few dozen MB of RAM, no GPU work).
- The first inference call starts a private `gufo serve llm` child on
  a loopback port and loads the default model (from the SSD models
  directory this takes ~4–5 s).
- The model stays loaded under these rules, then unloads back to the
  light resting state:
  - `keep_alive: 0` on `/api/generate` or `/api/chat` unloads at once;
  - no inference for `GUFO_IDLE_UNLOAD` seconds (default 1200 = 20 min)
    unloads;
  - a residency ceiling of `GUFO_KEEP_ALIVE` seconds (default 1800 =
    30 min) from load, refreshed by inference activity, bounds
    residency; a per-request `keep_alive` is honored up to that
    ceiling, and `keep_alive: -1` pins the model until an explicit
    unload. In practice the idle rule fires first.
- Meta calls (`/api/tags`, `/api/ps`, `/api/version`, `/api/show`,
  `/v1/models`) are answered by the supervisor itself and never load
  the model.

## API surface

Ollama-shaped: `POST /api/generate`, `POST /api/chat`, `GET
/api/tags`, `GET /api/ps`, `POST /api/show`, `GET /api/version`,
`POST /api/embed` (friendly 501: the resident model is a text model).
OpenAI-shaped: `GET /v1/models`, `POST /v1/chat/completions`, `POST
/v1/completions` (proxied to the Gufo child once loaded). Models are
referenced by name and resolved inside `GUFO_MODELS_DIR`; errors are
Ollama-shaped `{"error": "..."}` objects with friendly messages.

## Character prompt and context discipline

- `GUFO_SYSTEM_PROMPT` or `GUFO_SYSTEM_PROMPT_FILE` set a pinned
  system prompt. It is placed first in every chat request and is
  never trimmed.
- When the estimated prompt exceeds `GUFO_MAX_PROMPT_TOKENS`, the
  oldest middle (non-system) messages are dropped, the pinned head
  and the recent tail are kept, and the trim is logged with counts.
  Nothing is ever silently middle-cut.
- Prefix reuse is the continuation cache of the Gufo server. By
  ruling of Volmarr it carries NO RAM cap by default
  (GUFO_CACHE_RAM_BYTES unset = unlimited); a cap exists only
  when the operator sets that variable to a byte count.
- Honest gap, recorded plainly: this Gufo build exposes no
  KV-cache-quantization or flash-attention switch on the serve
  command line, so there is no q8_0-KV equivalent to enable here.
  The cache-budget knobs above are the economy controls it does have.

## Robustness

Bad JSON, wrong types, oversized bodies, and unknown models get
friendly errors; the service keeps serving. A failed load leaves the
supervisor healthy and the next call retries. A child that dies
mid-generation is reaped and reloads on the next call. A generation
that runs past `GUFO_REQUEST_TIMEOUT_S` is treated as wedged: the
child is killed and the service recovers.

## Strain and thermal awareness

Every `GUFO_STRAIN_POLL_S` seconds the watcher samples the amdgpu
temperature (hwmon, resolved by name), the 1-minute load average, and
MemAvailable. When temperature reaches `GUFO_TEMP_THROTTLE_C`
(default 83 °C), or load exceeds `GUFO_LOAD_THROTTLE_PER_CPU` × CPUs
(default 1.25), or MemAvailable falls to `GUFO_MEM_MIN_AVAILABLE_MB`
(default 12288), the service throttles: inference concurrency drops
to 1 and generated tokens are capped at `GUFO_THROTTLED_MAX_TOKENS`
(default 1024); responses carry an `X-Gufo-Throttled: 1` header.
Recovery is automatic (temperature must fall to
`GUFO_TEMP_RECOVER_C`, default 78 °C). Transitions are logged once.
`GUFO_THERMAL_FILE` is a test hook: a file containing one millidegree
integer overrides the sensor reading so the throttle path can be
proven without heating the machine.

## Configuration (environment only, Ollama-style)

| Variable | Default | Meaning |
|---|---|---|
| `GUFO_HOST` / `GUFO_PORT` | `127.0.0.1` / `11435` | public bind (11434 stays Ollama's own) |
| `GUFO_CHILD_PORT` | `18100` | private Gufo child bind |
| `GUFO_BIN` | `~/.nix-profile/bin/gufo` | the Gufo binary to supervise |
| `GUFO_MODELS_DIR` | `~/models/gufo` | models directory (Phase 1 setting) |
| `GUFO_DEFAULT_MODEL` | — | default model name or path (Phase 1 setting) |
| `GUFO_IDLE_UNLOAD` | `1200` | idle seconds before unload |
| `GUFO_KEEP_ALIVE` | `1800` | residency ceiling seconds, refreshed by activity |
| `GUFO_REQUEST_TIMEOUT_S` | `900` | wedged-generation watchdog |
| `GUFO_LOAD_TIMEOUT_S` | `180` | child health deadline at load |
| `GUFO_MAX_REQUEST_BYTES` | `33554432` | friendly-413 limit |
| `GUFO_MAX_PROMPT_TOKENS` | `131072` | trim budget (estimated tokens) |
| `GUFO_CACHE_RAM_BYTES` | *(unset = no cap)* | child continuation-cache RAM cap; a limit exists only when set |
| `GUFO_MAX_CONCURRENT` | `4` | parallel generations when healthy |
| `GUFO_SYSTEM_PROMPT` / `GUFO_SYSTEM_PROMPT_FILE` | — | pinned character prompt |
| `GUFO_LOG_FILE` | — | optional rotating log file (5 MB × 3); default is stderr/journal |
| `GUFO_TRACE_FILE` | — | optional: pass `--trace` to the child (test rigs) |
| `GUFO_THERMAL_FILE` | — | test hook: fake temperature source |

## Install (as deployed on purpleraider)

1. Copy `gufo_supervisor.py` to `~/.local/lib/gufo-resident/`.
2. Copy `gufo-resident.service` to `/etc/systemd/system/`, adjust
   paths and environment, `systemctl daemon-reload`.
3. `systemctl enable --now gufo-resident.service`.

Stop/start: `sudo systemctl stop|start|restart gufo-resident.service`;
status: `systemctl status gufo-resident.service`; logs:
`journalctl -u gufo-resident.service`.
