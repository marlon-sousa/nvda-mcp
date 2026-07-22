# Spec 0012 — packaging/release: per-component tagging + bridge release (entry 12a)

Implementation contract for ROADMAP entry 12a (split off entry 12, agreed
2026-07-22). Authored on the entry's branch per process; the spec rides in the
implementing PR.

> **Process note, 2026-07-22.** Entry 12 read "Spec: none yet → specify when
> reached", so the next step was a spec conversation. The workflows were written
> first on this branch and the spec follows on the same branch, after the
> decisions below were agreed in conversation. The ordering was wrong; the
> record is not. Every "Decided" below was settled in that conversation, and
> nothing here was reverse-engineered from the code.

## Goal

Entry 12 covers packaging and release for the whole repository. This entry
delivers the **bridge half** and the **tagging scheme all components will
share**, leaving server distribution (still undecided per spec 0005) to 12b.

Three things:

1. **A release path for the add-on** — a tag produces a reviewed GitHub release
   carrying the `.nvda-addon`, with notes and a version that cannot disagree
   with `buildVars`.
2. **A build on every relevant PR** — the packaged add-on, downloadable from the
   PR, so a reviewer or the live-NVDA checklist installs the exact build under
   review instead of building it by hand.
3. **A tagging scheme that survives more components** — the repository is
   `screen-readers-mcp`; spec 0005 commits to more bridges. The scheme must let
   the server and each bridge release on their own cadence from day one.

## Decided

- **Per-component tags, prefixed: `<component>-v<semver>`.** `nvda-bridge-v0.2.0`
  releases the add-on; `server-v0.3.1` will release the server. A git tag is a
  whole-repo ref — there is no such thing as tagging a subdirectory — so the
  prefix is pure convention, given meaning by the workflow's trigger filter. A
  single bare `vX.Y.Z` namespace was rejected: one release workflow would have to
  guess which component to build, and the two could never carry different version
  numbers.
- **A dash, not a slash.** `nvda-bridge/v0.2.0` (the Go-module convention) is
  URL-encoded as `%2F` in the release asset download URL. That URL is what the
  NV Access add-on store entry links to and what `README.tpl.md` builds. Not
  worth the encoding hazard on the most user-facing link the project has.
- **The version lives in `buildVars.addon_version` and nowhere else.** The tag
  does not introduce a second copy: it is an *assertion*, and the release
  workflow re-reads `buildVars` and fails the release if the two disagree. The
  same rule will apply to the server against its `pyproject.toml`. `buildVars`
  is importable with plain Python (it pulls only `site_scons` typings/utils, not
  SCons), so reading it costs one step and no build environment.
- **Release notes come from `buildVars.addon_changelog`, not the tag
  annotation.** Same reason: `addon_changelog` is already the text the add-on
  store shows as "what's new", so one edit serves both, and the release body
  cannot drift from the store listing.
- **Compatibility is protocol-keyed, so components release independently.**
  `hello` compares `PROTOCOL_VERSION` and never compares component versions
  (`domain/controllers/commands/hello.py`). Bridge 0.4.0 and server 0.9.0
  interoperate if both speak protocol 1. Therefore: no lockstep tagging, no
  combined release tag, and **every release states the protocol version it
  speaks** — that is the fact a user needs, and tags cannot express it.
- **Tags are pushed by a human; the workflow reacts.** Release-on-merge
  (watching `buildVars.py` on main and releasing when the version changes) was
  considered and rejected on three counts. One, a protocol change touches
  `shared/`, `mcpServer/` and `bridges/nvda/` together — `sync_shared.py`
  guarantees that coupling — so one merge would fire several release workflows
  concurrently. Two, it makes editing `buildVars.py` a publishing act, when that
  file also holds the description, the changelog and the NVDA compatibility
  range. Three, it welds "version bumped" to "ready to ship", removing the gap
  where a release waits on the store or on a co-ordinated server release.
- **Three validation layers, because each catches a different mistake.**
  GitHub's `tags:` trigger takes **glob filter patterns, not regex** — no
  anchoring, `.` is literal — so the glob only *routes*. A strict regex in the
  first step *validates* the shape. Reading `buildVars` *verifies* the content.
- **The tagged commit must be an ancestor of `main`.** Stops a tag pushed from a
  feature branch publishing unmerged code. Requires `fetch-depth: 0`, since the
  default depth-1 checkout has no ancestry to test.
- **Releases are published as drafts.** Once the store entry points at a
  download URL, replacing a bad asset is painful. The draft is the review gate;
  publishing is a deliberate human act.
- **Merge gates stay unconditional; only the artifact build is path-filtered.**
  `ci.yml` already warns that branch protection matches required checks by
  literal job name, so a path-filtered *required* job parks every PR that misses
  the filter on "Expected — waiting for status to be reported". Splitting gate
  from artifact is what makes path filtering safe: `ci.yml`'s three jobs keep
  running on every PR, and the artifact build is a separate, non-required
  workflow. **`build .nvda-addon` must never be added to branch protection.**
- **`shared/**` is in the artifact path filter.** `sync_shared.py` copies the
  wire module into the addon, so a change under `shared/` genuinely changes the
  built add-on. Filtering on `bridges/nvda/**` alone would miss it.
- **The PR comment is a separate `workflow_run` workflow.** The build runs with
  a read-only token on fork PRs and cannot comment. `workflow_run` runs in the
  base repo's context with write access. Because it only fires when the build
  ran, the path filter governs the comment too. Adapted from the
  EnhancedDictionaries workflow of the same name.
