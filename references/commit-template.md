# Chinese Commit Message Template

Use this reference when a commit is expected. Write the final git commit message
in Chinese unless the user explicitly requests another language.

## Format

```text
type(scope): 中文简要主题

背景：
- 为什么要做这次提交
- 当前上下文或问题来源

变更：
- 具体修改点 1
- 具体修改点 2
- 具体修改点 3

验证：
- 执行命令 1
- 执行命令 2
- 结果摘要

说明：
- 风险或兼容性影响
- 未覆盖部分
- 后续建议
```

## Rules

- Keep the subject concise; include `scope` only when it adds useful context.
- Cover motivation, implementation details, validation, and residual risk.
- Mention every validation command that was run and its result.
- If validation was skipped or only partially run, explain why.
- If the commit preserves pre-existing user changes before new development, say that explicitly in `背景` or `说明`.
- Do not use empty messages such as `update`, `fix`, `done`, or `changes`.

## Recommended Types

- `feat`: 新功能
- `fix`: 缺陷修复
- `refactor`: 重构
- `test`: 测试补充或修正
- `docs`: 文档调整
- `chore`: 工程或维护性调整
