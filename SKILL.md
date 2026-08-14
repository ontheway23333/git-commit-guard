---
name: git-commit-guard
description: "Enforce a git-first, milestone-based repository workflow and a recoverable documentation lifecycle. Use when Codex inspects, modifies, debugs, refactors, implements, tests, documents, migrates, or finishes work in a local git repository. Require dirty-worktree ownership review, dependency-aware batches, targeted validation, small detailed Chinese commits, and lifecycle-safe plan/migration/generated documents with immutable identity, finite-state transitions, archival, repaired links, and generated indexes."
---

# Git Commit Guard

Treat code history and engineering-intent history as one auditable repository state.

`<skill-dir>` below is the directory containing this `SKILL.md`. Resolve it to an absolute path once per turn and reuse it. Do not assume `docs_guard.py` is on `PATH` or already vendored into the target repository.

## Start Of Turn

1. Run `git status --short --branch` before any edit.
2. If this is not a Git repository, say that this skill is not applicable.
3. Inspect every modified, deleted, and untracked path with `git diff --stat`, `git diff`, and targeted reads. Classify ownership as current-agent, user, collaborator, generated, or unknown.
4. Preserve user and collaborator work. Edit only non-overlapping owned paths; never clean the worktree merely to make it look tidy.
5. Infer the strongest reasonable validation from repository configuration, scripts, tests, and CI.
6. Detect documentation governance before planning:
   - Look for `.git-commit-guard.yml`.
   - Look for Markdown under the configured/default `docs/` root whose frontmatter contains an `id`.
   - Treat unmarked Markdown as legacy/exempt unless the user explicitly authorizes migration.
7. If the repository contains managed documentation, a lifecycle config, or the task creates/transitions such a document, read [references/document-lifecycle.md](references/document-lifecycle.md) completely before touching it.
8. When the bundled script is applicable, run:

   ```text
   python <skill-dir>/scripts/docs_guard.py check <repo> --base-ref HEAD
   ```

   Surface baseline errors before implementation. Do not silently repair unrelated legacy documents.

## Complex Task Inventory

Treat work as complex when it spans multiple modules or deliverables, needs sequencing, can be parallelized, changes a public contract, or is likely to require more than one commit.

Before implementing complex work:

1. Translate the request into concrete deliverables and acceptance checks.
2. Inspect relevant code, tests, configuration, managed documents, and active plans.
3. Record dependencies, shared-file conflicts, risks, validation commands, documentation impact, and commit boundaries.
4. Divide the work into the smallest coherent batches that stand independently.
5. Keep at most one dependent batch active. Parallelize only truly independent, non-overlapping work when permitted.
6. Update the plan as evidence changes; do not preserve a stale plan for appearance.

Use this shape when a formal plan helps:

```text
Batch N: <outcome>
- Deliverables: <code/tests/docs>
- Dependencies: <earlier batch or none>
- Ownership: <main agent or named subagent; non-overlapping files>
- Documentation: <managed document IDs and intended transitions, or none>
- Validation: <targeted commands>
- Commit boundary: <independently reviewable state>
```

## Parallel Development

1. Use subagents only when the active system/user instructions permit them and at least two tasks are independent.
2. Give each subagent a bounded outcome, explicit file ownership, inputs, validation, and a no-commit rule unless commit ownership is explicitly delegated or isolated worktrees exist.
3. Keep dependency sequencing, shared-file edits, managed-document transitions, integration decisions, and final commits with the coordinator.
4. Never assign overlapping files in the same batch.
5. Inspect every returned diff or evidence and validate the combined batch before committing.
6. Skip delegation when coordination overhead exceeds the benefit.

## Concurrent Review

When another agent or reviewer is concurrently working:

1. Establish ownership from coordination state, not transient filesystem changes.
2. Treat reviewer-owned code and documentation as read-only. Do not edit, stage, commit, revert, reformat, or delegate those paths.
3. Continue only independent, non-overlapping work.
4. Wait for the current review result before starting the next dependent batch and explicitly disposition findings.
5. Do not poll documentation-writing progress as a separate dependency after review completes; proceed when ownership does not overlap.

## Milestone Commit Workflow

