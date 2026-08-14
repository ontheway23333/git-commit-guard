#!/usr/bin/env python3
"""Validate the Git Commit Guard skill package without external dependencies."""

from __future__ import annotations

import argparse
import importlib.util
import py_compile
import re
import sys
from pathlib import Path


REQUIRED_FILES = [
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "SKILL.md",
    "agents/openai.yaml",
    "assets/git-commit-guard.yml",
    "assets/github-actions-docs-guard.yml",
    "assets/pre-commit-config.fragment.yml",
    "references/commit-template.md",
    "references/document-lifecycle.md",
    "scripts/docs_guard.py",
    "scripts/validate_skill.py",
    "tests/test_docs_guard.py",
    "README.md",
    "LICENSE",
]

SKILL_NAME_RE = re.compile(r"^[a-z0-9-]{1,63}$")
TEXT_EXTENSIONS = {".md", ".py", ".yaml", ".yml"}
TEXT_FILENAMES = {".editorconfig", ".gitattributes", ".gitignore", "LICENSE"}
MAX_DESCRIPTION_CHARS = 1024
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SKILL_SCRIPT_RE = re.compile(r"(?:^|[\s`\"'(]|<skill-dir>/)scripts/([A-Za-z0-9_.-]+\.py)", re.MULTILINE)


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
    if len(description) > MAX_DESCRIPTION_CHARS:
        fail(errors, f"SKILL.md description must stay within {MAX_DESCRIPTION_CHARS} characters, got {len(description)}")
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


def validate_internal_links(root: Path, errors: list[str]) -> None:
    """A broken reference silently removes guidance the agent is told to read."""

    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts:
            continue
        text = read_text(path, errors)
        for destination in MARKDOWN_LINK_RE.findall(text):
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", destination) or destination.startswith(("#", "//")):
                continue
            target = destination.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            resolved = (root / target.lstrip("/")) if target.startswith("/") else (path.parent / target)
            if not resolved.exists():
                fail(errors, f"{path.relative_to(root)} links to missing path: {destination}")


def validate_referenced_scripts(root: Path, errors: list[str]) -> None:
    for relative in ("SKILL.md", "README.md", "references/document-lifecycle.md"):
        path = root / relative
        if not path.is_file():
            continue
        for name in sorted(set(SKILL_SCRIPT_RE.findall(read_text(path, errors)))):
            if not (root / "scripts" / name).is_file():
                fail(errors, f"{relative} references missing scripts/{name}")


def validate_python_sources(root: Path, errors: list[str]) -> None:
    for path in sorted(root.rglob("*.py")):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            py_compile.compile(str(path), doraise=True, cfile=str(path.with_suffix(".pyc.check")))
        except py_compile.PyCompileError as exc:
            fail(errors, f"{path.relative_to(root)} does not compile: {exc.msg.strip()}")
        finally:
            path.with_suffix(".pyc.check").unlink(missing_ok=True)


def validate_default_config_asset(root: Path, errors: list[str]) -> None:
    """Prove the shipped default config is accepted by the shipped guard tool."""

    script = root / "scripts" / "docs_guard.py"
    asset = root / "assets" / "git-commit-guard.yml"
    if not script.is_file() or not asset.is_file():
        return
    spec = importlib.util.spec_from_file_location("_docs_guard_validation", script)
    if spec is None or spec.loader is None:
        fail(errors, "cannot import scripts/docs_guard.py")
        return
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their defining module through sys.modules during exec_module.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        config = module.load_config(root, asset)
    except Exception as exc:
        fail(errors, f"assets/git-commit-guard.yml is not accepted by docs_guard.load_config: {exc}")
        return
    finally:
        sys.modules.pop(spec.name, None)
    defaults = module.DEFAULT_CONFIG["documentation"]
    documentation = config["documentation"]
    for key in ("root", "directories", "filename", "index"):
        if documentation.get(key) != defaults.get(key):
            fail(errors, f"assets/git-commit-guard.yml documentation.{key} drifted from DEFAULT_CONFIG")


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
    validate_internal_links(root, errors)
    validate_referenced_scripts(root, errors)
    validate_python_sources(root, errors)
    validate_default_config_asset(root, errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"OK: {root} is a valid Git Commit Guard skill package")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
