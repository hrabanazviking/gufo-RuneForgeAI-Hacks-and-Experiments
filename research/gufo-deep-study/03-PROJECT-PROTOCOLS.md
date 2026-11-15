# 03 — Project Protocols: How Gufo Operates Day to Day

Sources: upstream tree at `800ce328` — `docs/internal/releasing.md`,
`docs/internal/ci.md`, `docs/internal/development.md`, `docs/versions.md`,
`docs/internal/extension-distribution.md`, the registry repo
`gufo-org/gufo-extension` (`REVIEW.md`, PR template, index), `.github/`,
`release-please-config.json`, `CHANGELOG.md`; GitHub API. See `00-INDEX.md`.

## 1. The shape of the operation

Gufo runs as a small maintainer-led project with heavy automation. At study
time: 63 contributor accounts, but two authors (francescobozzo,
fedeizzo) account for ~650 of the contributions, with a release bot
(`gufo-release-bot[bot]`, 40) doing mechanical release work. Flow volume is
high for the size: 691 PRs (566 merged) and 525 issues in the project's
first ~3 months, 41 releases in the same span — roughly a release every
two to three days at the current cadence (v0.24.0 on 2026-10-25 through
v0.34.0 on 2026-11-11).

## 2. Versioning and the release machine

**Semantic versioning over the documented surface** (`docs/versions.md`):
the version covers the documented CLI, the HTTP API, and the public Nix
flake outputs; a breaking change is "something documented stops working
without a change on your side." Pre-1.0: fixes and performance work bump
the patch, features *and* breaking changes bump the minor. Post-1.0,
breaking means major. The changelog marks breaking changes explicitly.
Channels: GitHub releases `vX.Y.Z` (source + .deb + Windows ZIP), container
images `X.Y.Z` / `X.Y` / `latest` (plus `edge` and `sha-<revision>` for
development), and the Nix flake at `github:gufo-org/gufo/vX.Y.Z`. **"A
released version never changes."** Development builds report their exact
Git revision in `gufo --version`. The docs site keeps the **ten newest
releases frozen** plus a `development` version that follows main.

**Release-please runs everything** (`docs/internal/releasing.md`,
`release-please-config.json`, `.github/workflows/release-please.yml`):

- Ordinary PRs **never** edit `version.txt`, `CHANGELOG.md`, or the
  release-please manifest — the automation owns them. Version 1.0.0 "is an
  explicit decision, never automatic."
- The workflow is **manual only** (`workflow_dispatch`; no schedule): a
  maintainer runs "Release automation" from the Actions tab. It opens or
  updates a release PR that bumps `version.txt`, `CHANGELOG.md`, and the
  manifest from the Conventional Commit history, and runs normal CI plus
  the full Devlab functional tier.
- The workflow waits up to **160 minutes** for the title check, the repo
  checks, and `devlab/functional`. On failure or timeout it leaves the PR
  open and comments. On pass it squash-merges the release PR, tags
  `vX.Y.Z` (tags never move), creates the GitHub Release, and dispatches
  the `gufo-release` event to the **toolboxes** repo and the website.
- **Publishing** (in toolboxes, `publish_release.yml`): container images
  from the tag; the Windows ZIP built by the reusable `windows-build.yml`
  against the tag, verified (`gufo.exe --version` + diagnostics with only
  the bundled runtime on PATH) and attached with a `.sha256`; the **Debian
  package** `gufo_<version>-1_amd64.deb` for Debian 13, verified in a fresh
  container, attached with checksum. Uploads go through a dedicated GitHub
  App (Contents write; `RELEASE_APP_CLIENT_ID` / `RELEASE_APP_PRIVATE_KEY`
  secrets in toolboxes) and **never overwrite existing assets**; manual
  workflow inputs exist to rebuild one release or recover a single asset.
