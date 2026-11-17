#!/usr/bin/env python3
"""Gufo resident supervisor: an Ollama-mannered front for our Gufo build.

One small stdlib-only process. It owns the public HTTP surface and the
model lifecycle; the Gufo server itself runs as a private child process
that is started on first inference and stopped on unload.

Public surface:
  Ollama-shaped:  /api/generate /api/chat /api/tags /api/ps /api/show
                  /api/version /api/embed (friendly unsupported)
  OpenAI-shaped:  /v1/models (answered by the supervisor, works unloaded)
                  /v1/chat/completions /v1/completions (proxied to Gufo)

Lifecycle (Ollama-mannered):
  - No model is loaded at startup. Resting state is this process alone.
  - First inference starts the child and loads the default model.
  - keep_alive: 0 on generate/chat unloads immediately after the reply.
  - No inference for GUFO_IDLE_UNLOAD seconds (default 1200) unloads.
  - Residency ceiling GUFO_KEEP_ALIVE seconds (default 1800) from load,
    refreshed by inference activity; the idle rule fires first in
    practice. A per-request keep_alive is honored up to the ceiling;
    keep_alive: -1 pins the model until an explicit unload.
  - After unload the supervisor keeps answering meta calls (tags, ps,
    version, show, models) without loading anything.

Character prompt and context discipline (from our Ollama Memory Forge
record):
  - GUFO_SYSTEM_PROMPT / GUFO_SYSTEM_PROMPT_FILE configure a pinned
    system prompt. It is placed first in every chat request and is
    never trimmed.
  - Prompts are never silently middle-cut by the engine room here:
    when the estimated prompt exceeds GUFO_MAX_PROMPT_TOKENS, the
    oldest middle (non-system) messages are dropped, the pinned head
    and the most recent tail are preserved, and the trim is logged
    with counts. Nothing is dropped silently.
  - Prefix reuse is the Gufo server's own continuation cache (its RAM
    checkpoint budget is capped conservatively via --cache-ram-bytes).

Robustness law:
  - Malformed input (bad JSON, wrong types, oversized bodies, unknown
    models) gets a friendly Ollama-shaped {"error": ...} reply and the
    service keeps serving. Handlers never raise out of the server.
  - A failed load leaves the supervisor healthy; the next call retries.
  - A child that dies mid-generation is reaped; the next call reloads.
  - A generation that exceeds GUFO_REQUEST_TIMEOUT_S kills the child
    (wedged-state watchdog) and the service recovers on the next call.

Strain and thermal awareness:
  - A watcher samples the amdgpu hwmon temperature (resolved by name),
    /proc/loadavg and MemAvailable every GUFO_STRAIN_POLL_S seconds.
  - When the machine is hot or strained, inference concurrency drops
    to 1 and generated-token caps tighten; recovery is automatic.
    Transitions are logged once, not nagged. GUFO_THERMAL_FILE is a
    test hook: a file holding one millidegree integer overrides the
    sensor so the throttle path can be proven without heating the
    machine.

Configuration is environment-only, Ollama-style. See README.md beside
this file for the full variable list.
"""

import http.client
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

SUPERVISOR_VERSION = "1.0.0"

log = logging.getLogger("gufo-resident")


def env_str(name, default=""):
    v = os.environ.get(name)
    return default if v is None or v == "" else v


def env_int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def env_float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


class Config:
    def __init__(self):
        self.host = env_str("GUFO_HOST", "127.0.0.1")
        self.port = env_int("GUFO_PORT", 11435)
        self.child_host = "127.0.0.1"
        self.child_port = env_int("GUFO_CHILD_PORT", 18100)
        self.gufo_bin = env_str("GUFO_BIN", os.path.expanduser("~/.nix-profile/bin/gufo"))
        self.models_dir = os.path.expanduser(env_str("GUFO_MODELS_DIR", "~/models/gufo"))
        self.default_model = env_str("GUFO_DEFAULT_MODEL", "")
        self.idle_unload_s = env_float("GUFO_IDLE_UNLOAD", 1200.0)
        self.keep_alive_ceiling_s = env_float("GUFO_KEEP_ALIVE", 1800.0)
        self.request_timeout_s = env_float("GUFO_REQUEST_TIMEOUT_S", 900.0)
        self.load_timeout_s = env_float("GUFO_LOAD_TIMEOUT_S", 180.0)
        self.max_request_bytes = env_int("GUFO_MAX_REQUEST_BYTES", 32 * 1024 * 1024)
        self.max_prompt_tokens = env_int("GUFO_MAX_PROMPT_TOKENS", 131072)
        self.cache_ram_bytes = env_int("GUFO_CACHE_RAM_BYTES", 8 * 1024 * 1024 * 1024)
        self.max_concurrent = env_int("GUFO_MAX_CONCURRENT", 4)
        self.throttled_max_tokens = env_int("GUFO_THROTTLED_MAX_TOKENS", 1024)
        self.temp_throttle_c = env_float("GUFO_TEMP_THROTTLE_C", 83.0)
        self.temp_recover_c = env_float("GUFO_TEMP_RECOVER_C", 78.0)
        self.load_throttle_per_cpu = env_float("GUFO_LOAD_THROTTLE_PER_CPU", 1.25)
        self.mem_min_available_mb = env_int("GUFO_MEM_MIN_AVAILABLE_MB", 12288)
        self.strain_poll_s = env_float("GUFO_STRAIN_POLL_S", 5.0)
        self.thermal_file = env_str("GUFO_THERMAL_FILE", "")
        self.trace_file = env_str("GUFO_TRACE_FILE", "")
        self.system_prompt = env_str("GUFO_SYSTEM_PROMPT", "")
        prompt_file = env_str("GUFO_SYSTEM_PROMPT_FILE", "")
        if prompt_file and not self.system_prompt:
            try:
                with open(os.path.expanduser(prompt_file), "r", encoding="utf-8") as fh:
                    self.system_prompt = fh.read().strip()
            except OSError as exc:
                log.warning("could not read GUFO_SYSTEM_PROMPT_FILE %s: %s", prompt_file, exc)


