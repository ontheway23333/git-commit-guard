# Documentation Lifecycle v1

This reference defines the normative lifecycle for repository-managed engineering documents. Read it completely before creating, editing, transitioning, validating, indexing, or adopting managed documents.

## Contents

1. Scope and recognition
2. Normative invariants
3. Directory and path projection
4. Canonical frontmatter schema
5. Identity, dates, and slugs
6. State machines
7. Content contracts
8. Generated-document rules
9. Relationships and successors
10. Atomic transition protocol
11. Validation model
12. Index and registry
13. Project configuration
14. Legacy adoption and exemptions
15. Git and commit integration
16. CI and pre-commit integration
17. CLI reference
18. Prohibited behavior

## 1. Scope and recognition

Documentation Lifecycle governs engineering-intent records whose state must remain recoverable from the repository:

- implementation plans and design plans;
- migration plans and operational migration runbooks;
- breaking-change or rollout plans;
- reproducible generated audits, inventories, reports, snapshots, and benchmarks.

A Markdown file is lifecycle-managed when its frontmatter has an immutable `id`. Once managed, missing required metadata is an error; removing or changing the ID does not make the document legacy again.

Files without a managed ID remain legacy/exempt by default. Common exemptions include:

- `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `LICENSE`;
- `CODE_OF_CONDUCT.md`, `AGENTS.md`, and `SKILL.md`;
- package READMEs, vendor/third-party documentation, and ordinary reference prose.

The lifecycle applies only to documentation. Never treat executable migration source as managed documentation merely because a directory or filename contains “migration.” Examples outside scope include `database/migrations/*.php`, `migrations/*.sql`, ORM migration modules, and deployment executables.

## 2. Normative invariants

The following are hard v1 invariants:

1. Every managed document has one globally unique immutable ID.
2. A path is a mutable locator, never document identity.
3. `created_at`, the filename creation date, and `slug` do not change after creation.
4. Frontmatter is the source of truth; filename and directory must agree with it.
5. A status change updates metadata, filename, directory, links, index, and registry as one transaction.
6. Terminal status is historical fact and cannot transition back to a live status.
7. Replaced documents remain present and are connected to successors by ID.
8. Tracked moves use `git mv`; updates target the canonical document rather than creating copies.
9. Repository-local Markdown/MDX links cannot silently break after a transition.
10. Code and documentation state should align at logical commit boundaries.

Configuration may relocate directories or generated artifacts, but it may not disable unique identity, canonical frontmatter, immutable history, or transition validity.

## 3. Directory and path projection

Default layout:

```text
docs/
├── plan/
├── migrations/
├── generated/
├── archive/
│   ├── plan/<created-year>/
│   ├── migrations/<created-year>/
│   └── generated/<created-year>/
├── INDEX.md
└── .registry.json
```

Live documents use:

```text
docs/<type-directory>/<created-date>-<status>-<slug>.md
```

Terminal documents use:

```text
docs/archive/<type-directory>/<created-year>/<created-date>-<status>-<slug>.md
```

The default type mapping is:

| `type` | Live directory | ID prefix |
|---|---|---|
| `plan` | `plan/` | `PLAN` |
| `migration` | `migrations/` | `MIG` |
| `generated` | `generated/` | `GEN` |

The archive year is derived from `created_at`, not `archived_at`, so the projected path remains deterministic. Small repositories may disable year partitioning in configuration. Large repositories should retain type and year partitioning to prevent `archive/` from becoming a new dumping ground.

Filenames must be lowercase, ASCII, kebab-case, and end in `.md`. Do not use bracketed statuses; `[]` has special glob semantics in common shells.

## 4. Canonical frontmatter schema

All managed documents require:

```yaml
---
schema_version: 1
id: PLAN-20260814-001
slug: payment-refactor
title: Payment Refactor
type: plan
status: active
created_at: 2026-08-14T21:20:00+08:00
updated_at: 2026-08-20T10:05:21+08:00
status_changed_at: 2026-08-18T12:10:00+08:00
owner: null
supersedes: []
superseded_by: []
related: []
depends_on: []
---
```

Rules:

- `schema_version` must be `1`.
- `id`, `slug`, `title`, `type`, `status`, `created_at`, `updated_at`, and `status_changed_at` are required.
- Relationships are lists of IDs, not paths.
- Every timestamp uses ISO 8601 with an explicit timezone.
- `updated_at` advances for any content or metadata change.
- `status_changed_at` advances only when status changes.
- `archived_at` is required at the exact operation that enters a terminal state.
- Unknown additive fields are allowed so repositories can add `priority`, `milestone`, `issue`, `pr`, or ownership metadata without breaking schema v1.

`slug` is explicitly stored because a canonical path cannot otherwise be derived from frontmatter without deriving it from mutable `title`. This closes an ambiguity in path projection and makes slug immutability enforceable.

## 5. Identity, dates, and slugs

ID format:

```text
<TYPE>-YYYYMMDD-<sequence>
```

Examples:

```text
PLAN-20260814-001
MIG-20260814-001
GEN-20260814-001
```

The ID date and filename date must equal the local calendar date in `created_at`. Prefer `docs_guard.py new`, which allocates the next free sequence, projects the canonical path, and emits the required frontmatter and sections. When creating a document by hand, determine the sequence by scanning `docs/.registry.json` and managed frontmatter; never guess without checking collisions.

The creation date represents document identity creation, not last modification or completion. A document created on August 14 and completed on August 30 remains:

```text
2026-08-14-completed-payment-refactor.md
```

Never rewrite `created_at` or the filename date to August 30. Record later events in `updated_at`, `status_changed_at`, and `archived_at`.

Treat `slug` as immutable after the first commit. Titles may improve without a slug rename. If an exceptional slug correction is necessary before first commit, update frontmatter and filename together and validate before publishing history.

## 6. State machines

### Plans and migrations

| From | Allowed next states |
|---|---|
| `draft` | `active`, `cancelled`, `superseded` |
| `active` | `blocked`, `review`, `completed`, `cancelled`, `superseded` |
| `blocked` | `active`, `cancelled`, `superseded` |
| `review` | `active`, `completed`, `superseded` |
| `completed` | none |
| `cancelled` | none |
| `superseded` | none |

Semantic guidance:

- `draft`: the plan is being formed; implementation has not started.
- `active`: implementation is underway.
- `blocked`: implementation started but an external or technical blocker prevents progress.
- `review`: implementation is substantially complete and undergoing validation/review.
- `completed`: completion criteria passed and the intended work is done.
- `cancelled`: the work will not proceed.
- `superseded`: another canonical document replaces this proposal or work record.

Direct `draft -> completed` is invalid because it erases the execution and review history. A very small task that does not warrant lifecycle states should not create a managed plan merely for ceremony.

### Generated documents

| From | Allowed next states |
|---|---|
| `current` | `stale`, `superseded` |
| `stale` | `current`, `superseded` |
| `superseded` | none |

`stale -> current` is appropriate when the same canonical generated artifact is refreshed in place. Create a new document/ID and supersede the old one when preserving distinct snapshots is important.

## 7. Content contracts

Missing recommended sections produce warnings rather than errors so teams can tailor content while retaining interoperable metadata.

### Plan

```text
# <Title>
## Context
## Problem
## Goals
## Non-goals
## Current State
## Proposed Design
## Implementation Plan
## Validation
## Risks
## Rollback
## Progress
## Decisions
```

### Migration

```text
# <Title>
## Context
## Scope
## Preconditions
## Compatibility
## Migration Steps
## Validation
## Rollback
## Observability
## Failure Handling
## Completion Criteria
```

### Generated

```text
# <Title>
## Generation Metadata
## Source
## Scope
## Results
## Limitations
```

Use `Progress` for durable milestone state, not a transcript of agent activity. Use `Decisions` for choices and rationale that future maintainers cannot reconstruct from code alone.

## 8. Generated-document rules

`docs/generated/` is only for documents reproducible from code, logs, data, or deterministic tool output, such as:

- API or dependency audits;
- schema and architecture snapshots;
- coverage, inventory, or benchmark reports.

It is not a catch-all for AI-written prose. Human-authored proposals belong in `docs/plan/`.

Generated metadata adds:

```yaml
generated: true
generated_at: 2026-08-14T21:20:00+08:00
generator: codex
source:
  - app/
  - routes/
generation_command: python tools/api_audit.py
```

`generated: true` is required. Missing `source`, `generator`, or `generated_at` is a warning in v1 because some tools cannot expose all provenance. Prefer a reproducible `generation_command` when available.

Do not archive generated reference material merely because an implementation plan completed. Transition it only when the artifact itself becomes stale or is superseded.

## 9. Relationships and successors

Relationship fields contain immutable IDs:

```yaml
supersedes:
  - PLAN-20260814-001
superseded_by: []
related:
  - MIG-20260920-001
depends_on: []
```

`supersedes` and `superseded_by` must be reciprocal and reference existing managed documents.

When a non-terminal document is replaced:

1. Create the successor with a new ID and creation date.
2. Transition the predecessor to `superseded` with `--superseded-by`.
3. Archive the predecessor and update both relationship lists atomically.

When completed work later needs a new design:

1. Leave the predecessor `completed`; it remains a true historical outcome.
2. Create a new `draft` successor.
3. Run `link-successor` to add reciprocal relationships without rewriting the old status.

This distinguishes “the work was completed and later evolved” from “the original proposal was replaced before completion.” `cancelled` means the work stopped; `superseded` means another canonical proposal replaced it.

## 10. Atomic transition protocol

A transition is one logical transaction:

```text
validate baseline
→ validate requested edge
→ update status and timestamps
→ update lifecycle relationships
→ rebase links inside the moving document
→ git mv tracked document (or move untracked document)
→ repair inbound repository Markdown/MDX links
→ regenerate INDEX and registry
→ validate the result against HEAD
→ inspect worktree and staged diff
```

The bundled transition command snapshots affected Markdown and generated artifacts and attempts rollback if a post-move validation fails. This is filesystem-level best-effort transactionality, not a substitute for reviewing `git status` and the diff.

Before transition:

- require a valid managed-document baseline;
- refuse illegal edges and terminal reopening;
- refuse an existing destination;
- refuse staged source/successor changes so existing index intent is not overwritten;
- verify successor identity and compatible type.

After transition, inspect both staged and unstaged changes. `git mv` stages the rename, while repaired links and regenerated artifacts may remain unstaged until the agent deliberately stages the whole owned milestone.

## 11. Validation model

Errors fail `check`; warnings report content-quality gaps.

| Condition | Level |
|---|---|
| duplicate document ID | ERROR |
| invalid ID/type/status/schema | ERROR |
| filename, directory, or status projection mismatch | ERROR |
| live document in archive or terminal document outside archive | ERROR |
| changed `created_at`, `slug`, or `type` against Git base | ERROR |
| removed/changed tracked managed ID | ERROR |
| invalid state transition | ERROR |
| stale `status_changed_at` or `updated_at` | ERROR |
| missing/invalid `archived_at` | ERROR |
| broken managed-doc link or link into `docs/` | ERROR |
| unknown, self, or non-reciprocal relationship | ERROR |
| stale/missing `INDEX.md` or registry | ERROR |
| partial lifecycle-like frontmatter without ID | WARNING |
| generated document missing provenance detail | WARNING |
| missing recommended content section | WARNING |

Git-history validation is explicit:

```text
docs_guard.py check <repo> --base-ref HEAD
docs_guard.py check <repo> --base-ref origin/main
```

Use `HEAD` before a local commit. In CI, compare with the actual merge/integration base. A structural check without `--base-ref` cannot prove that immutable fields or transition edges were preserved across commits.

Link validation is intentionally gradual: it checks links originating in managed documents and repository Markdown/MDX links that point into the configured docs root. It does not turn unrelated pre-existing legacy links into a surprise repository-wide migration project.

## 12. Index and registry

`docs/INDEX.md` and `docs/.registry.json` are generated outputs and must not be hand-edited.

The index groups active plans, active migrations, generated documents, and archived history. It provides clickable titles and visible status/update dates.

The registry maps immutable ID to canonical metadata and current path:

```json
{
  "PLAN-20260814-001": {
    "type": "plan",
    "status": "active",
    "title": "Payment Refactor",
    "created_at": "2026-08-14T21:20:00+08:00",
    "updated_at": "2026-08-20T10:05:21+08:00",
    "path": "docs/plan/2026-08-14-active-payment-refactor.md"
  }
}
```

Refresh both with `index`; verify without writing with `index --check`. Commit them with the managed-document change that made them stale.

## 13. Project configuration

Copy `assets/git-commit-guard.yml` from this skill to repository root as `.git-commit-guard.yml` when defaults do not fit or when the repository wants explicit policy discovery.

Default shape:

```yaml
version: 1
documentation:
  enabled: true
  root: docs
  directories:
    plan: plan
    migration: migrations
    generated: generated
    archive: archive
  archive:
    preserve_type: true
    partition_by_year: true
  filename:
    pattern: "{created_date}-{status}-{slug}.md"
    date_format: "%Y-%m-%d"
  index:
    enabled: true
    path: INDEX.md
    registry: .registry.json
  validation:
    unique_id: true
    validate_links: true
    enforce_frontmatter: true
    fail_on_invalid_transition: true
```

Paths must remain repository-relative and cannot contain `..`. The filename pattern must include `{created_date}`, `{status}`, and `{slug}`. The hard validation invariants must remain `true`; `validate_links` can be disabled only when another authoritative repository link checker replaces it.

## 14. Legacy adoption and exemptions

First encounter with an older repository:

1. Scan documentation and existing conventions.
2. Report likely plans, migrations, duplicates, and stale files as legacy observations.
3. Govern only documents explicitly created or modified for the current task.
4. Do not move, rename, add frontmatter to, or archive unrelated legacy documents.
5. Ask for explicit repository-wide authorization before bulk adoption.

For authorized bulk adoption, use reviewable batches:

1. inventory/classification report;
2. ID and frontmatter assignment without moves;
3. path/status projection moves;
4. link repair and generated registry;
5. CI enforcement.

Validate and commit each batch. This separates classification errors from filesystem changes and makes rollback understandable.

## 15. Git and commit integration

Code history answers what changed; managed documentation answers why, intended design, current progress, validation, migration outcome, and why older approaches ended.

Align major state transitions with code milestones:

- `draft -> active`: approved execution begins;
- `active -> review`: implementation is ready for verification/review;
- `review -> completed`: code, tests, and completion criteria pass;
- live -> `blocked`: commit only when the blocker record is durable and useful;
- live -> `cancelled`/`superseded`: preserve the rationale and successor relationship.

Prefer one logical commit containing code, tests, progress/evidence, transition, archive move, link repair, index, and registry. Split only when each commit has independent engineering meaning.

Never create three mechanical commits for status edit, move, and index refresh when they represent one transition. Conversely, do not hide unrelated implementation inside a documentation-transition commit.

## 16. CI and pre-commit integration

Minimum CI gate:

```text
python <skill-dir>/scripts/docs_guard.py check . --base-ref <integration-base>
python <skill-dir>/scripts/docs_guard.py index . --check
```

Choose `<integration-base>` from the CI provider's merge-base context, such as the target branch fetched locally. Do not assume `HEAD^` is correct for merge commits or multi-commit pull requests.

A pre-commit hook may run structural check plus `index --check`; a pre-push or CI hook should add Git-base validation. Hooks must call the committed/shared script path used by the project. If a project vendors the tool, document how it is updated from the skill.

This skill includes two copy-and-adapt assets:

- `assets/pre-commit-config.fragment.yml` for a local pre-commit hook;
- `assets/github-actions-docs-guard.yml` for GitHub Actions.

Before using either asset:

1. Copy `scripts/docs_guard.py` to a stable, committed project path such as `tools/docs_guard.py`; CI cannot rely on a developer's personal skill installation.
2. Merge the fragment into existing hook/workflow configuration; never overwrite unrelated repository automation.
3. Keep full Git history available to the CI job so base-ref validation can read earlier managed documents.
4. Adapt the integration-base resolver for non-GitHub CI or repository-specific merge strategies.
5. Test the hook on a valid transition and a deliberately invalid transition before making it a required branch check.

Warnings should remain visible in CI output. Promote a warning to an error only through a schema/config version change, not silently.

## 17. CLI reference

Create a managed document with a collision-free ID and canonical path:

```text
python scripts/docs_guard.py new plan payment-refactor --repo /repo --title "Payment Refactor"
python scripts/docs_guard.py new migration invoice-backfill --repo /repo
python scripts/docs_guard.py new generated api-audit --repo /repo --generator codex
python scripts/docs_guard.py new plan payment-refactor --repo /repo --dry-run
```

`new` refuses a duplicate slug, a terminal initial status, and an occupied destination. It requires a structurally valid baseline, refreshes the index and registry, and reports any provenance warnings on the created document so they can be filled in before commit.

Structural and history validation:

```text
python scripts/docs_guard.py check /repo
python scripts/docs_guard.py check /repo --base-ref HEAD
```

Generate or verify derived artifacts:

```text
python scripts/docs_guard.py index /repo
python scripts/docs_guard.py index /repo --check
```

Preview and perform a normal transition:

```text
python scripts/docs_guard.py transition /repo/docs/plan/2026-08-14-active-payment-refactor.md review --dry-run
python scripts/docs_guard.py transition /repo/docs/plan/2026-08-14-active-payment-refactor.md review
```

Supersede a live document:

```text
python scripts/docs_guard.py transition <old-document> superseded --superseded-by PLAN-20260920-001
```

Attach a successor to an already completed document while preserving `completed`:

```text
python scripts/docs_guard.py link-successor <completed-document> <successor-document>
```

`--at` accepts an explicit timezone-bearing timestamp for deterministic automation and tests. Normal agent use should allow the tool to use local timezone automatically.

## 18. Prohibited behavior

Never:

- invent `doing`, `working`, `finished`, `done-ish`, `FINAL`, `LATEST`, or similar status substitutes;
- change only frontmatter status without filename/directory projection;
- move only the file without updating frontmatter and timestamps;
- reopen `completed`, `cancelled`, or `superseded` documents;
- overwrite or delete superseded history to keep directories clean;
- modify `created_at` to match the latest edit or archive date;
- copy a document instead of renaming/moving the canonical file;
- use relationship paths where immutable IDs are required;
- leave reciprocal successor metadata incomplete;
- treat executable database/API migration source as documentation;
- bulk-normalize unrelated user documentation without authorization;
- hand-edit generated index/registry files;
- declare a transition complete while validation, links, or derived artifacts are stale.