- **Docs publishing:** the website's `sync-docs.yml` copies the public docs
  at the tag into a new frozen site version (ten kept); `docs-website.yml`
  refreshes the `development` docs on main pushes that touch public docs.
- **Changelog shape** (`CHANGELOG.md`, release-please generated): a
  "Notable user-facing changes" framing; sections ⚠ BREAKING CHANGES,
  Features, Bug Fixes, Performance, Documentation, Code Refactoring
  (build/ci/test/chore/style are hidden by config); each entry is the PR's
  Conventional Commit title with scope, an issue link, and a commit
  short-SHA link. Example from 0.34.0: "audio: decode EmbeddingGemma 2
  audio in Rust and drop libsndfile and soxr (#1118)".

## 3. The PR title protocol — the project's smallest strict law

`docs/internal/releasing.md` defines it and `tools/ci/check-pr-title.py`
enforces it — and the checker's test **reads the type table and the
examples from the doc itself**, so doc and enforcement cannot drift.

- Form: `<type>[(scope)][!]: <description>`, single line.
- Types and their version effect: `fix` → patch; `perf` → patch; `feat` →
  minor; `docs`, `test`, `build`, `ci`, `chore`, `refactor`, `style` → no
  bump by default; `revert` inherits the reverted change's effect. The
  largest bump across a release wins.
- Scope is short, lowercase, and exists to give ownership context
  (e.g. `feat(server)!: remove the legacy completion endpoint`).
- **The breaking mark must be in the title**: the footer is lost in the
  squash merge, so `!` in the title is the only breaking signal that
  survives into the changelog.
- Squash merge is the merge method, and the squash retains the PR title —
  which is why the title *is* the changelog entry and the commit message
  (root `AGENTS.md`: "Conventional Commits single-line").

## 4. Issue and PR flow — what exists and what does not

Verified against the tree and the GitHub community-profile API at
`800ce328`:

- **No issue templates, no PR template, no `CONTRIBUTING.md`, no
  `CODE_OF_CONDUCT.md`, no `SECURITY.md` in the main repository.** The
  `.github/` directory contains only `actionlint.yaml` and `workflows/`.
  GitHub's community profile scores the repo **37%** (description, license,
  and readme present; code of conduct, contributing, issue templates, and
  PR template absent). These are facts about the tree, stated here because
  Volmarr asked what protocols exist — the project's norms live in
  `AGENTS.md` and the internal docs instead (dossier 04).
- **Discussions are enabled**, and at least one process routes there by
  rule: a new Rust component must be proposed in **Discussion #864** before
  work starts (`src/core/rust/AGENTS.md`).
- The **registry repo is the exception**: `gufo-org/gufo-extension` has a
  pull request template — the author's checklist for a registry release
  (release + commit, source license, weight licenses, maintainers, build
  platforms + Gufo revision, evidence; for updates, the changes since the
  previous release). See section 6.
- Practical flow for a code change, assembled from `AGENTS.md` +
  development.md + ci.md: stage new files in git first (Nix flakes see
  only tracked files); run the format gate before committing C++; run the
  smallest check that covers the change; expect the hosted checks, the PR
  title check, the Windows build, and — for anything touching shipped
  behavior — the Devlab functional gate on real Strix Halo hardware; use
  `gh` for GitHub operations after `gh auth status`; prefer `jj` (Jujutsu)
  over git when available (both are in the dev shell).

## 5. CI gates — hosted checks plus a hardware Devlab

Nine workflows (`.github/workflows/`, triggers verified):