CFG = Config()


# ---------------------------------------------------------------------------
# Model directory helpers
# ---------------------------------------------------------------------------

def list_model_files():
    """Return [(base_name, full_path, size)] for every GGUF in the models dir."""
    out = []
    try:
        names = sorted(os.listdir(CFG.models_dir))
    except OSError:
        return out
    for name in names:
        if not name.lower().endswith(".gguf"):
            continue
        path = os.path.join(CFG.models_dir, name)
        try:
            if os.path.isfile(path):
                out.append((name[: -len(".gguf")], path, os.path.getsize(path)))
        except OSError:
            continue
    return out


def normalize_model_name(raw):
    """Accept 'name', 'name:latest', 'name.gguf', 'name:tag' -> base name."""
    if raw is None:
        return ""
    name = str(raw).strip()
    if name.lower().endswith(".gguf"):
        name = name[: -len(".gguf")]
    if ":" in name and "/" not in name:
        name = name.split(":", 1)[0]
    return name


def resolve_model(raw_name):
    """Resolve a client-supplied model reference to (base, path, size).

    Empty reference -> the configured default. Unknown -> None.
    Paths outside the models directory are refused (returns None).
    """
    files = list_model_files()
    wanted = normalize_model_name(raw_name)
    if not wanted:
        wanted = normalize_model_name(CFG.default_model)
        if not wanted:
            return None
    if "/" in wanted or wanted in (".", ".."):
        return None
    for base, path, size in files:
        if base.lower() == wanted.lower():
            return (base, path, size)
    return None


def quant_of(base):
    m = re.search(r"[._-](Q\d+_[A-Z0-9_]+|IQ\d+_[A-Z]+|F16|F32|BF16)$", base, re.IGNORECASE)
    return m.group(1).upper() if m else ""


def family_of(base):
    return base.split("-", 1)[0].split("_", 1)[0].lower() if base else ""


# ---------------------------------------------------------------------------
# Minimal GGUF metadata reader (for /api/show); fully failure-tolerant.
# ---------------------------------------------------------------------------

_GGUF_TYPES = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?",
               10: "Q", 11: "q", 12: "d"}


def gguf_metadata(path, wanted_prefixes=("general.",)):
    import struct

    info = {}
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
            if len(head) < 8 or head[:4] != b"GGUF":
                return info
            version = struct.unpack("<I", head[4:8])[0]
            if version not in (2, 3):
                return info
            counts = fh.read(16)
            _n_tensors, n_kv = struct.unpack("<QQ", counts)

            def read_str():
                n = struct.unpack("<Q", fh.read(8))[0]
                if n > 1 << 24:
                    raise ValueError("string too long")
                return fh.read(n).decode("utf-8", "replace")

            import struct as _s
            sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1,
                     10: 8, 11: 8, 12: 8}
            for _ in range(min(n_kv, 4096)):
                key = read_str()
                vtype = struct.unpack("<I", fh.read(4))[0]
                keep = any(key.startswith(p) for p in wanted_prefixes)
                if vtype == 8:  # string
                    val = read_str()
                    if keep:
                        info[key] = val
                elif vtype == 9:  # array
                    etype = struct.unpack("<I", fh.read(4))[0]
                    n = struct.unpack("<Q", fh.read(8))[0]
                    if n > 1 << 22:
                        raise ValueError("array too long")
                    if etype == 8:
                        vals = [read_str() for _ in range(min(n, 64))]
                        if keep:
                            info[key] = vals
                    else:
                        fh.seek(sizes.get(etype, 0) * n, 1)
                elif vtype in _GGUF_TYPES:
                    fmt = "<" + _GGUF_TYPES[vtype]
                    val = struct.unpack(fmt, fh.read(sizes[vtype]))[0]
                    if keep:
                        info[key] = val
                else:
                    break
    except Exception:
        return info
    return info


# ---------------------------------------------------------------------------
# Strain / thermal watcher
# ---------------------------------------------------------------------------

