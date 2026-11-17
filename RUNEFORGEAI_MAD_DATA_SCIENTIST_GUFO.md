# RuneForgeAI Mad Data Scientist Personal Gufo Hacks

This is **Volmarr's personal RuneForgeAI hack line of Gufo**. It is not
official Gufo, it is not a community edition, and it is not built to
please anyone upstream. It is built the way a mad data scientist builds
the machine on his own desk: to his own standards, for his own needs,
on his own hardware — and it answers to RuneForgeAI alone.

Official Gufo lives at gufo-org/gufo. This fork,
hrabanazviking/gufo-RuneForgeAI-Hacks-and-Experiments, is where Gufo
gets taken apart, improved, and rebuilt into the runner we actually
want to live with. What survives real use here may, one day and only
when it is mature, be offered back upstream as a gift. Until then, this
line is sovereign.

## No support. No warranty. Read this first.

Plain words, so nobody can miss them:

- **RuneForgeAI offers NO support, NO help, and NO warranty of any
  kind for this personal version of Gufo.** Not a little support. Not
  "best effort." None. There is no help desk, no issue queue with our
  name on it, no promise that anything here works on your machine.
- **You are better off using the official upstream Gufo.** Seriously.
  It lives at gufo-org/gufo, it is the real project, and it is the
  version a sensible person runs. This fork is one man's personal
  workbench, kept in the open because open is how we work — not
  because it is a product offered to the world.
- **It is open source, so you may use the code as open source
  allows** — entirely at your own risk. If it sings on your hardware,
  good. If it breaks, the pieces are yours to keep.
- **By using it, you automatically agree** that you alone are
  responsible for the outcome, and that you have — or provide — your
  own tech support. Running this hack means signing that agreement
  with your actions; there is no other signature and no exception.
- **Do not expect the official Gufo project to support you either.**
  If you run this personal hack line and something goes wrong, it is
  unlikely the official Gufo project will support you — and it would
  be unfair to ask them to clean up after a version they did not
  make. Take your questions about official Gufo to official Gufo,
  running official code.

Friendly, and firm: this is a personal mad data scientist's bench.
Visitors may look, and may take the code as the license allows — but
they bring their own tools, their own skills, and their own risk.

## Our standards

- **Needs first.** Every change exists because our work needs it. If a
  feature does not serve the machines and the projects in this house,
  it does not get built, however fashionable it is elsewhere.
- **Our line, our rules.** The running line is never shaped to please
  upstream reviewers. It is the proving ground: improvements earn their
  place by working, under real load, on real hardware.
- **Plain and honest.** Behavior is documented as it truly is. Gaps are
  recorded as gaps, never dressed up as features.
- **Forgiving machinery.** Software here must not crash on bad input,
  must not silently lose a user's words, and must yield to the human
  using the machine. The machine serves the man, never the reverse.
- **No silent cuts.** Nothing in this line quietly throws away context,
  memory, or data. When something must be trimmed, it is logged, with
  counts, where the owner can see it.

## What we are adding

1. **A default-model setting, the Ollama way.** Environment variables
   as the primary mechanism: `GUFO_MODELS_DIR` names the models
   directory and bare model names resolve inside it;
   `GUFO_DEFAULT_MODEL` names the model a command uses when none is
   given. No config file required. An explicit `--model` always wins.
   A default that cannot be resolved is a clear, named error — never a
   silent fallback. `gufo diagnose` reports the effective settings.
2. **A resident, lazy-loading service.** Our Gufo sits resident like
   Ollama does: running at boot, loading **no** model until the first
   inference call, resting light, and springing to life in seconds
   when called. The model then stays loaded under plain rules:
   an Ollama-compatible unload (`keep_alive: 0`) drops it at once;
   twenty idle minutes drop it; a thirty-minute residency ceiling,
   refreshed by activity, bounds it. After an unload the service is
   back to its light resting state and still answers housekeeping
   calls. Timeouts are configurable, Ollama-style.
3. **An Ollama-compatible API surface.** `/api/generate`, `/api/chat`,
   `/api/tags`, `/api/ps`, `/api/show`, `/api/version`, `/api/embed`
   (or an honest, friendly "not supported"), `keep_alive` honored —
   alongside the OpenAI-compatible `/v1/chat/completions`,
   `/v1/completions`, and `/v1/models` the engine already speaks.
   Models are referenced by name. Software that talks to Ollama can
   talk to this.
4. **A pinned character prompt, and the Memory Forge lessons.** The
   character/system prompt is an anchor: always present, never
   truncated, never pushed out by a long conversation. Long prompts
   are never silently middle-cut (the defect we proved in Ollama):
   when context must shrink, the pinned head and the recent tail are
   preserved and the trim is logged. The front of the conversation is
   reused, not recomputed, where the engine honestly allows it; and
   where the engine has no equivalent for a proven optimization
   (such as quantized KV cache), the gap is written down plainly
   instead of being faked.
5. **Robustness as law.** Malformed requests — bad JSON, wrong types,
   oversized bodies, weird shapes — get a friendly, plain,
   Ollama-shaped error and the service keeps serving. A failed model
   load leaves the service healthy and ready to try again. A crashed
   or wedged inference is reaped and recovered without a restart.
   Logging is informative and quiet: no nagging, sane rotation.
6. **Strain and thermal awareness.** The service watches the machine —
   temperature, load, memory pressure — and slows itself down when
   the machine is hot or strained, returning to full performance when
   the machine is healthy again. The owner's interactive work always
   wins. This service never fights the man for his own computer.
7. **Friendliness.** Quiet, predictable behavior. Helpful errors. No
   demands, no nagging, no surprise resource use.

## Two-track governance

- **Track one — our line (sovereign).** The branch `yrsa/our-gufo` is
  the running line: the Gufo we build, install, and live with. It is
  also the proving ground where improvements mature under real use.
- **Upstream tracking.** The dev clone carries `upstream` pointing at
  gufo-org/gufo. Over time: fetch upstream, merge it into our line,
  and on our line **our features win conflicts**. Upstream goodness
  flows in; our sovereignty does not flow out.
- **Track two — donations (separate, later, no hurry).** When a mature
  improvement is chosen for donation, it gets its **own** clean branch
  named `donate/<feature>`, based on upstream's **current** main, with
  the improvement cherry-picked and reshaped to comply fully with
  upstream's standards, protocols, and style — none of our
  house-specific extras. Donations are gifts, prepared carefully, one
  at a time, when they are ready and not before.

## The rule about this file

**This charter is a house document. It is never donated.** It must
never appear on any `donate/*` branch, in any upstream pull request,
or in any patch offered to official Gufo. The same holds for every
house-only file on our line (the campaign state document, the resident
supervisor's house configuration, and anything else that exists only
because this is RuneForgeAI's personal line).

Therefore the donation procedure includes a hard step, every time:
**before any `donate/*` branch is pushed or any upstream PR is opened,
verify that this charter and all house-only files are absent from it.**
A donation that carries house files is not a donation; it is a leak,
and it does not ship.

---

*RuneForgeAI Mad Data Scientist Personal Gufo Hacks — built by
Volmarr's forge, for Volmarr's machines, to Volmarr's standards.*