| Workflow | Trigger | Job |
| --- | --- | --- |
| `checks.yml` | push, pull_request | "Repository checks" — hosted Ubuntu: format, docs, dependency inventory, server-command checks, CPU contract suite via `nix flake check`; also warms the Linux package cache on main |
| `linux-build.yml` | reusable (`workflow_call`) | Linux package build used by checks and Devlab |
| `windows-build.yml` | reusable | Windows package build (also called by toolboxes releases) |
| `devlab-windows.yml` | push, pull_request | GitHub Windows build → Devlab Windows Strix Halo: GPU diagnostics + model smoke on the same run's bundle |
| `devlab-linux.yml` | pull_request, manual | Authorize/select → build candidate **and main** → run Linux model checks on Devlab Strix Halo → publish results + the `devlab/functional` status |
| `devlab-comment.yml` | `workflow_run` | Keeps the PR's Devlab comment current, including for forks, without running PR code |
| `pr-title.yml` | pull_request | The title protocol of section 3 |
| `docs-website.yml` | push to main touching public docs, manual | Dispatches docs refresh to the website |
| `release-please.yml` | **manual only** | Section 2 |

**The required ruleset on main** (`docs/internal/ci.md`) requires five
status contexts: "Run CPU and repository checks", "Validate PR title",
"Build / Windows package", "Run Windows model checks", and
`devlab/functional`. A context is caller-job + leaf-job name, so renaming
a job means updating the ruleset, `release-please.yml`, and
`devlab-comment.yml` in the same change — ci.md says so explicitly.

**The Devlab is the project's hardware truth.** Hosted CI never builds
ROCm or runs model oracles; the Devlab (self-hosted Strix Halo machines,
Linux and Windows) runs the functional tiers. Its verdict rules are
strict (`docs/internal/ci.md`): `devlab/functional` **fails on correctness
failures and on checked phases consistently slower than main**; missing or
incomparable evidence is an **error**, not a pass; noisy but complete
comparisons pass with a visible warning. This applies to ordinary and
release PRs alike.

**Cache discipline:** repo checks use a compiler cache + Cachix + Magic
Nix Cache with a fresh key each run; PR builds do not push to Cachix (the
main-branch warming job exists for that reason); Windows caches the SDK
archive, a compiler cache, and the vcpkg binary cache; Devlab runners
download verified bundles from the hosted builds rather than rebuilding.

**Boundary gates** (CTest, labelled `cpu;repository`, in the hosted
selection): `check-extension-isolation.py --fail-on-serving-boundary`
(extensions never reach into serving), `check-target-graph.py` over the
build's `gufo-link-graph.json` (transitive link closure of every
`library.json` library plus core/cache/ext-runtime; only allow-listed HIP
libraries may be absent, and only with `hip: false` recorded), and
`ext_runtime_neutral_contracts_test` (builds the extension runtime in an
isolated fixture project linking only `gufo_ext_runtime` + OpenSSL). A
separate hosted Windows job checks extension contracts with ClangCL and
only OpenSSL from the vcpkg baseline — no HIP SDK needed.

## 6. The extension registry, review, and trust model

This is the project's most fully documented social protocol
(`docs/extensions.md`, `docs/internal/extension-distribution.md`, registry
`REVIEW.md`).

**Discovery.** The public catalogue at gufo.blog/extensions lists GitHub
repos that a search for the string `gufo-extension` finds — authors put
that string in their repo name or description to be listed. Listing in the
catalogue is not review.

**The registry** (`github.com/gufo-org/gufo-extension`) is what
`gufo extension install <name>` consults: an `index.json` plus one JSON
file per extension (four listed at study time: `deepseek41flash`, `flint`,
`lfm3`, `strycast_qwen35moe`), a JSON schema, and `tools/registry.py`.
Install flow: fetch the registry index from `raw.githubusercontent.com`,
pick the newest release compatible with the host platform and the host's
extension-API series, install `<source>@<revision>`, and **abort unless
the downloaded source matches the reviewed digest**. `GUFO_EXTENSION_
REGISTRY` can override the registry URL/file.

**What "reviewed" means** (registry `REVIEW.md`, the operative text): "A
release enters the registry only after a Gufo maintainer reviews its
source at the listed commit and approves the pull request. The approval is
the record of the review." The reviewer reads the **whole diff** since the
previous reviewed release (the whole tree for a new extension) against a
published checklist:

- **No code beyond stated purpose** — nothing that reaches the network,
  launches processes, reads or writes files outside model/cache/user-named
  paths, collects telemetry, or hides behavior. The review explicitly
  includes `extension.cmake` and everything it includes, because CMake
  runs at install time with the user's permissions.
- **No prebuilt binaries or downloads** — no vendored objects, libraries,
  generated blobs, or build-time downloads the review cannot read;
  third-party sources pinned, licenses noted.
- **Public surface only** — only `<gufo/ext/...>` headers and public
  `gufo_ext_*` targets; every included library declared in `packages`
  (headers that happen to be on the include path do not count).
- **Truthful metadata** — manifest fields match the source.
- **Licenses** — the license must allow redistribution and use; weights
  are not bundled without the right.
- **Accountability** — listed maintainers must be reachable.

`tools/registry.py verify` performs only the mechanical checks (commit
exists at the source, manifest fields match, digest matches): "It does not
replace reading the code." Registry releases are immutable — a fix is a
new release; withdrawal is its own reviewed PR explaining why, and `gufo`
warns users about installed releases no longer listed. The public docs
carry the standing warning, verbatim in spirit: an extension is native
code running with your permissions and its build scripts run when it
builds — install only source you have read or authors you trust, pinned to
an exact revision; **"Review protects against malicious or careless code;
it isn't a sandbox."** Unreviewed sources (a git URL or local directory)
install only with a warning and interactive confirmation (`--yes` for
non-terminal use), and a git URL must name a commit or tag.