class StrainWatcher(threading.Thread):
    def __init__(self, state):
        super().__init__(daemon=True, name="strain-watcher")
        self.state = state
        self.throttled = False
        self.reason = ""
        self.temp_c = None

    def read_temp_c(self):
        if CFG.thermal_file:
            try:
                with open(CFG.thermal_file, "r", encoding="utf-8") as fh:
                    return int(fh.read().strip()) / 1000.0
            except (OSError, ValueError):
                return None
        best = None
        try:
            hwmon_root = "/sys/class/hwmon"
            for entry in sorted(os.listdir(hwmon_root)):
                base = os.path.join(hwmon_root, entry)
                try:
                    with open(os.path.join(base, "name"), "r", encoding="utf-8") as fh:
                        if fh.read().strip() != "amdgpu":
                            continue
                except OSError:
                    continue
                for fn in sorted(os.listdir(base)):
                    if fn.startswith("temp") and fn.endswith("_input"):
                        try:
                            with open(os.path.join(base, fn), "r", encoding="utf-8") as fh:
                                val = int(fh.read().strip()) / 1000.0
                            best = val if best is None else max(best, val)
                        except (OSError, ValueError):
                            continue
        except OSError:
            pass
        return best

    def sample(self):
        temp = self.read_temp_c()
        self.temp_c = temp
        try:
            load1 = os.getloadavg()[0]
        except OSError:
            load1 = 0.0
        mem_avail_mb = None
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemAvailable:"):
                        mem_avail_mb = int(line.split()[1]) // 1024
                        break
        except OSError:
            pass
        ncpu = os.cpu_count() or 1
        reasons = []
        if temp is not None:
            if not self.throttled and temp >= CFG.temp_throttle_c:
                reasons.append("temperature %.1fC >= %.1fC" % (temp, CFG.temp_throttle_c))
            elif self.throttled and temp > CFG.temp_recover_c:
                reasons.append("temperature %.1fC still above recovery %.1fC"
                                 % (temp, CFG.temp_recover_c))
        if load1 >= ncpu * CFG.load_throttle_per_cpu:
            reasons.append("load1 %.2f >= %.2f" % (load1, ncpu * CFG.load_throttle_per_cpu))
        if mem_avail_mb is not None and mem_avail_mb <= CFG.mem_min_available_mb:
            reasons.append("MemAvailable %d MB <= %d MB"
                           % (mem_avail_mb, CFG.mem_min_available_mb))
        return reasons

    def run(self):
        while True:
            try:
                reasons = self.sample()
                strained = bool(reasons)
                if strained and not self.throttled:
                    self.throttled = True
                    self.reason = "; ".join(reasons)
                    self.state.set_throttled(True)
                    log.info("strain throttle ENGAGED (%s): concurrency=1, max_tokens<=%d",
                             self.reason, CFG.throttled_max_tokens)
                elif not strained and self.throttled:
                    self.throttled = False
                    self.reason = ""
                    self.state.set_throttled(False)
                    log.info("strain throttle RELEASED: machine healthy again")
            except Exception as exc:  # the watcher itself must never die loudly
                log.warning("strain watcher sample failed: %s", exc)
            time.sleep(CFG.strain_poll_s)


# ---------------------------------------------------------------------------
# Lifecycle state: UNLOADED -> LOADING -> LOADED, child process management
# ---------------------------------------------------------------------------

class ResidentState:
    def __init__(self):
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.status = "unloaded"  # unloaded | loading | loaded
        self.child = None  # subprocess.Popen
        self.child_log_fh = None
        self.model = None  # (base, path, size)
        self.loaded_at = 0.0
        self.last_activity = 0.0
        self.unload_at = None  # float deadline, or inf when pinned by keep_alive -1
        self.active_gens = 0
        self.load_error = ""
        self.throttled = False
        self.gen_sem = threading.Semaphore(CFG.max_concurrent)
        self.throttle_sem = threading.Semaphore(1)
        self.gufo_version = "unknown"

    # -- throttle -----------------------------------------------------------
    def set_throttled(self, on):
        with self.lock:
            self.throttled = on

    def is_throttled(self):
        with self.lock:
            return self.throttled

    def acquire_gen_slot(self):
        sem = self.throttle_sem if self.is_throttled() else self.gen_sem
        sem.acquire()
        return sem

    # -- lifecycle ----------------------------------------------------------
    def child_alive(self):
        return self.child is not None and self.child.poll() is None

    def ensure_loaded(self, model):
        """Start the child if needed. Returns (ok, error_message)."""
        with self.cond:
            if self.status == "loaded":
                if not self.child_alive():
                    log.warning("child died while marked loaded; reaping")
                    self._mark_unloaded_locked("child exited")
                elif self.model and self.model[1] == model[1]:
                    return True, ""
                else:
                    self._stop_child_locked("switching model")
                    self._mark_unloaded_locked("model switch")
            if self.status == "loading":
                while self.status == "loading":
                    self.cond.wait(timeout=5.0)
                if self.status == "loaded" and self.model and self.model[1] == model[1]:
                    return True, ""
                if self.status == "unloaded":
                    return False, self.load_error or "model failed to load"
                if self.status == "loaded":
                    # a different model finished loading while we waited
                    self._mark_unloaded_locked("model switch after wait")
            # status == unloaded: we become the loader
            self.status = "loading"
            self.load_error = ""
        ok, err = self._start_child(model)
        with self.cond:
            if ok:
                self.status = "loaded"
                self.model = model
                now = time.time()
                self.loaded_at = now
                self.last_activity = now
                self.unload_at = now + min(CFG.idle_unload_s, CFG.keep_alive_ceiling_s)
                log.info("model loaded: %s (child pid %s)", model[0],
                         self.child.pid if self.child else "?")
            else:
                self.status = "unloaded"
                self.load_error = err
                log.error("model load FAILED for %s: %s (service stays up; next call retries)",
                          model[0], err)
            self.cond.notify_all()
        return ok, err

    def _start_child(self, model):
        base, path, _size = model
        cmd = [CFG.gufo_bin, "serve", "llm",
               "--host", CFG.child_host, "--port", str(CFG.child_port),
               "--model", path,
               "--served-model-name", base,
               "--cache-ram-bytes", str(CFG.cache_ram_bytes)]
        if CFG.trace_file:
            cmd += ["--trace", CFG.trace_file]
        env = dict(os.environ)
        try:
            self.child_log_fh = open("/tmp/gufo-resident-child.log", "ab", buffering=0)
            proc = subprocess.Popen(cmd, stdout=self.child_log_fh,
                                    stderr=subprocess.STDOUT, env=env,
                                    stdin=subprocess.DEVNULL)
        except OSError as exc:
            return False, "could not start gufo server: %s" % exc
        self.child = proc
        deadline = time.time() + CFG.load_timeout_s
        while time.time() < deadline:
            if proc.poll() is not None:
                return False, ("gufo server exited during load with code %s; "
                               "see child log" % proc.returncode)
            try:
                conn = http.client.HTTPConnection(CFG.child_host, CFG.child_port,
                                                  timeout=3)
                conn.request("GET", "/v1/health")
                resp = conn.getresponse()
                resp.read()
                conn.close()
                if resp.status == 200:
                    return True, ""
            except OSError:
                pass
            time.sleep(0.5)
        try:
            proc.kill()
        except OSError:
            pass
        return False, "gufo server did not become healthy within %.0f s" % CFG.load_timeout_s

    def _stop_child_locked(self, why):
        proc = self.child
        if proc is not None:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                except OSError:
                    pass
            log.info("gufo child stopped (%s)", why)
        self.child = None
        if self.child_log_fh is not None:
            try:
                self.child_log_fh.close()
            except OSError:
                pass
            self.child_log_fh = None

    def _mark_unloaded_locked(self, why):
        self._stop_child_locked(why)
        self.status = "unloaded"
        self.model = None
        self.unload_at = None

    def unload(self, why):
        with self.cond:
            if self.status == "loaded":
                self._mark_unloaded_locked(why)
                log.info("model unloaded (%s); back to light resting state", why)
            self.cond.notify_all()

    def note_activity(self, keep_alive_s):
        """Record finished inference; compute the unload deadline.

        keep_alive_s: None = default rules; 0 = unload now; -1 = pin;
        >0 = keep at least that long (still bounded by the residency
        ceiling measured from the last activity, per house rules).
        Returns True when an immediate unload was requested.
        """
        now = time.time()
        with self.lock:
            self.last_activity = now
            if keep_alive_s is not None and keep_alive_s == 0:
                return True
            if keep_alive_s is not None and keep_alive_s < 0:
                self.unload_at = float("inf")
                return False
            idle_deadline = now + CFG.idle_unload_s
            ceiling_deadline = now + CFG.keep_alive_ceiling_s
            deadline = min(idle_deadline, ceiling_deadline)
            if keep_alive_s:
                deadline = max(deadline, min(now + keep_alive_s, ceiling_deadline))
            self.unload_at = deadline
            return False

    def ps_entry(self):
        with self.lock:
            if self.status != "loaded" or not self.model:
                return None
            base, _path, size = self.model
            expires = ""
            if self.unload_at and self.unload_at != float("inf"):
                expires = time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                        time.localtime(self.unload_at))
            return {
                "name": base + ":latest",
                "model": base + ":latest",
                "size": size,
                "digest": "",
                "details": {"format": "gguf", "family": family_of(base),
                            "families": [family_of(base)], "parameter_size": "",
                            "quantization_level": quant_of(base)},
                "expires_at": expires,
                "size_vram": size,
            }


