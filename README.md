# Git Commit Guard

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Validate](https://github.com/ontheway23333/git-commit-guard/actions/workflows/validate.yml/badge.svg)](https://github.com/ontheway23333/git-commit-guard/actions/workflows/validate.yml)

Git Commit Guard is a Codex skill that makes AI coding agents treat every local
repository as valuable user work. It enforces a git-first workflow: inspect the
worktree before editing, protect existing changes, validate before committing,
keep unrelated work separate, and write detailed Chinese commit messages.

It also governs a recoverable **documentation lifecycle**, so plans, migrations,
and generated reports keep an immutable identity, a legal state machine, and a
canonical path instead of drifting into `plan-final-v2-NEW.md`.

Use it when an agent is allowed to work inside a git repository and you want a
clear audit trail instead of vague commits like `update code`.

## Contents

- [What It Enforces](#what-it-enforces)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Expected Agent Behavior](#expected-agent-behavior)
- [Commit Message Format](#commit-message-format)
- [Documentation Lifecycle](#documentation-lifecycle)
- [Repository Layout](#repository-layout)
- [Troubleshooting](#troubleshooting)
- [Validation](#validation)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## What It Enforces

- **Status first**: run `git status --short --branch` before starting new code work.
- **Dirty worktree protection**: inspect existing modified, deleted, staged, and
  untracked files before editing anything else.
- **Validation before commits**: prefer targeted tests, lint, type checks, build
  commands, or the strongest reasonable local verification for the changed scope.
- **Separated intent**: keep pre-existing work, new implementation work, and
  unrelated follow-up changes in separate commits whenever practical.
- **Detailed Chinese commits**: use a structured message with background,
  changes, verification, and known limitations.
- **No destructive shortcuts**: never run `git reset --hard`, `git clean -fd`,
  `git checkout -- <path>`, history rewrites, or `--no-verify` unless the user
  explicitly asks for that command. Uncommitted work has no reflog.
- **Secrets and artifact guard**: read the cached diff for credentials, `.env`
  files, machine-local paths, and build output before staging.
- **Documentation lifecycle**: immutable IDs, finite-state transitions, archival,
  repaired links, and generated indexes — enforced by a bundled validator.

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.9+ | `scripts/docs_guard.py` uses only the standard library |
| Git on `PATH` | used for `ls-files`, `ls-tree`, `mv`, and base-ref comparison |
| PyYAML | **optional**; a conservative YAML subset parser is used when absent |

The skill runs no service, opens no network connection, and collects no data.

## Installation

Clone this repository into your Codex skills directory.

macOS or Linux:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/ontheway23333/git-commit-guard.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/git-commit-guard"
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\skills" | Out-Null
git clone https://github.com/ontheway23333/git-commit-guard.git `
  "$HOME\.codex\skills\git-commit-guard"
```

Restart Codex after installation if your client does not auto-refresh skills.

## Quick Start

Create a managed plan in any git repository:

```bash
python scripts/docs_guard.py new plan payment-refactor --repo . --title "Payment Refactor"
```

```text
Create: PLAN-20260815-001 (plan/draft)
Path: docs/plan/2026-08-15-draft-payment-refactor.md
Created: docs/plan/2026-08-15-draft-payment-refactor.md
```

The tool allocates the ID, projects the path, and writes canonical frontmatter
plus the required sections:

```yaml
---
schema_version: 1
id: PLAN-20260815-001
slug: payment-refactor
title: Payment Refactor
type: plan
status: draft
created_at: 2026-08-15T02:40:33+08:00
updated_at: 2026-08-15T02:40:33+08:00
status_changed_at: 2026-08-15T02:40:33+08:00
owner: null
supersedes: []
superseded_by: []
related: []
depends_on: []
---
```

It also regenerates `docs/INDEX.md`:

```markdown
## Active Plans

| ID | Status | Title | Updated |
|---|---|---|---|
| PLAN-20260815-001 | draft | [Payment Refactor](plan/2026-08-15-draft-payment-refactor.md) | 2026-08-15 |
```

Move the plan through its lifecycle as the work progresses:

```bash
python scripts/docs_guard.py transition docs/plan/2026-08-15-draft-payment-refactor.md active
```

Verify the repository at any point:

```bash
python scripts/docs_guard.py check . --base-ref HEAD
```

```text
Summary: 1 managed, 1 legacy/exempt, 0 errors, 0 warnings
```

## Usage

Invoke the skill explicitly in a repository task:

```text
Use $git-commit-guard to implement this change, validate it, and create a
detailed Chinese git commit.
```

Clients that support `agents/openai.yaml` may also invoke it implicitly for
coding tasks in local git repositories.

## Expected Agent Behavior

1. Check the current branch and worktree state before touching files.
2. If the worktree is dirty, review the existing diff and summarize what appears
   to have changed.
3. Run the narrowest meaningful validation command for the existing changes,
   then broaden validation when the scope is cross-cutting.
4. Preserve validated pre-existing work in its own commit when committing is
   authorized by the task or local policy.
5. Make the requested code changes.
6. Update managed documentation state alongside the code it describes, using
   `docs_guard.py` rather than hand-editing frontmatter and paths.
7. Re-read the final diff, run the strongest practical validation pass, commit
   the final changes, and report the commands and commit hashes.

If a higher-priority instruction forbids commits, the agent should still inspect,
validate, and report the exact next git commands instead of committing.

## Commit Message Format

The commit message policy is intentionally Chinese-first because this skill is
designed for teams that want Chinese audit trails. The reference template lives
in [`references/commit-template.md`](references/commit-template.md).

Recommended shape:

```text
type(scope): 中文简要主题

背景：
- 为什么要做这次提交

变更：
- 具体修改点

验证：
- 执行过的命令和结果

说明：
- 风险、未覆盖部分或后续建议
```

A filled-in example:

```text
fix(payment): 修复退款金额四舍五入偏差

背景：
- 退款单在分币位出现 1 分误差，财务对账每日需人工修正。
- 根因是浮点累加后再取整，而非按最小货币单位计算。

变更：
- RefundCalculator 改为整数分计算，移除中间浮点累加。
- 补充边界用例：0 元退款、超额退款、多笔部分退款合并。

验证：
- pytest tests/payment/ -q  -> 42 passed
- ruff check app/payment    -> 通过

说明：
- 历史错误数据需另行脚本修正，本次不含数据迁移。
```

Recommended types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.

## Documentation Lifecycle

Managed documents are Markdown files under `docs/` whose frontmatter carries an
immutable `id`. Markdown without one stays legacy/exempt, so the skill never
turns an existing repository into a surprise migration project.

### States

Plans and migrations:

| From | Allowed next states |
|---|---|
| `draft` | `active`, `cancelled`, `superseded` |
| `active` | `blocked`, `review`, `completed`, `cancelled`, `superseded` |
| `blocked` | `active`, `cancelled`, `superseded` |
| `review` | `active`, `completed`, `superseded` |
| `completed`, `cancelled`, `superseded` | terminal — no way back |

Generated documents use `current` and `stale`, with `superseded` terminal.

Terminal documents are archived, never reopened. When completed work later needs
a new design, `link-successor` attaches a successor while preserving the
predecessor's `completed` status as historical fact.

### Path projection

Frontmatter is the source of truth; the path is a projection of it. Completing a
plan moves the file and repairs every inbound link in one operation:

```text
before                                          after
docs/                                           docs/
|-- plan/                                       |-- archive/
|   `-- 2026-08-15-review-payment-refactor.md   |   `-- plan/
|-- INDEX.md                                    |       `-- 2026/
`-- .registry.json                              |           `-- 2026-08-15-completed-payment-refactor.md
                                                |-- INDEX.md
                                                `-- .registry.json
```

The creation date in the filename never changes — it is document identity, not
last-modified. A plan created on 2026-08-15 and completed on 2026-08-30 keeps
`2026-08-15` in its name.

### CLI

`scripts/docs_guard.py` is a dependency-light CLI that owns the error-prone parts
of the lifecycle:

| Command | Purpose |
|---|---|
| `new <type> <slug>` | create a document with a collision-free ID and canonical path |
| `check <repo> [--base-ref REF]` | validate structure, links, relationships, and history |
| `index <repo> [--check]` | regenerate or verify `INDEX.md` and `.registry.json` |
| `transition <doc> <status>` | status change, `git mv`, link repair, and index refresh as one operation |
| `link-successor <old> <new>` | attach a successor without rewriting terminal history |

`new` and `transition` accept `--dry-run` to preview without writing.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | no errors |
| `1` | validation errors found |
| `2` | guard failure or invalid usage |

Full rules live in
[`references/document-lifecycle.md`](references/document-lifecycle.md).

### Enforcing it in your own repository

Vendor `scripts/docs_guard.py` to a committed path such as `tools/docs_guard.py`
— CI cannot rely on a developer's personal skill installation — then adapt
[`assets/pre-commit-config.fragment.yml`](assets/pre-commit-config.fragment.yml)
and [`assets/github-actions-docs-guard.yml`](assets/github-actions-docs-guard.yml).
Copy [`assets/git-commit-guard.yml`](assets/git-commit-guard.yml) to
`.git-commit-guard.yml` only when the defaults do not fit.

In CI, compare against the real integration base rather than `HEAD`:

```bash
python tools/docs_guard.py check . --base-ref origin/main
python tools/docs_guard.py index . --check
```

## Repository Layout

```text
git-commit-guard/
|-- .editorconfig
|-- .gitattributes
|-- .github/
|   `-- workflows/
|       `-- validate.yml
|-- .gitignore
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
|-- assets/
|   |-- git-commit-guard.yml
|   |-- github-actions-docs-guard.yml
|   `-- pre-commit-config.fragment.yml
|-- references/
|   |-- commit-template.md
|   `-- document-lifecycle.md
|-- scripts/
|   |-- docs_guard.py
|   `-- validate_skill.py
|-- tests/
|   `-- test_docs_guard.py
|-- LICENSE
`-- README.md
```

## Troubleshooting

| Message | Cause and fix |
|---|---|
| `source has staged changes; commit or unstage them before transition` | `git mv` stages the previous rename. Commit that milestone before the next transition. |
| `transition requires a valid baseline` | The repository already has documentation errors. Run `check` first and resolve them. |
| `illegal transition completed -> active` | Terminal status is permanent. Create a successor and use `link-successor`. |
| `slug '<slug>' is already used by a managed document` | Slugs are unique and immutable. Choose a different one; do not rename an existing document. |
| `stale; run docs_guard.py index` | `INDEX.md` or `.registry.json` is out of date. Run `index` and commit it with the change that made it stale. |
| `cannot read git reference '<ref>'` | The base ref does not exist locally. Fetch it first; in CI use `fetch-depth: 0`. |
| `check` reports `0 managed` in a repository full of docs | Expected. Documents become managed only once their frontmatter has an `id`; unmarked Markdown stays exempt by design. |

## Validation

Run the package validator and the guard tests before publishing changes:

```bash
python scripts/validate_skill.py .
```

```bash
python -m unittest discover -s tests -v
```

The validator checks required files, `SKILL.md` frontmatter, internal Markdown
links, Python syntax, and that the shipped default config is still accepted by
`docs_guard.py`. CI runs the tests on Linux and Windows, with and without
PyYAML, so both YAML parsing paths stay exercised.

If you are developing inside Codex and have the official skill validator
available, you can run that too:

```bash
python path/to/skill-creator/scripts/quick_validate.py /path/to/git-commit-guard
```

## Contributing

Pull requests are welcome. Keep changes small and auditable:

- Keep `SKILL.md` concise and focused on behavior the agent must follow.
- Put detailed reusable examples or templates in `references/`.
- Keep repository automation dependency-light and documented in `README.md`.
- Preserve the Chinese commit policy unless the change intentionally adds a
  configurable alternative.
- Validate the skill folder and run the tests before opening a pull request.
- Do not add secrets, local machine paths, generated build output, or large
  binary artifacts.

## Security

This skill does not run a service or collect data. Its main safety boundary is
the agent behavior it instructs. If you find wording that could make an agent
discard user work, commit secrets, or bypass validation, please open an issue
with a minimal reproduction.

## License

MIT. See [`LICENSE`](LICENSE).
