# Git Commit Guard

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Validate](https://github.com/ontheway23333/git-commit-guard/actions/workflows/validate.yml/badge.svg)](https://github.com/ontheway23333/git-commit-guard/actions/workflows/validate.yml)

Git Commit Guard is a Codex skill that makes AI coding agents treat every local
repository as valuable user work. It enforces a git-first workflow: inspect the
worktree before editing, protect existing changes, validate before committing,
keep unrelated work separate, and write detailed Chinese commit messages.

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
- **No destructive shortcuts**: avoid commands such as `git reset --hard` or
  `git checkout -- <path>` unless the user explicitly asks for them.

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
6. Re-read the final diff, run the strongest practical validation pass, commit
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

## Repository Layout

```text
git-commit-guard/
|-- .editorconfig
|-- .github/
|   `-- workflows/
|       `-- validate.yml
|-- .gitattributes
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
|-- references/
|   `-- commit-template.md
|-- scripts/
|   `-- validate_skill.py
|-- LICENSE
`-- README.md
```

## Validation

Run the repository validator before publishing changes:

```bash
python scripts/validate_skill.py .
```

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
