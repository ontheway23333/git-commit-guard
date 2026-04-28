---
name: git-commit-guard
description: "Enforce a git-first workflow for repository coding tasks. Use when Codex is working inside a local git repository to inspect, modify, debug, refactor, implement, test, or finish code. Before any new development, require checking git status, reviewing dirty files, validating the current worktree, and committing validated changes. After implementation, require targeted verification, broader end-of-turn validation, and detailed Chinese git commits."
---

# Git Commit Guard

Treat every coding task as operating on a potentially valuable worktree.

## Start Of Turn

1. Run `git status --short --branch` first.
2. If the repository is clean, continue to the requested work.
3. If the repository is dirty, stop new development first.
4. Inspect modified, deleted, and untracked files with `git diff --stat`, `git diff`, and targeted file reads.
5. Summarize what changed by file and by intent before editing anything else.
6. Infer the strongest reasonable validation from the repo itself. Prefer existing test, lint, type-check, compile, or build commands over ad hoc checks.
7. Use the narrowest command that gives real signal for the dirty changes, then broaden if the change is cross-cutting.
8. If validation fails, surface the blocker immediately. Fix it only when that is in scope and safe; otherwise do not create a normal commit.
9. If validation passes and the dirty changes are intentional, create a detailed Chinese git commit before starting the next implementation step.

## Dirty Worktree Handling

When `git status` is not clean, do all of the following before new development:

- Review whether the changes look coherent, risky, incomplete, or broken.
- Inspect tests related to the changed files when feasible.
- Call out uncertainty if unrelated edits may have been mixed together.
- Preserve the user's existing work. Do not discard, overwrite, or silently clean up unrelated changes.

## During Work

1. Keep unrelated changes in separate commits whenever practical.
2. Do not mix pre-existing dirty changes with new feature work without reviewing both scopes.
3. Before starting a new logical phase that depends on a clean base, commit the validated current state.
4. Avoid destructive git commands unless the user explicitly asks for them.

## Verification Standard

Before committing existing dirty changes, prefer this order:

1. Targeted tests for touched modules or packages
2. Fast lint, type-check, or compile commands relevant to touched files
3. Broader project test commands if the repository is small or the change is cross-cutting

Before the final commit, run a broader validation pass whenever practical:

- Full or broader unit test coverage
- Lint
- Type check
- Build or compile
- Targeted smoke test for the implemented flow

If the full sweep is not feasible, state exactly what was run and what was not run.

## End Of Turn

1. Re-read the final diff before the last commit.
2. If files changed during the turn, run the strongest reasonable final validation.
3. If the requested development is finished, or the conversation is likely ending, prefer comprehensive validation over a narrow spot check.
4. If validation passes, stage the final diff and create a detailed Chinese git commit before sending the final response.
5. If no files changed, do not create an empty commit.
6. Confirm `git status` is clean after the final commit.
7. If the repository is not a git repo, say that this skill is not applicable.

## Commit Policy

1. Write every commit message in Chinese.
2. Use a concise subject line plus a detailed body.
3. Explain what changed, why it changed, implementation details, verification status, and any known limitation or follow-up.
4. If a commit preserves user changes before new work begins, say that explicitly so the history remains auditable.
5. When drafting the message, read `references/commit-template.md` for the preferred structure and examples.

Recommended `type` values:

- `feat`
- `fix`
- `refactor`
- `test`
- `docs`
- `chore`

## Response Behavior

1. Mention early when the worktree is dirty and what you are reviewing.
2. Tell the user what you verified before each commit.
3. Surface failures immediately with the likely cause.
4. After each commit, report the commit purpose clearly in Chinese.
5. In the final response, include the validation that ran, the commit hash or hashes created during the turn, and any residual risk.
