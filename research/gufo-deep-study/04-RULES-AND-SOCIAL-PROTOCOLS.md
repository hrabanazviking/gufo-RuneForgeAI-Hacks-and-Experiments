# 04 — Rules and Social Protocols: The Human Layer, in Full

Sources: all six `AGENTS.md` files read in full at `800ce328`;
`docs/AGENTS.md` (the documentation constitution); the registry `REVIEW.md`;
`NOTICE` + `THIRD_PARTY_NOTICES.md` + `licenses/`; the three gufo.blog
posts; `docs/internal/*`. Quotations are short and attributed; rules are
summarized faithfully in the study's words with their home file named.
See `00-INDEX.md`.

## 1. Where the rules live (and where they do not)

Gufo has **no `CODE_OF_CONDUCT.md`, no `CONTRIBUTING.md`, no issue or PR
templates** in the main repository as of `800ce328` — verified by tree
listing and by GitHub's community profile (37%). The project's social
contract is instead distributed across:

- **`AGENTS.md` files** — six of them, scoped like constitutions for
  sub-territories: root (whole repo), `docs/` (documentation),
  `include/gufo/ext/changes/` (API change records), `src/core/rust/`
  (the Rust enclave), `src/families/qwen/` and `src/models/qwen/` (the
  Qwen family and models). Every `CLAUDE.md` in the tree is a **symlink**
  to the corresponding `AGENTS.md` — one rulebook, two names, no drift.
  The README's contributing section points here in one breath:
  contributions are welcome; start with the development and testing docs;
  "`AGENTS.md` holds the rules that people and coding agents follow."
  The address is deliberately to *people and coding agents* alike — the
  blog confirms the project is "heavily built with AI and our own ideas,
  and we're happy with that."
- **The internal docs** (`docs/internal/`) — releasing, CI, testing,
  extension distribution carry the operational norms.
- **The registry's `REVIEW.md`** — the trust etiquette for community code.
- **The blog** — the project's public voice and self-explanation.

The practical consequence for an outsider: **you learn how to behave here
by reading `AGENTS.md` and the internal docs, not by finding a conduct
file.** The rules below are therefore the real social protocol.

## 2. The root AGENTS.md — the whole-repo rulebook

Summarized rule by rule (root `AGENTS.md`):

**Toolchain and builds**
- Nix supplies the pinned toolchain; CMake owns flags, dependencies,
  installation, and generated files. Commands: `nix build` (dev package,
  all discovered extensions), `nix build .#release` (lock-mode, no
  tests/tools), `nix flake check` (hosted CPU/repo checks), `nix develop`
  (GPU dev shell).
- Stage only task-owned paths before Nix builds — flakes see tracked
  files only. (In practice: commit/stage your new files or the build
  silently ignores them.)
- Run the format gate before committing C++:
  `nix shell --inputs-from . nixpkgs#clang-tools -c python3 tools/ci/check-format.py`.
- Run the smallest check that covers the change. The `gpu-test` preset is
  RelWithDebInfo + assertions.