STATE = ResidentState()


class Reaper(threading.Thread):
    """Idle/ceiling unloader + dead-child reaper. Never unloads mid-generation."""

    def __init__(self, state):
        super().__init__(daemon=True, name="reaper")
        self.state = state

    def run(self):
        while True:
            time.sleep(1.0)
            try:
                st = self.state
                with st.lock:
                    if st.status == "loaded" and not st.child_alive():
                        log.warning("child process gone; marking unloaded (self-heal)")
                        st._mark_unloaded_locked("child died")
                        continue
                    if (st.status == "loaded" and st.active_gens == 0
                            and st.unload_at is not None
                            and time.time() >= st.unload_at):
                        st._mark_unloaded_locked("idle/ceiling deadline reached")
                        log.info("model unloaded (idle/ceiling deadline); resting state")
            except Exception as exc:
                log.warning("reaper tick failed: %s", exc)


# ---------------------------------------------------------------------------
# Prompt discipline: pinned character prompt + no silent middle-cut
# ---------------------------------------------------------------------------

def estimate_tokens(text):
    return int(len(text) / 3.5) + 1


def message_text(msg):
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "\n".join(parts)
    return ""


def apply_prompt_discipline(messages):
    """Insert the pinned system prompt and trim the middle if over budget.

    Returns (messages, dropped_count). The pinned prompt is always the
    first system message and is never dropped. System messages are
    never dropped. When trimming, the oldest non-system messages go
    first; the most recent tail is preserved. Every trim is logged.
    """
    msgs = list(messages)
    if CFG.system_prompt:
        msgs = [{"role": "system", "content": CFG.system_prompt}] + msgs
    total = sum(estimate_tokens(message_text(m)) for m in msgs)
    if total <= CFG.max_prompt_tokens:
        return msgs, 0
    system_idx = {i for i, m in enumerate(msgs) if m.get("role") == "system"}
    # Always keep: all system messages + the last message (current turn).
    keep = set(system_idx)
    keep.add(len(msgs) - 1)
    kept_tokens = sum(estimate_tokens(message_text(msgs[i])) for i in keep)
    tail = []
    for i in range(len(msgs) - 2, -1, -1):
        if i in keep:
            continue
        t = estimate_tokens(message_text(msgs[i]))
        if kept_tokens + t > CFG.max_prompt_tokens:
            break
        tail.append(i)
        kept_tokens += t
    keep.update(tail)
    dropped = len(msgs) - len(keep)
    if dropped > 0:
        log.info("context trim: dropped %d middle message(s) (~%d tokens over budget); "
                 "pinned head and recent tail preserved", dropped, total - CFG.max_prompt_tokens)
    return [msgs[i] for i in sorted(keep)], dropped


