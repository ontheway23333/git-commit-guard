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
  explicitly asks for that command.
- **Secrets and artifact guard**: read the cached diff for credentials, `.env`
  files, machine-local paths, and build output before staging.
- **Documentation lifecycle**: immutable IDs, finite-state transitions, archival,
  repaired links, and generated indexes — enforced by a bundled validator.

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

## Documentation Lifecycle

Managed documents are Markdown files under `docs/` whose frontmatter carries an
immutable `id`. Markdown without one stays legacy/exempt, so the skill never
turns an existing repository into a surprise migration project.

`scripts/docs_guard.py` is a dependency-light CLI (PyYAML optional) that owns the
error-prone parts of that lifecycle:

```bash
python scripts/docs_guard.py new plan payment-refactor --repo . --title "Payment Refactor"
python scripts/docs_guard.py check . --base-ref HEAD
python scripts/docs_guard.py index . --check
python scripts/docs_guard.py transition <document> review
python scripts/docs_guard.py link-successor <completed-document> <successor-document>
```

`new` allocates a collision-free ID, projects the canonical path, and writes the
required sections. `transition` performs the status change, `git mv`, link
repair, and index refresh as one rollback-protected operation. Full rules live in
[`references/document-lifecycle.md`](references/document-lifecycle.md).

To enforce this in your own repository, vendor `scripts/docs_guard.py` to a
committed path such as `tools/docs_guard.py`, then adapt
[`assets/pre-commit-config.fragment.yml`](assets/pre-commit-config.fragment.yml)
and [`assets/github-actions-docs-guard.yml`](assets/github-actions-docs-guard.yml).
Copy [`assets/git-commit-guard.yml`](assets/git-commit-guard.yml) to
`.git-commit-guard.yml` only when the defaults do not fit.

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

## Validation

Run the package validator and the guard tests before publishing changes:

```bash
python scripts/validate_skill.py .
```

```bash
python -m unittest discover -s tests -v
```

The validator checks required files, frontmatter, internal Markdown links,
Python syntax, and that the shipped default config is still accepted by
`docs_guard.py`. CI runs the tests on Linux and Windows, with and without
PyYAML, so both YAML parsing paths stay exercised.

If you are developing inside Codex and have the official skill validator
available, you can run that too:

```bash
python path/to/skill-creator/scripts/quick_validate.py /path/to/git-commit-guard
```

Also run basic repository checks before publishing changes:

```bash
git status --short --branch
```

## Contributing

Pull requests are welcome. Keep changes small and auditable:

- Keep `SKILL.md` concise and focused on behavior the agent must follow.
- Put detailed reusable examples or templates in `references/`.
- Keep repository automation dependency-light and documented in `README.md`.
- Preserve the Chinese commit policy unless the change intentionally adds a
  configurable alternative.
- Validate the skill folder before opening a pull request.
- Do not add secrets, local machine paths, generated build output, or large
  binary artifacts.

## Security

This skill does not run a service or collect data. Its main safety boundary is
the agent behavior it instructs. If you find wording that could make an agent
discard user work, commit secrets, or bypass validation, please open an issue
with a minimal reproduction.

## License

MIT. See [`LICENSE`](LICENSE).