**Timing and evidence (the project's honesty core)**
- Correctness and expected prefill/cache work are strict.
- Timings are mandatory per request and per phase at 5% and 10 ms, and
  are **never averaged across requests**.
- Run once; investigate flags; compare against main or a PR only for the
  affected histories; **fix confirmed regressions before publishing**.
- Noisy evidence stays visibly inconclusive and unqualified — **do not
  widen margins** to make a result pass.
- **"A missing-model skip is not a quality pass."**
- For reported coding-agent loops, replay with
  `tests/functional/pi_agent.py` and retain the sessions.

**Code ownership**
- Kernel work follows `.agents/skills/optimize-kernel`.
- Production paths retain quality; **successful optimizations become the
  default without extra switches** (no flag-gated improvements left
  lying around).
- Model code, tests, tools, and numerical contracts stay with their
  model.
- Windows code lives only in `src/core/platform/` leaves, one per OS
  facility; no `windows.h`/`_WIN32` outside it and vendored code; never
  emulate POSIX with macros.
- One canonical long option and one backend name per behavior; no
  aliases.

**GitHub and commits**
- Use `gh` for GitHub after `gh auth status`.
- Conventional Commits, single-line; PR titles follow `releasing.md`;
  squash merge retains the title; breaking changes carry `!`.
- Leave version and changelog to the release workflow.
- Prefer `jj` over git when available.

**Extension API**
- SURFACE-closure changes need the `ext-api` label plus one new immutable
  record under `include/gufo/ext/changes/<major>.<minor>/`; run
  `check-extension-api.py --write` after header changes. Pre-1.0 a minor
  may break; a revision is additive; compatibility is source-only, never
  ABI.

**NPU**
- Keep repeated runtime work inside IRON `range_` loops (Python `range`
  expands the IR); time cold builds; preserve verification and compiler
  optimization.

**Working with the human**
- "Follow the user's remote workflow, preserve unrelated work." — the
  rulebook ends by subordinating itself to the person directing the work
  and to not disturbing work that is not yours.

## 3. The documentation constitution (docs/AGENTS.md)

This is the project's most literary rulebook — a style law enforced by
`tools/ci/check-docs.py`:

- **Layout:** `docs/*.md` and `docs/models/*.md` are public (published on
  the website, one frozen copy per release); `docs/internal/` is for
  contributors and agents, repo-only; implementation notes and
  benchmark/quality/experiment evidence live in
  `docs/internal/models/<model>/`; design RFCs in `docs/internal/design/`.
  A public page says how to use; an internal page says how it is built,
  measured, and changed; a page doing both must be split.
- **Shape:** every public page opens with `# Title`, a blank line, and a
  one-to-two-sentence summary (the site uses both as title and
  description). `docs/README.md` is the index the site navigation builds
  from — a page not in the index does not exist publicly.
- **Voice:** "Write like the Gufo blog: plain, direct and exact." Address
  the reader as "you"; active voice; contractions are fine. Plain words
  over jargon; a needed technical term is **bolded** and defined at first
  use; one name per concept. Lead with what the reader does or gets.
- **Numbers exactly, with units, and dated** ("As of November 2026, …").
  Link evidence under `docs/internal/` instead of repeating it. Tables
  only for same-column comparisons. Warnings are blockquotes beginning
  `**Warning:**`.
- **Budgets:** 250 lines for a public page, 120 for a model page; over
  budget means split or move material internal.
- **Currency law:** public pages hold *current behavior only* — **no
  history** (no "used to", "now", "recently"), **no PR or issue numbers**,
  **no design rationale** (rationale goes to `docs/internal/design/`). A
  behavior change updates its owning page in the same PR. A new public
  page needs a maintainer's agreement.
- **The filler ban list** (banned words in public docs): "simply", "just",
  "easily", "basically", "obviously", "note that", "it is worth",
  "seamless", "blazing".
- **Figures:** static SVG only, in `docs/figures/`; 760-wide viewBox;
  background rect first; the shared `figures/style.css` embedded verbatim
  and only its classes used; `role="img"` with a `<title>` as alt text;
  ids prefixed with the file name; no script, foreignObject, images,
  external hrefs, or web fonts; under 30 KB; ~20% spare width around text.
  And the rule that explains all the others: **prose must say everything
  the figure says, "because agents read the text, not the picture."**
- Format: plain GitHub-renderable Markdown — no MDX, no HTML, no scripts;
  code blocks name their language.

## 4. The territory rulebooks

**Rust (`src/core/rust/AGENTS.md`)** — summarized in dossier 02 §3. Its
social core: new components are *proposed socially first* (Discussion
#864); ports must prove themselves against a frozen independent oracle and
explain every difference; dependency additions carry licensing paperwork
in the same change; breaking behavior needs the `!` and a list in the PR
description.

**Qwen family (`src/families/qwen/AGENTS.md`)** — shared token spellings
live in one place (`control_tokens`); production framing code uses the
named constants, never literals; new tokens are confirmed against pinned
model metadata or the official reference; the C++ catalogue and its
Python mirror (`tools/gufo/control_tokens.py`) are updated together and
kept identical; and an epistemic rule worth quoting in substance:
**expected results must not be derived solely from the constants they
validate** — tests need independent fixtures and rendered-byte goldens.
Library boundaries: one directory per library with `library.json` +
`CMakeLists.txt`; acyclic graph; declared dependencies must be exactly
the ones actually included — an unused declaration fails, an undeclared
edge fails.

**Qwen models (`src/models/qwen/AGENTS.md`)** — the 27B directory owns
target inference, native MTP, and DFlash2; kernel per-source compile
options are bound to the model's target and must travel with moved
kernels, producing identical production code objects; **run the model's
quality runners before changing arithmetic, layouts, or cache
boundaries.** It also records an in-flight migration honestly: the model
is "the model's home until Card 20 gives it an `extension.json` manifest"
— the CMake still defines a plain library, i.e. the 27B is mid-conversion
to extension form and the rulebook says so.

**API change records (`include/gufo/ext/changes/AGENTS.md`)** — one
uniquely named Markdown record per public-contract change; descriptive
filename (a feature/issue identifier is fine; no version or revision
numbers in filename, heading, or description); heading + the concrete
contracts changed + compatibility/rebuilding implications; **keep
implementation history and test logs out**; merged records are permanent
and immutable; `baseline.md` documents the initial contracts without
advancing the revision.

## 5. Licensing hygiene — how they treat other people's code

This is a cultural norm enforced by tooling, and it is thorough:

- The project itself is **MIT** (`LICENSE`), and `NOTICE` (an Apache-style
  notice file) credits adapted code source by source: llama.cpp/ggml
  (MIT), DS4 (MIT) and its GB10/GX10 fork, Qwen reference chat templates
  (Apache-2.0 — Gufo "implements a separate bounded renderer"), h3.c
  (MIT) with its ccv ancestry (BSD-3), ROCm components, hipCUB (BSD-3),
  the Flash-Next optimization adapted from an individual's fork at a
  named commit, the three Strix Halo llama.cpp inspiration forks, the
  Independent JPEG Group, and FFmpeg (invoked as separate executables;
  obligations remain with the invoker). It closes: weights are not
  included.
- `THIRD_PARTY_NOTICES.md` is the machine-checked inventory (dossier 02
  §10): component, relationship (linked / adapted / headers compiled in /
  reference), SPDX license, **pinned revision**, upstream link — for
  everything down to single Rust crates. `check-dependencies.py`
  validates it. `licenses/` keeps 25 full license texts, and every
  package installs `LICENSE` + `NOTICE` + the inventory under
  `share/licenses/gufo`. The notices file instructs: "Preserve embedded
  copyright notices when modifying adapted code."
- **Weight licenses are first-class**: the README's model table carries a
  license column (including the restrictive ones — Qwen Community License
  for Flash-Next, Qwen Research License *non-commercial* for Qwen-Image,
  MiniMax H3 Community License); extension authors must pin weights by
  hash and must not bundle weights they may not redistribute; registry
  review checks weight licenses explicitly.
- The registry review (dossier 03 §6) is licensing hygiene applied to
  strangers: no unreviewable binaries, third-party sources pinned and
  licenses noted, redistribution rights verified.

## 6. Credit practice

Credit is specific, pinned, and permanent: adapted code is credited to
the exact upstream commit in both `NOTICE` and the notices inventory; a
community member's fork optimization (mikealanni's Flash-Next GDN work)
is credited by name, repo, and commit hash in both files; copyright
notices of adapted code are preserved in place (e.g. Nathan Wilson's
notice retained in `licenses/strix-halo-llamacpp.txt`); the changelog
includes commit authors (`include-commit-authors: true` in the
release-please config); the blog names its reference projects and links
them. The reference-projects page (`docs/reference-projects.md`) is a
public thank-you list with one-line statements of what each project
taught them.

## 7. Community mores — voice, celebrations, refusals

From the blog and docs, in the project's own register:

- **The voice is plain, exact, and dry.** The blog exists, by its first
  post, for "what we learned along the way, the part that code, releases
  and benchmarks don't say" — and it is deliberately human-written:
  "Gufo is an inference engine heavily built with AI and our own ideas,
  and we're happy with that. This blog is the exception we want to keep:
  a channel from people to people. We write the posts ourselves… AI helps
  us correct and polish our English and build interactive playgrounds."
  That sentence is the project's whole AI etiquette in miniature: AI
  labor is normal and unhidden in the codebase; the human voice is
  reserved for the human channel.
- **What they celebrate:** squeezing one machine to its real limits;
  measurements with provenance; a community fork solving a problem
  upstream won't (Gufo RDMA is linked from the README and the homepage);
  an extension author shipping their own model without waiting for
  maintainers ("Nobody has to keep a fork alive" is an argument *for*
  extensions, framed as respect for fork authors' time).
- **What they refuse, stated as engineering law:**
  - an optimization that changes the output ("isn't one");
  - speed claims without the reference implementation run beside them,
    and margins widened to rescue noisy results;
  - models-as-breadth: they will not merge a model that isn't the best
    for its use case on this hardware — the refusal is published, with
    the extension system offered as the honorable alternative;
  - unaudited native code in the registry: review is whole-diff, human,
    and unhurried by tooling;
  - history and rationale in public docs; filler words; undated numbers.
- **Maintainer/contributor etiquette observable from the artifacts:**
  small single-purpose PRs with protocol titles; evidence attached to
  claims (quality files keep failures visible, including one explicitly
  "inconclusive" result whose cause is "not established"); design
  disagreements settled by written RFC with evaluated alternatives, not
  by thread volume; breaking changes announced in the title, never
  smuggled; releases frequent and mechanical so no single release is an
  event.

## 8. The doors an outsider actually has

- **Issues** (525 filed) — no template; a good issue here is presumably
  what their own docs model: exact, dated, with hardware/software
  identity and evidence. (The repo gives no template, so this is
  inference from their documentation norms, marked as such.)
- **Discussions** — enabled; the named use is design proposals for new
  Rust components (#864). Treat Discussions as the design-proposal door.
- **Pull requests** — gated by the title protocol, the format gate, the
  hosted checks, and the Devlab for behavior changes.
- **Your own extension repo** — the lowest-friction door of all: no
  upstream change needed; catalogue listing via the `gufo-extension`
  string; registry listing via a review PR in `gufo-org/gufo-extension`.
- **A named community fork** — the RDMA precedent: build it in the open,
  keep it current, and the project may name and link it without merging
  it.
- Not found in the tree as of `800ce328`: any Discord/forum/chat link in
  the repo docs (the lemonade fork's description carries a Discord link,
  but that is Lemonade's community, not Gufo's); any code of conduct or
  named moderation process; any security contact.

## 9. What this means for donating RuneForgeAI work back upstream

Volmarr's stated hope for the fork is: "We will try to donate back to the
project but we cannot know if they will like our crazy ideas!" Shaped by
everything above, an outside contribution is welcome here when it is:

1. **Scoped to their principles.** One machine (gfx1151), quality before
   speed, real workloads. A change that helps other hardware or trades
   output correctness for speed contradicts the project's constitution
   and should not be offered; a change that deepens Strix Halo quality
   or speed *with output preserved* is exactly their currency.
2. **An extension first, a core PR second.** The project's own design
   says: don't ask maintainers to upstream your model/variant — ship it
   as your own extension (template in `examples/extension_template`),
   prove it there, and let promotion-to-core be their decision under
   their criteria (fit, named maintainer, licensing review, platform
   evidence, core gates). Kernel or core fixes are the natural PR
   material; new models are extension material.
3. **Evidence-complete.** Quality report against an independent
   reference, benchmarks through HTTP against main with per-request/
   per-phase timings (never averaged), platform profile and temperatures
   recorded, failures and inconclusive results left visible. An
   optimization PR without its `QUALITY.md`/`BENCHMARKS.md`/
   `EXPERIMENTS.md` updates is unfinished by their norms.
4. **Protocol-exact in form.** Conventional-Commit single-line title
   with scope (and `!` if breaking); format gate run; smallest covering
   check run; new files staged before Nix builds; version/changelog
   untouched; public docs updated in the same PR if behavior changed —
   written in their voice (plain, dated numbers, no filler words, no
   history, no issue numbers) and within the line budgets.
5. **Licensing-clean.** Original work under MIT; any adapted code
   credited at commit granularity in `NOTICE`/`THIRD_PARTY_NOTICES.md`
   with license texts preserved; dependencies pinned exactly and
   recorded; weights never bundled, only pinned by hash.
6. **Patient with review.** Registry review reads the whole diff;
   Devlab gates compare against main on real hardware and treat missing
   evidence as error. A donation that arrives as several small,
   reviewable PRs (their RFC language: "reviewable PR boundaries") fits
   the project's grain; a single giant drop does not.
7. **Honest about AI authorship, in their way.** The project builds with
   AI openly and reserves human voice for human channels. Contributions
   written by agents are normal here — `AGENTS.md` governs them — but
   the *accountability* is a named, reachable maintainer's. Registry
   review requires reachable maintainers by name.

And the honest limit, from their own blog: some good work will still not
be upstreamed, because the best-model-per-use-case rule is a real filter.
The project's social contract treats that not as rejection but as the
reason extensions and named forks exist — the RDMA fork is linked from
their homepage, not merged, and is presented as a success of the model.

## Sources

- Tree at `800ce328`: `AGENTS.md` (root), `docs/AGENTS.md`,
  `src/core/rust/AGENTS.md`, `src/families/qwen/AGENTS.md`,
  `src/models/qwen/AGENTS.md`, `include/gufo/ext/changes/AGENTS.md`;
  `README.md` (contributing section); `NOTICE`; `THIRD_PARTY_NOTICES.md`;
  `licenses/`; `docs/reference-projects.md`;
  `docs/internal/releasing.md`, `docs/internal/extension-distribution.md`;
  `release-please-config.json`.
- Registry repo `gufo-org/gufo-extension`: `REVIEW.md`.
- gufo.blog: all three posts (blog index, 2026-11-15).
- GitHub API community profile, 2026-11-15 (absence of CoC/contributing/
  templates verified there and by tree listing).
