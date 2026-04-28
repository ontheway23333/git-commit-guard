#!/usr/bin/env python3
"""Validate the Git Commit Guard skill package without external dependencies."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_FILES = [
    ".editorconfig",
    ".gitattributes",
    "SKILL.md",
    "agents/openai.yaml",
    "references/commit-template.md",
    "README.md",
    "LICENSE",
]

SKILL_NAME_RE = re.compile(r"^[a-z0-9-]{1,63}$")
TEXT_EXTENSIONS = {".md", ".py", ".yaml", ".yml"}
TEXT_FILENAMES = {".editorconfig", ".gitattributes", "LICENSE"}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def read_text(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(errors, f"Missing required file: {path}")
    except UnicodeDecodeError as exc:
        fail(errors, f"{path} is not valid UTF-8: {exc}")
    return ""


def parse_skill_frontmatter(text: str, errors: list[str]) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        fail(errors, "SKILL.md must start with YAML frontmatter")
        return {}, text

    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = index
            break

    if end is None:
        fail(errors, "SKILL.md frontmatter is not closed")
        return {}, text

    data: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        if ":" not in line:
            fail(errors, f"Invalid frontmatter line {line_number}: {line}")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        data[key] = value

    return data, "\n".join(lines[end + 1 :])


def validate_skill_md(root: Path, errors: list[str]) -> None:
    skill_path = root / "SKILL.md"
    text = read_text(skill_path, errors)
    if not text:
        return

    metadata, body = parse_skill_frontmatter(text, errors)
    expected_keys = {"name", "description"}
    actual_keys = set(metadata)
    if actual_keys != expected_keys:
        fail(errors, f"SKILL.md frontmatter keys must be {sorted(expected_keys)}, got {sorted(actual_keys)}")

    name = metadata.get("name", "")
    if name != "git-commit-guard":
        fail(errors, "SKILL.md name must be git-commit-guard")
    if not SKILL_NAME_RE.fullmatch(name):
        fail(errors, "SKILL.md name must use lowercase letters, digits, and hyphens only")

    description = metadata.get("description", "")
    if len(description.split()) < 15:
        fail(errors, "SKILL.md description is too short to trigger reliably")
    if "git" not in description.lower() or "commit" not in description.lower():
        fail(errors, "SKILL.md description should mention git and commit behavior")

    if len(body.splitlines()) > 500:
        fail(errors, "SKILL.md body should stay under 500 lines")


def quoted_yaml_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\s+{re.escape(key)}:\s+\"([^\"]*)\"\s*$", text, flags=re.MULTILINE)
    return match.group(1) if match else None


def validate_openai_yaml(root: Path, errors: list[str]) -> None:
    path = root / "agents" / "openai.yaml"
    text = read_text(path, errors)
    if not text:
        return

    if "interface:" not in text:
        fail(errors, "agents/openai.yaml must contain interface section")
    if "policy:" not in text:
        fail(errors, "agents/openai.yaml must contain policy section")
    if "allow_implicit_invocation: true" not in text:
        fail(errors, "agents/openai.yaml should allow implicit invocation")

    display_name = quoted_yaml_value(text, "display_name")
    short_description = quoted_yaml_value(text, "short_description")
    default_prompt = quoted_yaml_value(text, "default_prompt")

    if display_name != "Git Commit Guard":
        fail(errors, "display_name must be quoted and set to Git Commit Guard")
    if not short_description:
        fail(errors, "short_description must be quoted")
    elif not 25 <= len(short_description) <= 64:
        fail(errors, "short_description should be 25-64 characters")
    if not default_prompt:
        fail(errors, "default_prompt must be quoted")
    elif "$git-commit-guard" not in default_prompt:
        fail(errors, "default_prompt must mention $git-commit-guard")


def validate_markdown(root: Path, errors: list[str]) -> None:
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts:
            continue
        text = read_text(path, errors)
        if text.count("```") % 2:
            fail(errors, f"{path.relative_to(root)} has an unclosed fenced code block")


def validate_text_files(root: Path, errors: list[str]) -> None:
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        if path.suffix not in TEXT_EXTENSIONS and path.name not in TEXT_FILENAMES:
            continue
        text = read_text(path, errors)
        for index, line in enumerate(text.splitlines(), start=1):
            if line.rstrip() != line:
                fail(errors, f"{path.relative_to(root)}:{index} has trailing whitespace")


def validate_commit_template(root: Path, errors: list[str]) -> None:
    text = read_text(root / "references" / "commit-template.md", errors)
    if not text:
        return
    for marker in ["背景：", "变更：", "验证：", "说明："]:
        if marker not in text:
            fail(errors, f"commit-template.md must include {marker}")


def validate_required_files(root: Path, errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            fail(errors, f"Missing required file: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Git Commit Guard skill package.")
    parser.add_argument("root", nargs="?", default=".", help="Path to the skill repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors: list[str] = []

    validate_required_files(root, errors)
    validate_skill_md(root, errors)
    validate_openai_yaml(root, errors)
    validate_markdown(root, errors)
    validate_text_files(root, errors)
    validate_commit_template(root, errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"OK: {root} is a valid Git Commit Guard skill package")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
