---
name: git-commit-guard
description: "Enforce a git-first safety workflow for AI coding agents working in local repositories. Use when Codex inspects, edits, debugs, refactors, tests, commits, or finishes code in a git repo: check status first, protect dirty worktrees, validate changes before commits, keep unrelated work separate, avoid destructive git commands, and write detailed Chinese commit messages."
---

# Git Commit Guard

Treat every coding task as operating on valuable user work.

## Core Rules

1. Run `git status --short --branch` before any repository edit or commit.
2. Preserve user work. Do not discard, overwrite, or silently clean up unrelated changes.
3. Use explicit staging paths when the worktree contains unrelated changes.
4. Avoid destructive git commands unless the user explicitly asks for the exact operation.
5. Do not commit secrets, credentials, local machine config, or large generated artifacts.
6. If a higher-priority instruction forbids commits, validate and report the exact git commands instead of committing.

## Start Of Turn

1. Run `git status --short --branch` first.
2. If the repository is clean, continue to the requested work.
3. If the repository is dirty, stop new development first.
4. Inspect staged, modified, deleted, and untracked files with `git diff --stat`, `git diff`, `git diff --cached`, and targeted file reads.
5. Summarize what changed by file and by apparent intent before editing anything else.
6. Call out uncertainty when unrelated edits may have been mixed together.
7. Infer the strongest reasonable validation from the repo itself. Prefer existing test, lint, type-check, compile, or build commands over ad hoc checks.
8. Use the narrowest command that gives real signal for the dirty changes, then broaden if the change is cross-cutting.
9. If validation fails, surface the blocker immediately. Fix it only when that is in scope and safe.
10. If validation passes and commits are expected by the task or local policy, preserve the existing dirty work in a detailed Chinese commit before starting the next implementation step.

## During Work

1. Keep unrelated changes in separate commits whenever practical.
2. Do not mix pre-existing dirty changes with new feature work without reviewing both scopes.
3. Before starting a new logical phase that depends on a clean base, validate and commit the current state when commits are expected.
4. Re-check `git status --short --branch` after major tool runs, generators, formatters, or failed commands.
5. If unexpected files change, inspect them before deciding whether they belong in the current commit.

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

If full validation is not feasible, state exactly what was run, what was not run, and why.

## End Of Turn

1. Re-read the final diff before the last commit.
2. If files changed during the turn, run the strongest reasonable final validation.
3. If the requested development is finished, or the conversation is likely ending, prefer comprehensive validation over a narrow spot check.
4. If validation passes and commits are expected, stage the final diff with explicit paths and create a detailed Chinese git commit before sending the final response.
5. If validation fails, do not create a normal success commit. Explain the failure and the safest next step.
6. If no files changed, do not create an empty commit.
7. Confirm `git status --short --branch` after the final commit.
8. If the directory is not a git repo, say that this skill is not applicable and continue only with non-git-safe workflow steps.

## Commit Policy

1. Write every commit message in Chinese unless the user explicitly requests another language.
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

1. Mention early when the worktree is dirty and what is being reviewed.
2. Tell the user what was verified before each commit.
3. Surface failures immediately with the likely cause.
4. After each commit, report the commit purpose clearly in Chinese.
5. In the final response, include the validation that ran, the commit hash or hashes created during the turn, and any residual risk.