- **`README.md` is versioned and drift-gated.** It is generated from
  `README.tpl.md`, but it is what GitHub renders for the add-on directory and
  what the store entry links to, so it is tracked (see PR #24). Both the
  artifact and release workflows regenerate it and fail on any diff. The check
  is deliberately *not* a required `ci.yml` job: making it one would mean
  building the add-on on every PR including ones touching only `mcpServer/`,
  which defeats the path filtering. It turns the PR red wherever drift can
  plausibly occur, and hard-blocks the release.
- **Add-on store submission stays manual.** NV Access rejects submissions
  created through the `gh` CLI or freeform issue bodies; the `registerAddon`
  issue form must be filled in a browser. The `submit-nvda-addon` skill handles
  it after the draft is published.
- **Never link `/releases/latest/download/...`.** GitHub's latest-release
  pointer is singular and repo-wide, so a server release would take the badge
  from the add-on. `README.tpl.md` builds an explicit versioned URL.

## Deliverables

### 1. `.github/workflows/release-nvda-bridge.yml` — the release path

Triggers on `push` to tags matching the glob `nvda-bridge-v*`. Runs on
`ubuntu-latest`. Steps, in order, each failing the release on its own:

1. Checkout with `fetch-depth: 0` (ancestry for step 3).
2. Validate the tag against `^nvda-bridge-v[0-9]+\.[0-9]+\.[0-9]+$`; export the
   version as a step output.
3. Fail unless the tagged commit is an ancestor of `origin/main`.
4. Install `gettext`, Python 3.13, and `scons markdown pytest`.
5. Fail unless `buildVars.addon_version` equals the tag's version.
6. `sync_shared.py`, then `pytest`.
7. `scons`.
8. Fail unless `README.md` regenerated byte-identical.
9. Compose notes: `addon_changelog`, then the `PROTOCOL_VERSION` read from
   `shared/nvda_mcp_wire/protocol.py` and a sentence stating that any server
   speaking it will pair.
10. `gh release create --draft --verify-tag`, asset
    `bridges/nvda/nvdaMcpBridge-<version>.nvda-addon`.

### 2. `.github/workflows/addon-artifact.yml` — the PR build

Triggers on `pull_request` filtered to `shared/**`, `bridges/nvda/**`, and its
own file, plus `workflow_dispatch`. Runs `sync_shared.py` and `scons`, stamps
the build date into the file name (`nvdaMcpBridge-0.1.0_20260722.nvda-addon`) so
builds are distinguishable on the PR, checks README drift, and uploads with
7-day retention. The artifact **name ends in `.nvda-addon`** — deliverable 3
finds it by that suffix. Not a required check.

### 3. `.github/workflows/comment-pr-artifact.yml` — the PR comment

`workflow_run` on `["Addon artifact"]`, `completed`, restricted to runs whose
originating event was `pull_request`. Upserts one comment per PR, marked with an
HTML comment, holding one section per commit (newest first, capped at 20), each
with the commit, date, build conclusion and artifact link. Re-running the same
commit replaces that commit's section. Resolves the PR through the head
owner/branch first, because `workflow_run.pull_requests` is empty for fork PRs.

### 4. Documentation

`README.md` (root) gains a short "Releasing" section: the tag format, the one
command, and a pointer here. `ROADMAP.md` entry 12 splits into 12a and 12b.

## File layout summary

| File | Role | Required check |
|---|---|---|
| `.github/workflows/release-nvda-bridge.yml` | Tag `nvda-bridge-v*` → draft release with the `.nvda-addon` | n/a (tag-triggered) |
| `.github/workflows/addon-artifact.yml` | PR → packaged add-on, path-filtered | **No — never add** |
| `.github/workflows/comment-pr-artifact.yml` | Build → PR comment with the download link | n/a (`workflow_run`) |
| `.github/workflows/ci.yml` | Unchanged; keeps the three unconditional gates | Yes (existing) |

## Acceptance criteria

1. Pushing `nvda-bridge-v<version>` where `<version>` equals
   `buildVars.addon_version`, on a commit merged to `main`, produces a draft
   release whose single asset is `nvdaMcpBridge-<version>.nvda-addon` and whose
   body is the changelog plus the protocol-version sentence.
2. A tag whose version disagrees with `buildVars` fails, and publishes nothing.
3. A malformed tag (`nvda-bridge-v1.2`, `nvda-bridge-v1.2.3-rc1`) fails at the
   regex step.
4. A tag on a commit not merged to `main` fails.
5. A PR touching only `mcpServer/` runs no add-on build and produces no comment,
   and is not blocked waiting for one.
6. A PR touching `shared/` or `bridges/nvda/` produces a downloadable add-on and
   a comment linking it; a second push to the same PR updates that comment
   rather than adding one.
7. A PR editing `README.tpl.md` without committing the regenerated `README.md`
   fails the artifact build.
8. `ci.yml`'s three job names are unchanged, so branch protection is untouched.

## Out of scope

- **Server distribution (entry 12b).** Spec 0005 still has the implementation
  language open (Python + PyInstaller vs a Go port judged against the published
  wire contract), plus the umbrella-installer and `.mcpb` questions. The
  `server-v*` tag namespace is reserved here; the workflow is deliberately absent
  rather than half-written.
- **Automated add-on store submission** — see Decided.
- **Code signing** of the `.nvda-addon`, and any release channel other than
  GitHub releases.
- **Version bumping itself.** Handled by the `bump-nvda-addon` skill, which
  edits `buildVars` and opens the bump PR. Its only divergence in this
  repository is that the tag it pushes gains the `nvda-bridge-v` prefix.

## Definition of done

The three workflows exist, `ci.yml` is unchanged, the root README documents the
tag format, ROADMAP entry 12 is split with 12a marked Done, and this spec is on
main. Acceptance criteria 1 through 4 are provable only by tagging a real
release; they are verified on the first bridge release rather than in this PR.