def parse_keep_alive(value):
    """Ollama keep_alive: seconds number, or duration string ('5m', '1h', '0', '-1')."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("", "none", "null"):
            return None
        try:
            return float(s)
        except ValueError:
            pass
        m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(ms|s|m|h)?", s)
        if m:
            num = float(m.group(1))
            unit = m.group(2) or "s"
            return num * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    return None


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

def ollama_error(status, message):
    return status, {"error": message}


def now_rfc3339():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000000%z", time.localtime())


class ChildError(Exception):
    pass


def child_request(method, path, body_obj=None, stream=False, timeout=None):
    """One request to the private Gufo child. Returns the HTTPResponse."""
    conn = http.client.HTTPConnection(CFG.child_host, CFG.child_port,
                                      timeout=timeout or CFG.request_timeout_s)
    body = None
    headers = {}
    if body_obj is not None:
        body = json.dumps(body_obj).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=headers)
    return conn, conn.getresponse()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "gufo-resident/" + SUPERVISOR_VERSION

    # -- plumbing ------------------------------------------------------------
    def log_message(self, fmt, *args):  # quiet: our logger carries the story
        log.debug("http: " + fmt, *args)

    def _send_json(self, status, obj, extra_headers=None):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        if STATE.is_throttled():
            self.send_header("X-Gufo-Throttled", "1")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, status, text):
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self):
        """Returns (obj, raw_bytes) or raises ValueError with a friendly message."""
        length = self.headers.get("Content-Length")
        if length is None:
            return None, b""
        try:
            n = int(length)
        except ValueError:
            raise ValueError("invalid Content-Length header")
        if n < 0 or n > CFG.max_request_bytes:
            raise ValueError("request body too large (limit %d bytes)" % CFG.max_request_bytes)
        raw = self.rfile.read(n) if n else b""
        if not raw:
            return None, raw
        try:
            return json.loads(raw.decode("utf-8")), raw
        except (ValueError, UnicodeDecodeError):
            raise ValueError("request body is not valid JSON")

    # -- dispatch -------------------------------------------------------------
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def _dispatch(self, method):
        try:
            path = urlparse(self.path).path
            if method == "GET" and path == "/":
                return self._send_text(200, "Gufo is running")
            if method == "GET" and path == "/api/version":
                return self._send_json(200, {"version": STATE.gufo_version})
            if method == "GET" and path == "/api/tags":
                return self._tags()
            if method == "GET" and path == "/api/ps":
                entry = STATE.ps_entry()
                return self._send_json(200, {"models": [entry] if entry else []})
            if method == "GET" and path == "/v1/models":
                return self._v1_models()
            if method == "POST" and path == "/api/show":
                return self._show()
            if method == "POST" and path == "/api/embed":
                return self._send_json(*ollama_error(
                    501, "embeddings are not supported by this Gufo resident "
                         "service: the resident model is a text generation model"))
            if method == "POST" and path == "/api/generate":
                return self._generate()
            if method == "POST" and path == "/api/chat":
                return self._chat()
            if method == "POST" and path in ("/v1/chat/completions", "/v1/completions"):
                return self._v1_proxy(path)
            status, obj = ollama_error(404, "not found: %s %s" % (method, path))
            return self._send_json(status, obj)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away; nothing to fix
        except Exception as exc:  # robustness law: never crash the service
            log.exception("handler error: %s", exc)
            try:
                self._send_json(500, {"error": "internal error in gufo resident "
                                               "service; the service is still running"})
            except Exception:
                pass

    # -- meta endpoints ---------------------------------------------------------
    def _tags(self):
        models = []
        for base, _path, size in list_model_files():
            models.append({
                "name": base + ":latest",
                "model": base + ":latest",
                "modified_at": now_rfc3339(),
                "size": size,
                "digest": "",
                "details": {"format": "gguf", "family": family_of(base),
                            "families": [family_of(base)], "parameter_size": "",
                            "quantization_level": quant_of(base)},
            })
        return self._send_json(200, {"models": models})

    def _v1_models(self):
        data = []
        for base, _path, _size in list_model_files():
            data.append({"id": base, "object": "model", "created": int(time.time()),
                         "owned_by": "gufo"})
        return self._send_json(200, {"object": "list", "data": data})

    def _show(self):
        try:
            body, _raw = self._read_body()
        except ValueError as exc:
            return self._send_json(*ollama_error(400, str(exc)))
        if not isinstance(body, dict):
            return self._send_json(*ollama_error(400, "request body must be a JSON object"))
        name = body.get("name", body.get("model", ""))
        model = resolve_model(name)
        if model is None:
            return self._send_json(*ollama_error(
                404, "model '%s' not found in the Gufo models directory" % name))
        base, path, _size = model
        meta = gguf_metadata(path)
        model_info = {}
        for key, val in meta.items():
            model_info[key] = val
        arch = meta.get("general.architecture", family_of(base))
        if arch:
            model_info["general.architecture"] = arch
        return self._send_json(200, {
            "modelfile": "",
            "parameters": "",
            "template": "",
            "details": {"format": "gguf", "family": family_of(base),
                        "families": [family_of(base)], "parameter_size": "",
                        "quantization_level": quant_of(base)},
            "model_info": model_info,
            "capabilities": ["completion"],
        })

    # -- inference plumbing -----------------------------------------------------
    def _prepare_inference(self, body, need_messages=True):
        """Shared validation + model resolution. Returns (model, error_tuple)."""
        if not isinstance(body, dict):
            return None, ollama_error(400, "request body must be a JSON object")
        model = resolve_model(body.get("model", ""))
        if model is None:
            wanted = body.get("model", "") or CFG.default_model or "(none set)"
            return None, ollama_error(
                404, "model '%s' not found; set GUFO_DEFAULT_MODEL or name a "
                     "model from the Gufo models directory" % wanted)
        return model, None

    def _options_to_openai(self, body, stream):
        opts = body.get("options") or {}
        if not isinstance(opts, dict):
            opts = {}
        out = {"stream": stream}
        if "temperature" in opts:
            out["temperature"] = opts["temperature"]
        if "top_p" in opts:
            out["top_p"] = opts["top_p"]
        if "top_k" in opts:
            out["top_k"] = opts["top_k"]
        if "seed" in opts:
            out["seed"] = opts["seed"]
        if "num_predict" in opts:
            out["max_tokens"] = opts["num_predict"]
        if "stop" in opts:
            out["stop"] = opts["stop"]
        if STATE.is_throttled():
            cap = CFG.throttled_max_tokens
            if "max_tokens" not in out or (isinstance(out.get("max_tokens"), int)
                                           and out["max_tokens"] > cap):
                out["max_tokens"] = cap
        return out

    def _run_chat(self, model, messages, body, stream, keep_alive_s):
        """Run one chat completion against the child; translate to Ollama shape."""
        ok, err = STATE.ensure_loaded(model)
        if not ok:
            return self._send_json(*ollama_error(
                500, "model failed to load: %s" % err))
        base = model[0]
        oa_body = {"model": base, "messages": messages}
        oa_body.update(self._options_to_openai(body, stream))
        if stream:
            oa_body["stream_options"] = {"include_usage": True}
        sem = STATE.acquire_gen_slot()
        with STATE.lock:
            STATE.active_gens += 1
        started = time.time()
        try:
            if stream:
                self._stream_chat(base, oa_body, started)
            else:
                self._blocking_chat(base, oa_body, started)
        finally:
            sem.release()
            with STATE.lock:
                STATE.active_gens -= 1
            if STATE.note_activity(keep_alive_s):
                STATE.unload("keep_alive: 0")

    def _blocking_chat(self, base, oa_body, started):
        try:
            conn, resp = child_request("POST", "/v1/chat/completions", oa_body)
            raw = resp.read()
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            STATE.unload("child request failed")
            return self._send_json(*ollama_error(
                502, "the model server stopped responding; it will reload on "
                     "the next call (%s)" % exc))
        if resp.status != 200:
            return self._send_json(*ollama_error(
                502, "model server returned HTTP %d" % resp.status))
        try:
            data = json.loads(raw.decode("utf-8"))
            choice = data["choices"][0]
            content = choice["message"].get("content", "")
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError):
            return self._send_json(*ollama_error(
                502, "model server returned an unreadable reply"))
        total_ns = int((time.time() - started) * 1e9)
        return self._send_json(200, {
            "model": base + ":latest",
            "created_at": now_rfc3339(),
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": choice.get("finish_reason", "stop"),
            "total_duration": total_ns,
            "load_duration": 0,
            "prompt_eval_count": usage.get("prompt_tokens", 0),
            "prompt_eval_duration": 0,
            "eval_count": usage.get("completion_tokens", 0),
            "eval_duration": total_ns,
        })

    def _stream_chat(self, base, oa_body, started):
        try:
            conn, resp = child_request("POST", "/v1/chat/completions", oa_body,
                                       stream=True)
        except (OSError, http.client.HTTPException) as exc:
            STATE.unload("child request failed")
            return self._send_json(*ollama_error(
                502, "the model server stopped responding; it will reload on "
                     "the next call (%s)" % exc))
        if resp.status != 200:
            try:
                resp.read()
                conn.close()
            except Exception:
                pass
            return self._send_json(*ollama_error(
                502, "model server returned HTTP %d" % resp.status))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        if STATE.is_throttled():
            self.send_header("X-Gufo-Throttled", "1")
        self.end_headers()

        def emit(obj):
            line = (json.dumps(obj) + "\n").encode("utf-8")
            self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
            self.wfile.flush()

        usage = {}
        finish = "stop"
        buffer = b""
        try:
            while True:
                chunk = resp.read1(8192) if hasattr(resp, "read1") else resp.read(8192)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line.startswith(b"data:"):
                        continue
                    payload = line[len(b"data:"):].strip()
                    if payload == b"[DONE]":
                        continue
                    try:
                        data = json.loads(payload.decode("utf-8"))
                    except ValueError:
                        continue
                    if data.get("usage"):
                        usage = data["usage"]
                    for choice in data.get("choices", []):
                        delta = choice.get("delta") or {}
                        piece = delta.get("content") or ""
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
                        if piece:
                            emit({"model": base + ":latest",
                                  "created_at": now_rfc3339(),
                                  "message": {"role": "assistant", "content": piece},
                                  "done": False})
        except (OSError, http.client.HTTPException):
            STATE.unload("child stream failed")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        total_ns = int((time.time() - started) * 1e9)
        try:
            emit({"model": base + ":latest", "created_at": now_rfc3339(),
                  "message": {"role": "assistant", "content": ""},
                  "done": True, "done_reason": finish,
                  "total_duration": total_ns, "load_duration": 0,
                  "prompt_eval_count": usage.get("prompt_tokens", 0),
                  "prompt_eval_duration": 0,
                  "eval_count": usage.get("completion_tokens", 0),
                  "eval_duration": total_ns})
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    # -- Ollama endpoints ---------------------------------------------------------
    def _generate(self):
        try:
            body, _raw = self._read_body()
        except ValueError as exc:
            return self._send_json(*ollama_error(400, str(exc)))
        model, err = self._prepare_inference(body)
        if err:
            return self._send_json(*err)
        keep_alive_s = parse_keep_alive(body.get("keep_alive"))
        prompt = body.get("prompt", "")
        if not isinstance(prompt, str):
            return self._send_json(*ollama_error(400, "'prompt' must be a string"))
        if prompt == "" and keep_alive_s == 0:
            STATE.unload("keep_alive: 0 (explicit unload)")
            return self._send_json(200, {"model": model[0] + ":latest",
                                         "created_at": now_rfc3339(),
                                         "response": "", "done": True,
                                         "done_reason": "unload"})
        if prompt == "" and keep_alive_s is not None and keep_alive_s != 0:
            ok, lerr = STATE.ensure_loaded(model)
            if not ok:
                return self._send_json(*ollama_error(500, "model failed to load: %s" % lerr))
            STATE.note_activity(keep_alive_s)
            return self._send_json(200, {"model": model[0] + ":latest",
                                         "created_at": now_rfc3339(),
                                         "response": "", "done": True,
                                         "done_reason": "load"})
        messages = []
        system = body.get("system")
        if isinstance(system, str) and system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        messages, _dropped = apply_prompt_discipline(messages)
        stream = body.get("stream", True)
        if not isinstance(stream, bool):
            stream = True
        # Translate through the chat path; shape the reply as /api/generate.
        return self._run_generate_shaped(model, messages, body, stream, keep_alive_s)

    def _run_generate_shaped(self, model, messages, body, stream, keep_alive_s):
        # Reuse the chat machinery by capturing its JSON: simplest honest road
        # is to run the same child call and re-shape. We duplicate the small
        # blocking/stream handling here in generate shape.
        ok, err = STATE.ensure_loaded(model)
        if not ok:
            return self._send_json(*ollama_error(500, "model failed to load: %s" % err))
        base = model[0]
        oa_body = {"model": base, "messages": messages}
        oa_body.update(self._options_to_openai(body, stream))
        if stream:
            oa_body["stream_options"] = {"include_usage": True}
        sem = STATE.acquire_gen_slot()
        with STATE.lock:
            STATE.active_gens += 1
        started = time.time()
        try:
            if stream:
                self._stream_generate(base, oa_body, started)
            else:
                self._blocking_generate(base, oa_body, started)
        finally:
            sem.release()
            with STATE.lock:
                STATE.active_gens -= 1
            if STATE.note_activity(keep_alive_s):
                STATE.unload("keep_alive: 0")

    def _blocking_generate(self, base, oa_body, started):
        try:
            conn, resp = child_request("POST", "/v1/chat/completions", oa_body)
            raw = resp.read()
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            STATE.unload("child request failed")
            return self._send_json(*ollama_error(
                502, "the model server stopped responding; it will reload on "
                     "the next call (%s)" % exc))
        if resp.status != 200:
            return self._send_json(*ollama_error(
                502, "model server returned HTTP %d" % resp.status))
        try:
            data = json.loads(raw.decode("utf-8"))
            choice = data["choices"][0]
            content = choice["message"].get("content", "")
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError):
            return self._send_json(*ollama_error(502, "model server returned an unreadable reply"))
        total_ns = int((time.time() - started) * 1e9)
        return self._send_json(200, {
            "model": base + ":latest", "created_at": now_rfc3339(),
            "response": content, "done": True,
            "done_reason": choice.get("finish_reason", "stop"),
            "total_duration": total_ns, "load_duration": 0,
            "prompt_eval_count": usage.get("prompt_tokens", 0),
            "prompt_eval_duration": 0,
            "eval_count": usage.get("completion_tokens", 0),
            "eval_duration": total_ns})

    def _stream_generate(self, base, oa_body, started):
        # Same SSE walk as _stream_chat, emitting generate-shaped lines.
        try:
            conn, resp = child_request("POST", "/v1/chat/completions", oa_body, stream=True)
        except (OSError, http.client.HTTPException) as exc:
            STATE.unload("child request failed")
            return self._send_json(*ollama_error(
                502, "the model server stopped responding; it will reload on "
                     "the next call (%s)" % exc))
        if resp.status != 200:
            try:
                resp.read()
                conn.close()
            except Exception:
                pass
            return self._send_json(*ollama_error(502, "model server returned HTTP %d" % resp.status))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def emit(obj):
            line = (json.dumps(obj) + "\n").encode("utf-8")
            self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
            self.wfile.flush()

        usage, finish, buffer = {}, "stop", b""
        try:
            while True:
                chunk = resp.read1(8192) if hasattr(resp, "read1") else resp.read(8192)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line.startswith(b"data:"):
                        continue
                    payload = line[len(b"data:"):].strip()
                    if payload == b"[DONE]":
                        continue
                    try:
                        data = json.loads(payload.decode("utf-8"))
                    except ValueError:
                        continue
                    if data.get("usage"):
                        usage = data["usage"]
                    for choice in data.get("choices", []):
                        delta = choice.get("delta") or {}
                        piece = delta.get("content") or ""
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
                        if piece:
                            emit({"model": base + ":latest", "created_at": now_rfc3339(),
                                  "response": piece, "done": False})
        except (OSError, http.client.HTTPException):
            STATE.unload("child stream failed")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        total_ns = int((time.time() - started) * 1e9)
        try:
            emit({"model": base + ":latest", "created_at": now_rfc3339(),
                  "response": "", "done": True, "done_reason": finish,
                  "total_duration": total_ns, "load_duration": 0,
                  "prompt_eval_count": usage.get("prompt_tokens", 0),
                  "prompt_eval_duration": 0,
                  "eval_count": usage.get("completion_tokens", 0),
                  "eval_duration": total_ns})
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _chat(self):
        try:
            body, _raw = self._read_body()
        except ValueError as exc:
            return self._send_json(*ollama_error(400, str(exc)))
        model, err = self._prepare_inference(body)
        if err:
            return self._send_json(*err)
        keep_alive_s = parse_keep_alive(body.get("keep_alive"))
        messages = body.get("messages")
        if messages is None or (isinstance(messages, list) and not messages):
            if keep_alive_s == 0:
                STATE.unload("keep_alive: 0 (explicit unload)")
                return self._send_json(200, {"model": model[0] + ":latest",
                                             "created_at": now_rfc3339(),
                                             "message": {"role": "assistant", "content": ""},
                                             "done": True, "done_reason": "unload"})
            return self._send_json(*ollama_error(400, "'messages' is required"))
        if not isinstance(messages, list):
            return self._send_json(*ollama_error(400, "'messages' must be a list"))
        for m in messages:
            if not isinstance(m, dict) or "role" not in m or "content" not in m:
                return self._send_json(*ollama_error(
                    400, "each message must be an object with 'role' and 'content'"))
        messages, _dropped = apply_prompt_discipline(messages)
        stream = body.get("stream", True)
        if not isinstance(stream, bool):
            stream = True
        return self._run_chat(model, messages, body, stream, keep_alive_s)

    # -- OpenAI proxy ------------------------------------------------------------
    def _v1_proxy(self, path):
        try:
            body, _raw = self._read_body()
        except ValueError as exc:
            return self._send_json(400, {"error": {"message": str(exc),
                                                   "type": "invalid_request_error"}})
        if not isinstance(body, dict):
            return self._send_json(400, {"error": {"message": "request body must be a JSON object",
                                                   "type": "invalid_request_error"}})
        model, err = self._prepare_inference(body)
        if err:
            status, obj = err
            return self._send_json(status, {"error": {"message": obj["error"],
                                                      "type": "invalid_request_error"}})
        ok, lerr = STATE.ensure_loaded(model)
        if not ok:
            return self._send_json(500, {"error": {"message": "model failed to load: %s" % lerr,
                                                   "type": "server_error"}})
        base = model[0]
        body = dict(body)
        body["model"] = base
        if path == "/v1/chat/completions" and isinstance(body.get("messages"), list):
            body["messages"], _d = apply_prompt_discipline(body["messages"])
        stream = bool(body.get("stream"))
        sem = STATE.acquire_gen_slot()
        with STATE.lock:
            STATE.active_gens += 1
        try:
            try:
                conn, resp = child_request("POST", path, body, stream=stream)
            except (OSError, http.client.HTTPException) as exc:
                STATE.unload("child request failed")
                return self._send_json(502, {"error": {
                    "message": "the model server stopped responding; it will "
                               "reload on the next call (%s)" % exc,
                    "type": "server_error"}})
            payload_status = resp.status
            ctype = resp.getheader("Content-Type") or "application/json"
            self.send_response(payload_status)
            self.send_header("Content-Type", ctype)
            if STATE.is_throttled():
                self.send_header("X-Gufo-Throttled", "1")
            if stream:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                try:
                    while True:
                        chunk = resp.read1(8192) if hasattr(resp, "read1") else resp.read(8192)
                        if not chunk:
                            break
                        self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                        self.wfile.flush()
                except (OSError, http.client.HTTPException):
                    STATE.unload("child stream failed")
                try:
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except OSError:
                    pass
            else:
                raw = resp.read()
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            try:
                conn.close()
            except Exception:
                pass
        finally:
            sem.release()
            with STATE.lock:
                STATE.active_gens -= 1
            if STATE.note_activity(None):
                STATE.unload("keep_alive: 0")


def probe_gufo_version():
    try:
        out = subprocess.run([CFG.gufo_bin, "--version"], capture_output=True,
                             text=True, timeout=15)
        first = (out.stdout or "").strip().splitlines()
        if first:
            return first[0].replace("gufo version", "gufo").strip()
    except Exception as exc:
        log.warning("could not probe gufo version: %s", exc)
    return "gufo (unknown build)"


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s gufo-resident %(levelname)s %(message)s")
    log_file = env_str("GUFO_LOG_FILE", "")
    if log_file:
        handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s gufo-resident %(levelname)s %(message)s"))
        logging.getLogger().addHandler(handler)
    STATE.gufo_version = "resident %s / %s" % (SUPERVISOR_VERSION, probe_gufo_version())
    log.info("gufo resident supervisor %s starting on %s:%d (models dir %s, default %s)",
             SUPERVISOR_VERSION, CFG.host, CFG.port, CFG.models_dir,
             CFG.default_model or "(none)")
    log.info("lifecycle: idle unload %.0fs, residency ceiling %.0fs, child port %d",
             CFG.idle_unload_s, CFG.keep_alive_ceiling_s, CFG.child_port)
    StrainWatcher(STATE).start()
    Reaper(STATE).start()
    server = ThreadingHTTPServer((CFG.host, CFG.port), Handler)
    server.daemon_threads = True

    def _shutdown(signum, _frame):
        log.info("signal %d: shutting down", signum)
        threading.Thread(target=server.shutdown, daemon=True).start()
        STATE.unload("supervisor shutdown")

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    try:
        server.serve_forever()
    finally:
        STATE.unload("supervisor exit")
        log.info("gufo resident supervisor stopped")


if __name__ == "__main__":
    main()