1. Define a commit boundary before each batch.
2. Complete the smallest coherent implementation, tests, and directly related documentation state change together.
3. Run the narrowest meaningful validation for that batch and record what remains for the final gate.
4. Never commit a knowingly broken milestone. Merge only the smallest dependency needed to make it coherent.
5. Stage only owned paths. Avoid broad staging in shared worktrees.
6. Inspect `git diff --cached --check`, `git diff --cached --stat`, and the cached diff before committing.
7. Commit immediately after a milestone passes; do not accumulate unrelated completed work.
8. Confirm committed paths and report the hash and purpose.

## Documentation Lifecycle Gate

For every lifecycle-managed document, enforce these non-negotiable invariants:

1. Frontmatter is canonical metadata; path and filename are projections of it.
2. `id`, `created_at`, and `slug` are immutable. A title may change without renaming the slug.
3. Filename format is `YYYY-MM-DD-status-slug.md`; its date is the original creation date, never the latest update date.
4. Frontmatter status, filename status, and directory must agree in the same operation.
5. Plan and migration statuses are only `draft`, `active`, `blocked`, `review`, `completed`, `cancelled`, and `superseded`.
6. Generated-document statuses are only `current`, `stale`, and `superseded`.
7. `completed`, `cancelled`, and `superseded` are terminal for plans/migrations; `superseded` is terminal for generated documents.
8. Archive terminal documents immediately under `docs/archive/<type>/<created-year>/` by default.
9. Never reactivate a terminal document. Create a successor with a new ID and record reciprocal `supersedes` / `superseded_by` relationships. Preserve a completed predecessor's `completed` status as historical fact.
10. Use IDs—not paths—for metadata relationships. Repair clickable repository-local Markdown/MDX links after every move.
11. Use `git mv` for tracked documents. Never implement a transition as delete-plus-copy or create `FINAL`, `NEW`, `LATEST`, `DONE`, or arbitrary `V2` status variants.
12. Never overwrite a superseded document, mutate `created_at`, copy a canonical document to avoid a move, or declare completion while links/indexes are stale.
13. Apply this lifecycle only to managed documentation. Never move or rewrite executable migrations such as `database/migrations/*.php` or `migrations/*.sql` as documentation.
14. Do not bulk-normalize legacy Markdown unless the user explicitly requests repository-wide adoption.

Create documents with the bundled tool rather than hand-writing frontmatter; it allocates a collision-free ID, the canonical path, and the required sections:

```text
python <skill-dir>/scripts/docs_guard.py new plan <slug> --repo <repo> --title <title>
python <skill-dir>/scripts/docs_guard.py new migration <slug> --repo <repo>
python <skill-dir>/scripts/docs_guard.py new generated <slug> --repo <repo>
```

Use the transition command instead of manually changing state:

```text
python <skill-dir>/scripts/docs_guard.py transition <document> <status>
python <skill-dir>/scripts/docs_guard.py transition <document> superseded --superseded-by <ID>
python <skill-dir>/scripts/docs_guard.py link-successor <terminal-document> <successor-document>
```

Add `--dry-run` to preview a creation or transition before writing.

Treat a transition as incomplete until metadata, `git mv`, link repair, `docs/INDEX.md`, `docs/.registry.json`, validation, and diff inspection all succeed. If the bundled tool cannot run, perform the same ordered transaction manually and report the missing automation.

## Documentation And Commit Alignment

1. Treat managed planning and migration documents as delivery state, not deferred cleanup.
2. Update `Progress`, `Decisions`, validation evidence, and genuine follow-ups while implementation advances.
3. Move `active -> review` only when implementation is substantially complete and ready for verification/review.
4. Move `review -> completed` only after the documented completion criteria and relevant validation pass.
5. Include a meaningful status transition in the same logical commit as the code state it describes whenever practical.
6. Preserve completed outcome/evidence before removing items from active queues.
7. Do not mark work complete merely because the task is ending, the context is long, or a commit exists.
8. For unmanaged existing trackers, follow repository convention and avoid creating a competing lifecycle system.

## Dirty Worktree Handling

When the worktree is dirty:

- Summarize changed paths and intent before editing.
- Inspect related tests and managed-document state where feasible.
- Call out mixed or uncertain ownership.
- Validate and commit only coherent current-agent paths.
- Never absorb unrelated changes into a milestone.
- Treat unknown or collaborator-owned paths as read-only until ownership is clear.