**`extensions.lock` and build selection.** Three selection modes
(`docs/internal/releasing.md`): **discovery** (default `nix build`, CMake
presets, Devlab — every extension found), **lock** (`.#release`, the
release-tag Windows ZIP — exactly `extensions.lock`, validated at every
configure), and the **toolboxes images** (currently the default package
with the release version — the doc notes, as an open item, that today the
in-tree set equals the locked set "but nothing enforces it; switching
Toolboxes to lock mode is open"). Hosted CPU checks build a real lock-mode
executable and reject artifact-key, option-name, and model-ID collisions
between shipped and unshipped extensions — but they "don't establish HIP
behavior," so provider-affecting changes also need functional, numerical,
and performance gates on the shipped lock-mode HIP build.

**Module lifecycle.** A module is bound to one exact build identity (hash
of API headers + version, compilers, ROCm, global flags, GPU arch, build
type, sanitizers); modules are never unloaded from a running process;
after a Gufo upgrade, `gufo extension list` shows `needs update` and the
module is skipped until `gufo extension update` rebuilds it from its
pinned source. The store is `$GUFO_EXTENSIONS_DIR` or
`~/.local/share/gufo/extensions`. Removal deletes files; running processes
keep using the module until they exit. On Windows, modules are DLLs that
load only into `gufo.exe`, and the manifest declares supported platforms.

**Promotion to core** requires: fit with the model-selection goals, a
named maintainer, licensing + dependency review, public-header isolation,
platform evidence, and the core gates. "Passing a suite, a registry
listing or a third-party image doesn't promote an extension."
`docs/internal/extension-conformance.md` lists the evidence an author must
supply (contracts and workloads, repository checks, the template).

## 7. The extension API change protocol

Public-contract changes follow their own paper trail
(`include/gufo/ext/changes/AGENTS.md`, `docs/internal/releasing.md`):

- Any change to the extension API's SURFACE closure, the manifest schema,
  or public CMake contracts needs the **`ext-api` label** and **one new,
  uniquely named, immutable Markdown record** under
  `include/gufo/ext/changes/<major>.<minor>/`. The filename is descriptive
  (a feature or issue identifier is fine; **no version or revision numbers**
  in filename, heading, or description). The record states the concrete
  contracts changed and the compatibility/rebuilding implications — no
  implementation history, no test logs. Merged records are **permanent and
  immutable**; `baseline.md` documents the initial contracts without
  advancing the revision.
- After editing extension headers, run
  `python3 tools/ci/check-extension-api.py --write`.
- The revision of the API is *derived*: `revision_base` (in
  `api-series.json`, currently series 0.3, base 0) plus the count of
  records in the active series directory (excluding `baseline.md`).
  In-tree extensions are fixed in the same PR as any API change.
- Experimental hooks (under `include/gufo/ext/experimental/`) graduate
  only by explicit review after **60 unchanged days**. Post-1.0, an
  adapter for the previous major must be provided for ≥60 days where
  feasible, with configure-time deprecation reports.

## 8. Design by RFC, in the open

Significant design work happens as RFC documents inside the repo
(`docs/internal/design/`): the cache redesign RFC (evaluating llama.cpp-,
SGLang-, and vLLM-like approaches against Gufo's design, with a comparison
table, success criteria, an acceptance contract, risks, instrumentation,
an implementation plan with "reviewable PR boundaries," and an evidence
appendix) and the model-extensions RFC. The documentation constitution
(dossier 04) routes all design rationale to `docs/internal/design/` —
public pages never carry it.

## 9. The agent skills the project ships

Gufo ships its own working procedures as agent skills under
`.agents/skills/` (also linked from `.claude/skills`, a symlink to
`../.agents/skills`): **`benchmark-model`** (30,752 bytes) and
**`optimize-kernel`** (14,372 bytes), each with frontmatter
`metadata.origin: gufo`. Their content is covered in dossier 02 (§4, §8);
their existence is the protocol point: the project treats coding agents as
first-class contributors whose procedures are versioned, reviewed
artifacts of the repo — the same status `AGENTS.md` itself has (every
`CLAUDE.md` in the tree is a symlink to an `AGENTS.md`).

## 10. Security handling — documented pieces, no security policy

What exists: the extension trust model above; install-time digest
verification; the hardening recipe for running third-party extensions
(network namespace with only loopback, read-only files except `/tmp` and
the cache dir, no capabilities, no new privileges, unlimited memlock,
`/dev/kfd` + DRM nodes with `video`+`render` groups — with the explicit
note "This limits what an extension can reach; it isn't a sandbox"); the
no-authentication warning for the server (reverse proxy with TLS + access
control for any remote exposure); artifact-retention rules for published
builds (Gufo + extension revisions, toolchain, build options,
`extensions.lock`, model artifact identities, install inventory,
capability results, image digest/ZIP checksum — recorded from the
installed binary's own `--version` and `diagnose` output, "not another
gufo from PATH"); and `tools/extensions/check_install.py`, which hashes
the installed binary and required files and can `--require-clean-
revision`.

What does **not** exist as of `800ce328`: a `SECURITY.md`, a documented
vulnerability-disclosure address or process, and a code of conduct (see
dossier 04). Anyone needing to report a security issue has no in-repo
channel named for the purpose; the observable doors are GitHub issues and
Discussions.

## Sources

- Tree at `800ce328`: `docs/internal/releasing.md`, `docs/internal/ci.md`,
  `docs/internal/development.md`, `docs/internal/extension-distribution.md`,
  `docs/internal/extension-conformance.md`, `docs/versions.md`,
  `docs/extensions.md`; `include/gufo/ext/changes/AGENTS.md`;
  `api-series.json`; `extensions.lock`; `release-please-config.json` +
  `.release-please-manifest.json`; `CHANGELOG.md`; `.github/workflows/`
  (all nine) + `.github/actionlint.yaml`; `AGENTS.md` (root).
- Registry repo `gufo-org/gufo-extension`: `REVIEW.md`,
  `.github/pull_request_template.md`, `index.json`, `extensions/*.json`,
  `tools/registry.py`.
- GitHub API, 2026-11-15: community profile (37%), repo facts, search
  counts (issues 525, PRs 691, merged 566), contributors.
