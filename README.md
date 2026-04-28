# Git Commit Guard 🛡️

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**Git Commit Guard** 是一个专门为 AI 编程助手（如 Cursor, Codex, 自研 LLM Agent）设计的技能/提示词配置（Skill/Prompt）库。

它通过强制执行“Git 优先”的工作流，赋予 AI 对本地代码仓库状态的感知能力与敬畏心，防止 AI 破坏未提交的用户代码，并自动生成高质量、结构化的中文 Git 提交记录。

## 🌟 为什么需要 Git Commit Guard？

当 AI 直接在本地代码库中工作时，通常缺乏上下文管理能力。它们可能会：
- 忽略当前的脏工作树（Dirty Worktree），将新功能与你之前的实验代码混杂在一起。
- 执行破坏性的 Git 操作。
- 留下诸如 "update code" 这样毫无上下文的无效 Commit Message。

**Git Commit Guard** 通过一套结构化的规则（定义在 `SKILL.md` 中），将 AI 约束为一个**严谨的资深工程师**，在任何修改前、开发中和回合结束时，严格遵循标准化流程。

## ✨ 核心特性

- 🛑 **脏状态拦截 (Dirty Worktree Handling)**：动手前强制检查 `git status`。如果发现未提交的变更，AI 必须先分析、验证并安全地将其提交，绝不覆盖用户的现有工作。
- ✅ **渐进式验证 (Verification Standard)**：强制 AI 在提交代码前，根据修改范围运行相应的 Lint、类型检查、编译或单元测试。
- 📝 **结构化中文提交 (Chinese Commit Policy)**：内置详细的中文提交模板（背景、变更、验证、说明），让 AI 产出的提交历史具备极高的可审计性。
- 🧩 **关注点分离**：引导 AI 在执行任务时，将不相关的变更拆分到不同的 Commit 中，保持原子性。

## 🚀 工作流详解 (AI 的行为规范)

Git Commit Guard 强制 AI 遵守以下三个阶段的纪律：

### 1. 回合开始 (Start Of Turn)
- 强制运行 `git status --short --branch`。
- 如果仓库是干净的，正常开始新工作。
- 如果是脏状态，暂停新需求开发。AI 会通过 `git diff` 审视这些未提交的文件，推断并运行现有的测试/Lint进行验证，最终生成一个标准的 commit 以保存用户的现有工作。

### 2. 开发期间 (During Work)
- 保持提交的原子性，绝不将不同的逻辑阶段混淆在一个提交中。
- 在开始下一个依赖于干净代码库的逻辑阶段前，主动提交已验证的当前状态。

### 3. 回合结束 (End Of Turn)
- 重新审视最终的 Diff。
- 执行全局或范围最广的合理验证（如完整的单元测试、构建流程）。
- 验证通过后，将最终变更提交，并向用户报告本次回合执行的校验命令及生成的 commit hash。

## 📋 中文提交规范模板

项目内置了 `references/commit-template.md`，强制 AI 生成如下格式的提交信息：

```text
type(scope): 中文简要主题

背景：
- 为什么要做这次提交
- 当前上下文或问题来源

变更：
- 具体修改点 1
- 具体修改点 2

验证：
- 执行的命令 (如 npm run test, cargo check)
- 结果摘要

说明：
- 风险、未覆盖部分或后续建议
