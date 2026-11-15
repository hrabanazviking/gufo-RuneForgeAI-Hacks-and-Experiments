# Gufo Deep Study — Index and Method

**Subject:** Gufo, the open-source inference engine for AMD Strix Halo, by the
gufo-org project on GitHub (https://github.com/gufo-org/gufo).
**Commissioned by:** Volmarr Wyrd, 2026-11-15, for the RuneForgeAI fork
`hrabanazviking/gufo-RuneForgeAI-Hacks-and-Experiments`.
**Study date:** 2026-11-15.
**Upstream tree studied:** a fresh clone of `gufo-org/gufo`, HEAD
`800ce3280201e94104cfff9d310837ab6a6f3d95`, `version.txt` = **0.34.0**
(released 2026-11-11). Every claim in these dossiers was checked against that
tree or against the project's own live pages/APIs on the study date; where a
number comes from the GitHub API or the website rather than the tree, the
dossier says so.

## What this corpus is

Six dossiers, written to stand alone, each with its own sources section:

| File | Contents |
| --- | --- |
| `00-INDEX.md` | This map: how the study was gathered, reading order, evidence conventions. |
| `01-THE-PROJECT.md` | What Gufo is; its four principles; the model curation method; the quality-gate method; architecture (single binary, per-model kernels, continuation cache for coding agents, speculative decoding, extension architecture, the RDMA community fork, reference projects). |
| `02-LANGUAGES-AND-METHODS.md` | Every language in the tree with measured share and role; toolchains (Nix, CMake presets, vcpkg, Rust 1.88); build roads per platform; testing method; benchmarking method; formatting/linting; dependency discipline. |
| `03-PROJECT-PROTOCOLS.md` | How the project operates: release-please flow, versioning, changelog discipline, versioned docs, the extension registry/review/trust model, `extensions.lock`, issue/PR flow, CI gates and the Devlab, the agent skills the project ships, design RFCs, security handling (and its gaps). |
| `04-RULES-AND-SOCIAL-PROTOCOLS.md` | The social layer in full: the `AGENTS.md` rulebooks rule by rule, the documentation constitution, contributing norms and tone, licensing-hygiene culture, credit practice, community mores from the blog, and exactly how an outside contribution must be shaped to be welcome — written for Volmarr's stated hope of donating RuneForgeAI hacks back upstream. |
| `05-WHAT-IT-MEANS-FOR-US.md` | Synthesis for our road: Gufo on purpleraider under the no-Docker law; how its continuation cache compares with the Ollama Memory Forge and Aesir residency findings; the ASR/TTS bearing on the Voxta SenseVoice gap; fork etiquette — what stays private, what could go upstream, and how. |

**Reading order:** 01 for the machine, 02 for the craft, 03 for the
operations, 04 for the people and the rules, 05 for what we do with it.

## How the study was gathered

1. **The tree itself, read directly.** The full documentary layer of the
   clone: `README.md`; all six `AGENTS.md` files (root, `docs/`,
   `include/gufo/ext/changes/`, `src/core/rust/`, `src/families/qwen/`,
   `src/models/qwen/`); `CLAUDE.md` (a symlink to `AGENTS.md`; `docs/CLAUDE.md`
   and `.claude/skills` are symlinks too); the public docs (`docs/*.md`,
   `docs/models/*.md`); the internal docs (`docs/internal/` — development,
   testing, benchmarks, cache, server, performance, releasing, CI, extension
   distribution, extension conformance, NPU, design RFCs); `NOTICE`;
   `THIRD_PARTY_NOTICES.md`; `licenses/`; `extensions.lock`;
   `api-series.json`; `Cargo.toml` and `rust-toolchain.toml`; `vcpkg.json`;
   `CMakePresets.json`; `release-please-config.json`; the nine GitHub
   workflows under `.github/workflows/`; the shipped agent skills under
   `.agents/skills/`; the extension template under `examples/`; the tools
   inventory under `tools/ci/`. Tree shape was measured with `git ls-files`
   (2,229 tracked files).
2. **The project's own live surfaces.** gufo.blog (homepage and all three
   blog posts, read in full or in substance); the extension registry repo
   `gufo-org/gufo-extension` (its `REVIEW.md`, PR template, and index read in
   full); the org's other repos (`toolboxes`, `website`, `nixpkgs`,
   `lfm3-gufo-extension`, `hrx-system`, a `lemonade` fork).
3. **The GitHub API (unauthenticated reads).** Repository facts, language
   byte counts, the community profile, the contributor list (63 accounts),
   the release list (41 releases), issue/PR totals (525 issues, 691 PRs, 566
   merged PRs at study time), and the org profile.

Nothing was joined, posted, filed, or forked for this study; the only writes
are these dossiers, their banking into Volmarr's fork on branch
`yrsa/gufo-deep-study`, and the distilled craft skill
`~/workspace/custom-skills/gufo-expertise/SKILL.md`.

## Evidence conventions

- Claims cite the file or page they come from, so any reader can re-check
  them against the clone at the HEAD above.
- Direct quotations are short and attributed; everything else is described in
  the study's own words.
- Where the project does **not** have a thing Volmarr asked about, the
  dossier says "not found in the tree as of `800ce328`" rather than guessing.
  The notable absences, all verified: **no `CODE_OF_CONDUCT.md`, no
  `CONTRIBUTING.md`, no `SECURITY.md`, no issue templates, and no pull
  request template in the main repository** (the registry repo does have a PR
  template). GitHub's community profile for the repo scores 37% for exactly
  these reasons. The rules that other projects put in those files live in
  Gufo's case inside `AGENTS.md` and the internal docs — dossier 04 covers
  them there.
- Numbers from forks' READMEs (e.g. third-party benchmark figures circulating
  in fork copies) are **not** cited as upstream results; upstream speed and
  quality numbers come only from `docs/` and `docs/internal/` at the studied
  HEAD.