If pre-existing dirty changes are intentional current-agent work, validate and commit them before dependent implementation. If validation fails outside scope, report the blocker and do not create a normal commit.

## Destructive Command Policy

Never run the following unless the user explicitly asks for that command on that path in the current turn:

1. `git reset --hard`, `git checkout -- <path>`, `git restore <path>` without `--staged`.
2. `git clean -fd`, `git stash`, `git stash drop`.
3. `git commit --amend`, `git rebase`, `git push --force`, `git push --force-with-lease`.
4. History rewrites, branch/tag deletion, and remote-ref deletion.
5. Deleting or truncating uncommitted files to make a check pass.

Prefer additive recovery: a new commit, a new branch, or a successor document. Uncommitted work has no reflog; a discarded worktree change is unrecoverable.

Never bypass repository safety with `--no-verify`, `--no-gpg-sign`, or by disabling a failing hook. Fix the cause or report it.

When a destructive command is genuinely the right answer, state the command, what it would discard, and why, then wait for the user.

## Secrets And Artifact Guard

Before staging, read the cached diff for:

1. Credentials, tokens, private keys, `.env` files, and connection strings.
2. Machine-local absolute paths and personal identifiers.
3. Build output, dependency directories, caches, and large binaries that belong in `.gitignore`.

Stop and report a suspected secret instead of committing it. Never commit a secret intending to remove it in a later commit; the value is already disclosed and must be rotated.

## Verification Standard

Before each milestone commit, prefer:

1. Targeted tests for touched modules or scripts.
2. Relevant lint, type-check, compile, or build.
3. Documentation guard checks when managed documents or links changed.
4. Broader project tests for cross-cutting work.

For managed documentation, run the applicable commands:

```text
python <skill-dir>/scripts/docs_guard.py index <repo> --check
python <skill-dir>/scripts/docs_guard.py check <repo> --base-ref HEAD
```

In CI, compare against the actual integration base such as `origin/main`, not blindly `HEAD`. `ERROR` fails; `WARNING` reports quality gaps without failing by default.

When enabling repository enforcement, vendor `scripts/docs_guard.py` into a stable project path such as `tools/docs_guard.py`, then adapt [assets/pre-commit-config.fragment.yml](assets/pre-commit-config.fragment.yml) and [assets/github-actions-docs-guard.yml](assets/github-actions-docs-guard.yml). Inspect existing hooks/workflows first; merge with repository conventions instead of overwriting them.

Before the final commit, run the broadest practical suite: tests, lint, type-check, build/compile, smoke checks, and documentation validation. State exactly what was and was not run.

## End Of Turn

1. Reconcile the task plan, current diff, managed-document progress, and archive state.
2. Re-read the final diff and run the strongest practical validation.
3. Refresh and verify generated documentation artifacts when managed documents changed.
4. Stage only current-agent owned paths and inspect the cached diff.
5. Create a detailed Chinese commit for every finished milestone; never create an empty commit.
6. Confirm owned paths are clean. Leave unrelated worktree changes untouched and report them.
7. In the final response, list validation, commit hashes, documentation IDs/transitions or why none applied, and residual risk.

## Commit Policy

1. Write every commit message in Chinese.
2. Use a concise subject plus a detailed body covering background, changes, verification, risks, and follow-up.
3. State explicitly when a commit preserves pre-existing user work.
4. Read [references/commit-template.md](references/commit-template.md) before drafting a commit.

Recommended types: `feat`, `fix`, `refactor`, `test`, `docs`, and `chore`.

## When Commits Are Not Permitted

If a higher-priority instruction, repository policy, or the user forbids committing:

1. Still perform status inspection, ownership review, implementation, and validation.
2. Leave the worktree coherent and state which paths form the milestone.
3. Report the exact `git add` and `git commit` commands plus the drafted Chinese message instead of running them.
4. Do not stage as a silent substitute for committing unless the user asked for a staged handoff.
5. Apply the same rule to documentation transitions: describe the intended transition rather than half-applying it.

## Response Behavior

1. Mention dirty-worktree scope and ownership early.
2. Tell the user what was verified before each commit.
3. Surface validation or lifecycle failures immediately with their likely cause.
4. Report each commit's purpose and hash in Chinese.
5. Report managed-document updates by immutable ID and transition.
6. If no documentation update applies, say why rather than creating ceremonial files.
