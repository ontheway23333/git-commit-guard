#!/usr/bin/env python3
"""Validate and transition lifecycle-managed repository documentation.

The tool intentionally depends only on Python's standard library. PyYAML is used
when available; a conservative YAML subset parser keeps the default workflow
portable when it is not installed.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised only in minimal runtimes
    yaml = None


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "documentation": {
        "enabled": True,
        "root": "docs",
        "directories": {
            "plan": "plan",
            "migration": "migrations",
            "generated": "generated",
            "archive": "archive",
        },
        "archive": {
            "preserve_type": True,
            "partition_by_year": True,
        },
        "filename": {
            "pattern": "{created_date}-{status}-{slug}.md",
            "date_format": "%Y-%m-%d",
        },
        "index": {
            "enabled": True,
            "path": "INDEX.md",
            "registry": ".registry.json",
        },
        "validation": {
            "unique_id": True,
            "validate_links": True,
            "enforce_frontmatter": True,
            "fail_on_invalid_transition": True,
        },
    },
}

TYPE_RULES = {
    "plan": {
        "prefix": "PLAN",
        "live": {"draft", "active", "blocked", "review"},
        "terminal": {"completed", "cancelled", "superseded"},
        "initial": "draft",
        "headings": (
            "Context",
            "Problem",
            "Goals",
            "Non-goals",
            "Current State",
            "Proposed Design",
            "Implementation Plan",
            "Validation",
            "Risks",
            "Rollback",
            "Progress",
            "Decisions",
        ),
    },
    "migration": {
        "prefix": "MIG",
        "live": {"draft", "active", "blocked", "review"},
        "terminal": {"completed", "cancelled", "superseded"},
        "initial": "draft",
        "headings": (
            "Context",
            "Scope",
            "Preconditions",
            "Compatibility",
            "Migration Steps",
            "Validation",
            "Rollback",
            "Observability",
            "Failure Handling",
            "Completion Criteria",
        ),
    },
    "generated": {
        "prefix": "GEN",
        "live": {"current", "stale"},
        "terminal": {"superseded"},
        "initial": "current",
        "headings": (
            "Generation Metadata",
            "Source",
            "Scope",
            "Results",
            "Limitations",
        ),
    },
}

TRANSITIONS = {
    "plan": {
        "draft": {"active", "cancelled", "superseded"},
        "active": {"blocked", "review", "completed", "cancelled", "superseded"},
        "blocked": {"active", "cancelled", "superseded"},
        "review": {"active", "completed", "superseded"},
    },
    "migration": {
        "draft": {"active", "cancelled", "superseded"},
        "active": {"blocked", "review", "completed", "cancelled", "superseded"},
        "blocked": {"active", "cancelled", "superseded"},
        "review": {"active", "completed", "superseded"},
    },
    "generated": {
        "current": {"stale", "superseded"},
        "stale": {"current", "superseded"},
    },
}

REQUIRED_FIELDS = {
    "schema_version",
    "id",
    "slug",
    "title",
    "type",
    "status",
    "created_at",
    "updated_at",
    "status_changed_at",
}
LIFECYCLE_MARKERS = {"schema_version", "id", "slug", "type", "status"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
INLINE_LINK_RE = re.compile(
    r"(?P<prefix>!?\[[^\]\n]*\]\()(?P<dest><[^>\n]+>|[^\s)]+)"
    r"(?P<title>\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?(?P<suffix>\))"
)
REFERENCE_LINK_RE = re.compile(
    r"(?m)^(?P<prefix>\s*\[[^\]\n]+\]:\s*)(?P<dest><[^>\n]+>|\S+)"
)


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str

    def render(self) -> str:
        location = f" {self.path}" if self.path else ""
        return f"{self.severity} [{self.code}]{location}: {self.message}"


@dataclass
class Document:
    path: Path
    relative_path: str
    text: str
    metadata: dict[str, Any]
    body: str

    @property
    def document_id(self) -> str:
        return scalar_text(self.metadata.get("id"))


@dataclass
class ScanResult:
    documents: list[Document]
    issues: list[Issue]
    legacy_count: int


class GuardFailure(RuntimeError):
    pass


def scalar_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return ""
    return str(value)


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return None
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1].replace("''", "'")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in inner.split(",")]
    return value


def parse_yaml_subset(source: str) -> dict[str, Any]:
    """Parse the mapping/list/scalar subset used by guard config and metadata."""

    raw_lines = []
    for number, raw in enumerate(source.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise GuardFailure(f"YAML line {number} uses a tab for indentation")
        raw_lines.append((number, len(raw) - len(raw.lstrip(" ")), raw.strip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(raw_lines):
            return {}, index
        is_list = raw_lines[index][2].startswith("- ")
        container: Any = [] if is_list else {}
        while index < len(raw_lines):
            number, current_indent, content = raw_lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise GuardFailure(f"unexpected indentation on YAML line {number}")
            if is_list:
                if not content.startswith("- "):
                    raise GuardFailure(f"mixed list and mapping on YAML line {number}")
                item = content[2:].strip()
                container.append(parse_scalar(item))
                index += 1
                continue
            if content.startswith("- ") or ":" not in content:
                raise GuardFailure(f"invalid mapping entry on YAML line {number}")
            key, raw_value = content.split(":", 1)
            key = key.strip()
            if not key:
                raise GuardFailure(f"empty mapping key on YAML line {number}")
            raw_value = raw_value.strip()
            index += 1
            if raw_value:
                container[key] = parse_scalar(raw_value)
                continue
            if index < len(raw_lines) and raw_lines[index][1] > indent:
                child_indent = raw_lines[index][1]
                child, index = parse_block(index, child_indent)
                container[key] = child
            else:
                container[key] = None
        return container, index

    if not raw_lines:
        return {}
    result, next_index = parse_block(0, raw_lines[0][1])
    if next_index != len(raw_lines) or not isinstance(result, dict):
        raise GuardFailure("YAML root must be a mapping")
    return result


def yaml_mapping(source: str, label: str) -> dict[str, Any]:
    try:
        if yaml is not None:
            parsed = yaml.safe_load(source)
            if parsed is None:
                return {}
            if not isinstance(parsed, dict):
                raise GuardFailure(f"{label} must contain a YAML mapping")
            return parsed
        return parse_yaml_subset(source)
    except GuardFailure:
        raise
    except Exception as exc:
        raise GuardFailure(f"cannot parse {label}: {exc}") from exc


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def safe_relative_path(value: str, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise GuardFailure(f"{label} must be a repository-relative path without '..'")
    return path


def find_repo(start: Path) -> Path:
    candidate = start.resolve()
    if candidate.is_file():
        candidate = candidate.parent
    result = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip()).resolve()
    for parent in (candidate, *candidate.parents):
        if (parent / ".git-commit-guard.yml").exists():
            return parent
    return candidate


def has_commits(repo: Path) -> bool:
    """Report whether HEAD resolves, so a fresh repository is not compared to nothing."""

    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "HEAD"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def baseline_ref(repo: Path) -> str | None:
    return "HEAD" if has_commits(repo) else None


def load_config(repo: Path, config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or repo / ".git-commit-guard.yml"
    override: dict[str, Any] = {}
    if path.exists():
        override = yaml_mapping(path.read_text(encoding="utf-8-sig"), str(path))
    config = deep_merge(DEFAULT_CONFIG, override)
    if config.get("version") != 1:
        raise GuardFailure("only .git-commit-guard.yml version 1 is supported")
    documentation = config.get("documentation")
    if not isinstance(documentation, dict):
        raise GuardFailure("configuration key 'documentation' must be a mapping")
    safe_relative_path(str(documentation.get("root", "docs")), "documentation.root")
    directories = documentation.get("directories", {})
    if not isinstance(directories, dict):
        raise GuardFailure("documentation.directories must be a mapping")
    for key in ("plan", "migration", "generated", "archive"):
        value = str(directories.get(key, ""))
        if not value:
            raise GuardFailure(f"documentation.directories.{key} must not be empty")
        safe_relative_path(value, f"documentation.directories.{key}")
    pattern = scalar_text(documentation.get("filename", {}).get("pattern"))
    if any(separator in pattern for separator in ("/", "\\")):
        raise GuardFailure("documentation.filename.pattern must be a filename, not a path")
    for placeholder in ("{created_date}", "{status}", "{slug}"):
        if placeholder not in pattern:
            raise GuardFailure(f"documentation.filename.pattern must contain {placeholder}")
    validation = documentation.get("validation", {})
    for hard_rule in ("unique_id", "enforce_frontmatter", "fail_on_invalid_transition"):
        if validation.get(hard_rule, True) is not True:
            raise GuardFailure(f"documentation.validation.{hard_rule} is a non-disableable lifecycle invariant")
    return config


def docs_root(repo: Path, config: dict[str, Any]) -> Path:
    return (repo / safe_relative_path(str(config["documentation"]["root"]), "documentation.root")).resolve()


def split_frontmatter(text: str) -> tuple[str, str] | None:
    normalized = text.lstrip("\ufeff")
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise GuardFailure("frontmatter has no closing '---'")


def parse_document(path: Path, repo: Path) -> tuple[Document | None, Issue | None, bool]:
    relative = path.relative_to(repo).as_posix()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        return None, Issue("ERROR", "ENCODING", relative, f"must be UTF-8: {exc}"), False
    try:
        parts = split_frontmatter(text)
    except GuardFailure as exc:
        return None, Issue("ERROR", "FRONTMATTER", relative, str(exc)), False
    if parts is None:
        return None, None, True
    frontmatter, body = parts
    try:
        metadata = yaml_mapping(frontmatter, f"frontmatter in {relative}")
    except GuardFailure as exc:
        return None, Issue("ERROR", "FRONTMATTER", relative, str(exc)), False
    markers = LIFECYCLE_MARKERS.intersection(metadata)
    if "id" not in metadata:
        if len(markers) >= 2:
            return (
                None,
                Issue(
                    "WARNING",
                    "PARTIAL_METADATA",
                    relative,
                    "lifecycle-like frontmatter has no immutable id and remains unmanaged",
                ),
                True,
            )
        return None, None, True
    return Document(path, relative, text, metadata, body), None, False


def scan_documents(repo: Path, config: dict[str, Any]) -> ScanResult:
    root = docs_root(repo, config)
    documents: list[Document] = []
    issues: list[Issue] = []
    legacy_count = 0
    if not root.exists():
        return ScanResult(documents, issues, legacy_count)
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        document, issue, legacy = parse_document(path, repo)
        if issue:
            issues.append(issue)
        if document:
            documents.append(document)
        elif legacy:
            legacy_count += 1
    return ScanResult(documents, issues, legacy_count)


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    raw = scalar_text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [scalar_text(item) for item in value if scalar_text(item)]


def is_terminal(document_type: str, status: str) -> bool:
    rules = TYPE_RULES.get(document_type)
    return bool(rules and status in rules["terminal"])


def expected_path(document: Document, repo: Path, config: dict[str, Any]) -> Path | None:
    document_type = scalar_text(document.metadata.get("type"))
    status = scalar_text(document.metadata.get("status"))
    slug = scalar_text(document.metadata.get("slug"))
    created = parse_timestamp(document.metadata.get("created_at"))
    if document_type not in TYPE_RULES or not status or not slug or created is None:
        return None
    documentation = config["documentation"]
    root = docs_root(repo, config)
    directories = documentation["directories"]
    filename = documentation["filename"]["pattern"].format(
        created_date=created.strftime(documentation["filename"]["date_format"]),
        status=status,
        slug=slug,
    )
    if is_terminal(document_type, status):
        parent = root / str(directories["archive"])
        if documentation["archive"].get("preserve_type", True):
            parent /= str(directories[document_type])
        if documentation["archive"].get("partition_by_year", True):
            parent /= created.strftime("%Y")
    else:
        parent = root / str(directories[document_type])
    return (parent / filename).resolve()


def validate_document_shape(document: Document, repo: Path, config: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    metadata = document.metadata
    missing = sorted(REQUIRED_FIELDS.difference(metadata))
    for field in missing:
        issues.append(Issue("ERROR", "MISSING_FIELD", document.relative_path, f"missing '{field}'"))
    if metadata.get("schema_version") != 1:
        issues.append(Issue("ERROR", "SCHEMA_VERSION", document.relative_path, "schema_version must be 1"))

    document_type = scalar_text(metadata.get("type"))
    status = scalar_text(metadata.get("status"))
    slug = scalar_text(metadata.get("slug"))
    document_id = scalar_text(metadata.get("id"))
    rules = TYPE_RULES.get(document_type)
    if rules is None:
        issues.append(Issue("ERROR", "TYPE", document.relative_path, f"invalid type '{document_type}'"))
    else:
        allowed_statuses = rules["live"] | rules["terminal"]
        if status not in allowed_statuses:
            issues.append(Issue("ERROR", "STATUS", document.relative_path, f"invalid {document_type} status '{status}'"))
        created = parse_timestamp(metadata.get("created_at"))
        id_pattern = rf"^{rules['prefix']}-\d{{8}}-\d{{3,}}$"
        if not re.fullmatch(id_pattern, document_id):
            issues.append(Issue("ERROR", "DOCUMENT_ID", document.relative_path, f"id must match {id_pattern}"))
        elif created and document_id.split("-")[1] != created.strftime("%Y%m%d"):
            issues.append(Issue("ERROR", "DOCUMENT_ID_DATE", document.relative_path, "id date must match created_at date"))

    if not SLUG_RE.fullmatch(slug):
        issues.append(Issue("ERROR", "SLUG", document.relative_path, "slug must be lowercase ASCII kebab-case"))
    if not scalar_text(metadata.get("title")).strip():
        issues.append(Issue("ERROR", "TITLE", document.relative_path, "title must not be empty"))

    timestamps: dict[str, datetime] = {}
    for field in ("created_at", "updated_at", "status_changed_at"):
        parsed = parse_timestamp(metadata.get(field))
        if parsed is None or parsed.utcoffset() is None:
            issues.append(Issue("ERROR", "TIMESTAMP", document.relative_path, f"{field} must be ISO 8601 with timezone"))
        else:
            timestamps[field] = parsed
    if timestamps.get("updated_at") and timestamps.get("created_at") and timestamps["updated_at"] < timestamps["created_at"]:
        issues.append(Issue("ERROR", "TIMESTAMP_ORDER", document.relative_path, "updated_at precedes created_at"))
    if timestamps.get("status_changed_at") and timestamps.get("created_at") and timestamps["status_changed_at"] < timestamps["created_at"]:
        issues.append(Issue("ERROR", "TIMESTAMP_ORDER", document.relative_path, "status_changed_at precedes created_at"))
    if timestamps.get("status_changed_at") and timestamps.get("updated_at") and timestamps["status_changed_at"] > timestamps["updated_at"]:
        issues.append(Issue("ERROR", "TIMESTAMP_ORDER", document.relative_path, "status_changed_at exceeds updated_at"))

    terminal = bool(rules and status in rules["terminal"])
    archived = parse_timestamp(metadata.get("archived_at"))
    if terminal and (archived is None or archived.utcoffset() is None):
        issues.append(Issue("ERROR", "ARCHIVED_AT", document.relative_path, "terminal document requires archived_at with timezone"))
    if document_type == "generated":
        if metadata.get("generated") is not True:
            issues.append(Issue("ERROR", "GENERATED_FLAG", document.relative_path, "generated document requires generated: true"))
        for field in ("generated_at", "generator"):
            if not metadata.get(field):
                issues.append(Issue("WARNING", "GENERATION_METADATA", document.relative_path, f"generated document should define {field}"))
        if not list_value(metadata.get("source")):
            issues.append(Issue("WARNING", "GENERATED_SOURCE", document.relative_path, "generated document should list reproducible source inputs"))

    expected = expected_path(document, repo, config)
    if expected is not None and document.path.resolve() != expected:
        issues.append(
            Issue(
                "ERROR",
                "PATH_PROJECTION",
                document.relative_path,
                f"frontmatter projects to {expected.relative_to(repo).as_posix()}",
            )
        )

    if rules:
        headings = set(HEADING_RE.findall(document.body))
        for heading in sorted(set(rules["headings"]) - headings):
            issues.append(Issue("WARNING", "MISSING_SECTION", document.relative_path, f"missing recommended section '## {heading}'"))
    return issues


def link_parts(destination: str) -> tuple[str, str, str, bool]:
    angled = destination.startswith("<") and destination.endswith(">")
    raw = destination[1:-1] if angled else destination
    fragment = ""
    query = ""
    if "#" in raw:
        raw, suffix = raw.split("#", 1)
        fragment = f"#{suffix}"
    if "?" in raw:
        raw, suffix = raw.split("?", 1)
        query = f"?{suffix}"
    return raw, query, fragment, angled


def local_link_target(destination: str, source: Path, repo: Path) -> Path | None:
    raw, _, _, _ = link_parts(destination)
    if not raw or raw.startswith("#") or "{{" in raw or "${" in raw:
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw) or raw.startswith("//"):
        return None
    decoded = unquote(raw).replace("\\", "/")
    if decoded.startswith("/"):
        target = repo / decoded.lstrip("/")
    else:
        target = source.parent / decoded
    try:
        resolved = target.resolve()
        resolved.relative_to(repo.resolve())
        return resolved
    except (OSError, ValueError):
        return None


def iter_link_matches(text: str) -> Iterable[re.Match[str]]:
    yield from INLINE_LINK_RE.finditer(text)
    yield from REFERENCE_LINK_RE.finditer(text)


def markdown_files(repo: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.md",
            "*.mdx",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return sorted({repo / relative for relative in result.stdout.splitlines() if relative})
    return sorted({*repo.rglob("*.md"), *repo.rglob("*.mdx")})


def validate_links(repo: Path, config: dict[str, Any], documents: list[Document]) -> list[Issue]:
    issues: list[Issue] = []
    if not documents:
        return issues
    managed_paths = {document.path.resolve() for document in documents}
    root = docs_root(repo, config)
    for path in markdown_files(repo):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        for match in iter_link_matches(text):
            destination = match.group("dest")
            target = local_link_target(destination, path, repo)
            if target is None or target.exists():
                continue
            try:
                points_into_docs = target.is_relative_to(root)
            except AttributeError:  # pragma: no cover - Python 3.8 compatibility
                points_into_docs = root in target.parents
            if path.resolve() in managed_paths or points_into_docs:
                issues.append(
                    Issue(
                        "ERROR",
                        "BROKEN_LINK",
                        path.relative_to(repo).as_posix(),
                        f"local link target does not exist: {destination}",
                    )
                )
    return issues


def validate_relationships(documents: list[Document]) -> list[Issue]:
    issues: list[Issue] = []
    by_id = {document.document_id: document for document in documents if document.document_id}
    relation_fields = ("supersedes", "superseded_by", "related", "depends_on")
    for document in documents:
        for field in relation_fields:
            raw = document.metadata.get(field, [])
            if raw is not None and not isinstance(raw, list):
                issues.append(Issue("ERROR", "RELATION_TYPE", document.relative_path, f"{field} must be a list of document IDs"))
                continue
            for target_id in list_value(raw):
                if target_id == document.document_id:
                    issues.append(Issue("ERROR", "SELF_RELATION", document.relative_path, f"{field} cannot reference its own id"))
                elif target_id not in by_id:
                    issues.append(Issue("ERROR", "UNKNOWN_RELATION", document.relative_path, f"{field} references unknown id {target_id}"))
        for older_id in list_value(document.metadata.get("supersedes")):
            older = by_id.get(older_id)
            if older and document.document_id not in list_value(older.metadata.get("superseded_by")):
                issues.append(Issue("ERROR", "RELATION_RECIPROCITY", document.relative_path, f"{older_id} does not list this document in superseded_by"))
        for newer_id in list_value(document.metadata.get("superseded_by")):
            newer = by_id.get(newer_id)
            if newer and document.document_id not in list_value(newer.metadata.get("supersedes")):
                issues.append(Issue("ERROR", "RELATION_RECIPROCITY", document.relative_path, f"{newer_id} does not list this document in supersedes"))
        status = scalar_text(document.metadata.get("status"))
        if status == "superseded" and not list_value(document.metadata.get("superseded_by")):
            issues.append(Issue("ERROR", "SUPERSEDED_BY", document.relative_path, "superseded document requires superseded_by"))
    return issues


def git_text(repo: Path, ref: str, relative_path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{relative_path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8-sig")


def scan_git_ref(repo: Path, config: dict[str, Any], ref: str) -> dict[str, Document]:
    root_relative = safe_relative_path(str(config["documentation"]["root"]), "documentation.root").as_posix()
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref, "--", root_relative],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GuardFailure(f"cannot read git reference '{ref}'")
    documents: dict[str, Document] = {}
    for relative in result.stdout.splitlines():
        if not relative.lower().endswith(".md"):
            continue
        text = git_text(repo, ref, relative)
        if text is None:
            continue
        try:
            parts = split_frontmatter(text)
            if parts is None:
                continue
            metadata = yaml_mapping(parts[0], f"{ref}:{relative}")
        except GuardFailure:
            continue
        document_id = scalar_text(metadata.get("id"))
        if document_id:
            documents[document_id] = Document(repo / relative, relative, text, metadata, parts[1])
    return documents


def validate_history(repo: Path, config: dict[str, Any], documents: list[Document], base_ref: str) -> list[Issue]:
    issues: list[Issue] = []
    old_by_id = scan_git_ref(repo, config, base_ref)
    current_by_id = {document.document_id: document for document in documents}
    for document_id, old in old_by_id.items():
        current = current_by_id.get(document_id)
        if current is None:
            issues.append(Issue("ERROR", "DOCUMENT_DISAPPEARED", old.relative_path, f"managed id {document_id} was removed or changed; preserve and archive it"))
            continue
        for field in ("created_at", "slug"):
            if scalar_text(old.metadata.get(field)) != scalar_text(current.metadata.get(field)):
                issues.append(Issue("ERROR", "IMMUTABLE_FIELD", current.relative_path, f"{field} changed relative to {base_ref}"))
        old_status = scalar_text(old.metadata.get("status"))
        current_status = scalar_text(current.metadata.get("status"))
        document_type = scalar_text(current.metadata.get("type"))
        if scalar_text(old.metadata.get("type")) != document_type:
            issues.append(Issue("ERROR", "IMMUTABLE_FIELD", current.relative_path, f"type changed relative to {base_ref}"))
        if old_status != current_status:
            allowed = TRANSITIONS.get(document_type, {}).get(old_status, set())
            if current_status not in allowed:
                issues.append(Issue("ERROR", "INVALID_TRANSITION", current.relative_path, f"illegal transition {old_status} -> {current_status}"))
            if scalar_text(old.metadata.get("status_changed_at")) == scalar_text(current.metadata.get("status_changed_at")):
                issues.append(Issue("ERROR", "STATUS_TIMESTAMP", current.relative_path, "status_changed_at was not advanced"))
        if old.text != current.text:
            old_updated = parse_timestamp(old.metadata.get("updated_at"))
            current_updated = parse_timestamp(current.metadata.get("updated_at"))
            if old_updated and current_updated and current_updated <= old_updated:
                issues.append(Issue("ERROR", "UPDATED_AT", current.relative_path, "updated_at must advance when content or metadata changes"))
    return issues


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_index(repo: Path, config: dict[str, Any], documents: list[Document]) -> str:
    root = docs_root(repo, config)
    groups = [
        ("Active Plans", lambda doc: scalar_text(doc.metadata.get("type")) == "plan" and not is_terminal("plan", scalar_text(doc.metadata.get("status")))),
        ("Active Migrations", lambda doc: scalar_text(doc.metadata.get("type")) == "migration" and not is_terminal("migration", scalar_text(doc.metadata.get("status")))),
        ("Generated Documents", lambda doc: scalar_text(doc.metadata.get("type")) == "generated" and not is_terminal("generated", scalar_text(doc.metadata.get("status")))),
        ("Archived", lambda doc: is_terminal(scalar_text(doc.metadata.get("type")), scalar_text(doc.metadata.get("status")))),
    ]
    lines = [
        "# Documentation Index",
        "",
        "<!-- Generated by git-commit-guard. Do not edit manually. -->",
        "",
    ]
    for heading, predicate in groups:
        selected = sorted((doc for doc in documents if predicate(doc)), key=lambda doc: doc.document_id)
        lines.extend([f"## {heading}", ""])
        if not selected:
            lines.extend(["_None._", ""])
            continue
        lines.extend(["| ID | Status | Title | Updated |", "|---|---|---|---|"])
        for document in selected:
            path = os.path.relpath(document.path, root).replace("\\", "/")
            title = escape_table(scalar_text(document.metadata.get("title")))
            updated = scalar_text(document.metadata.get("updated_at"))[:10]
            lines.append(f"| {document.document_id} | {scalar_text(document.metadata.get('status'))} | [{title}]({path}) | {updated} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_registry(documents: list[Document], repo: Path) -> str:
    registry: dict[str, Any] = {}
    for document in sorted(documents, key=lambda doc: doc.document_id):
        registry[document.document_id] = {
            "type": scalar_text(document.metadata.get("type")),
            "status": scalar_text(document.metadata.get("status")),
            "title": scalar_text(document.metadata.get("title")),
            "created_at": scalar_text(document.metadata.get("created_at")),
            "updated_at": scalar_text(document.metadata.get("updated_at")),
            "path": document.path.relative_to(repo).as_posix(),
        }
    return json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def generated_paths(repo: Path, config: dict[str, Any]) -> tuple[Path, Path]:
    root = docs_root(repo, config)
    index_config = config["documentation"].get("index", {})
    return root / str(index_config.get("path", "INDEX.md")), root / str(index_config.get("registry", ".registry.json"))


def validate_generated_artifacts(repo: Path, config: dict[str, Any], documents: list[Document]) -> list[Issue]:
    if not documents or not config["documentation"].get("index", {}).get("enabled", True):
        return []
    index_path, registry_path = generated_paths(repo, config)
    expected = ((index_path, render_index(repo, config, documents)), (registry_path, render_registry(documents, repo)))
    issues: list[Issue] = []
    for path, content in expected:
        relative = path.relative_to(repo).as_posix()
        if not path.exists():
            issues.append(Issue("ERROR", "GENERATED_ARTIFACT", relative, "missing; run docs_guard.py index"))
        elif path.read_text(encoding="utf-8-sig") != content:
            issues.append(Issue("ERROR", "GENERATED_ARTIFACT", relative, "stale; run docs_guard.py index"))
    return issues


def collect_issues(
    repo: Path,
    config: dict[str, Any],
    *,
    base_ref: str | None = None,
    check_generated: bool = True,
) -> tuple[ScanResult, list[Issue]]:
    scan = scan_documents(repo, config)
    issues = list(scan.issues)
    seen: dict[str, Document] = {}
    for document in scan.documents:
        issues.extend(validate_document_shape(document, repo, config))
        if document.document_id in seen:
            issues.append(Issue("ERROR", "DUPLICATE_ID", document.relative_path, f"duplicate id also used by {seen[document.document_id].relative_path}"))
        else:
            seen[document.document_id] = document
    issues.extend(validate_relationships(scan.documents))
    if config["documentation"].get("validation", {}).get("validate_links", True):
        issues.extend(validate_links(repo, config, scan.documents))
    if base_ref:
        issues.extend(validate_history(repo, config, scan.documents, base_ref))
    if check_generated:
        issues.extend(validate_generated_artifacts(repo, config, scan.documents))
    issues.sort(key=lambda issue: (issue.severity != "ERROR", issue.path, issue.code, issue.message))
    return scan, issues


def print_report(scan: ScanResult, issues: list[Issue]) -> int:
    for issue in issues:
        print(issue.render())
    errors = sum(issue.severity == "ERROR" for issue in issues)
    warnings = sum(issue.severity == "WARNING" for issue in issues)
    print(f"Summary: {len(scan.documents)} managed, {scan.legacy_count} legacy/exempt, {errors} errors, {warnings} warnings")
    return 1 if errors else 0


def refresh_index(repo: Path, config: dict[str, Any], *, check_only: bool = False) -> bool:
    scan, issues = collect_issues(repo, config, check_generated=False)
    errors = [issue for issue in issues if issue.severity == "ERROR"]
    if errors:
        for issue in errors:
            print(issue.render(), file=sys.stderr)
        raise GuardFailure("cannot refresh index while documentation errors exist")
    if not config["documentation"].get("index", {}).get("enabled", True):
        return False
    index_path, registry_path = generated_paths(repo, config)
    outputs = ((index_path, render_index(repo, config, scan.documents)), (registry_path, render_registry(scan.documents, repo)))
    changed = False
    for path, content in outputs:
        current = path.read_text(encoding="utf-8-sig") if path.exists() else None
        if current != content:
            changed = True
            if not check_only:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
    return changed


def yaml_scalar(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return scalar_text(value)


def update_frontmatter(text: str, changes: dict[str, Any]) -> str:
    lines = text.lstrip("\ufeff").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise GuardFailure("cannot update document without frontmatter")
    closing = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if closing is None:
        raise GuardFailure("cannot update unclosed frontmatter")
    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    index = 1
    while index < closing:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):", lines[index])
        if not match or match.group(1) not in changes:
            index += 1
            continue
        key = match.group(1)
        end = index + 1
        while end < closing and (lines[end].startswith(" ") or lines[end].startswith("\t")):
            end += 1
        lines[index:end] = [f"{key}: {yaml_scalar(changes.pop(key))}{newline}"]
        closing -= end - index - 1
        index += 1
    if changes:
        additions = [f"{key}: {yaml_scalar(value)}{newline}" for key, value in changes.items()]
        lines[closing:closing] = additions
    return "".join(lines)


def rewrite_destination(destination: str, source_before: Path, source_after: Path, old_path: Path, new_path: Path, repo: Path) -> str:
    target = local_link_target(destination, source_before, repo)
    if target is None:
        return destination
    if target == old_path.resolve():
        target = new_path.resolve()
    raw, query, fragment, angled = link_parts(destination)
    if raw.startswith("/"):
        replacement = "/" + target.relative_to(repo).as_posix()
    else:
        replacement = os.path.relpath(target, source_after.parent).replace("\\", "/")
        if replacement == ".":
            replacement = source_after.name
    replacement = f"{replacement}{query}{fragment}"
    return f"<{replacement}>" if angled else replacement


def rewrite_links(text: str, source_before: Path, source_after: Path, old_path: Path, new_path: Path, repo: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        destination = match.group("dest")
        rewritten = rewrite_destination(destination, source_before, source_after, old_path, new_path, repo)
        start, end = match.span("dest")
        relative_start = start - match.start()
        relative_end = end - match.start()
        whole = match.group(0)
        return whole[:relative_start] + rewritten + whole[relative_end:]

    text = INLINE_LINK_RE.sub(replace, text)
    return REFERENCE_LINK_RE.sub(replace, text)


def tracked(repo: Path, path: Path) -> bool:
    relative = path.relative_to(repo).as_posix()
    result = subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", relative], capture_output=True, check=False)
    return result.returncode == 0


def staged(repo: Path, path: Path) -> bool:
    relative = path.relative_to(repo).as_posix()
    result = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet", "--", relative], check=False)
    return result.returncode == 1


def move_document(repo: Path, old_path: Path, new_path: Path, use_git: bool) -> None:
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if new_path.exists():
        raise GuardFailure(f"destination already exists: {new_path}")
    if use_git:
        result = subprocess.run(
            ["git", "-C", str(repo), "mv", "--", old_path.relative_to(repo).as_posix(), new_path.relative_to(repo).as_posix()],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise GuardFailure(result.stderr.strip() or "git mv failed")
    else:
        shutil.move(str(old_path), str(new_path))


def capture(paths: Iterable[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.exists() else None for path in set(paths)}


def restore_files(snapshot: dict[Path, bytes | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def rewrite_repository_links(repo: Path, old_path: Path, new_path: Path) -> list[Path]:
    changed: list[Path] = []
    for path in markdown_files(repo):
        if not path.is_file() or ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8-sig")
        rewritten = rewrite_links(text, path, path, old_path, new_path, repo)
        if rewritten != text:
            path.write_text(rewritten, encoding="utf-8", newline="")
            changed.append(path)
    return changed


def choose_timestamp(raw: str | None) -> str:
    if raw:
        parsed = parse_timestamp(raw)
        if parsed is None or parsed.utcoffset() is None:
            raise GuardFailure("--at must be ISO 8601 with timezone")
        return parsed.isoformat(timespec="seconds")
    return datetime.now().astimezone().isoformat(timespec="seconds")


def find_document_by_id(documents: list[Document], document_id: str) -> Document | None:
    return next((document for document in documents if document.document_id == document_id), None)


def perform_transition(
    repo: Path,
    config: dict[str, Any],
    source_path: Path,
    new_status: str,
    *,
    at: str | None = None,
    superseded_by: str | None = None,
    dry_run: bool = False,
) -> Path:
    base_ref = baseline_ref(repo)
    scan, baseline_issues = collect_issues(repo, config, base_ref=base_ref)
    baseline_errors = [issue for issue in baseline_issues if issue.severity == "ERROR"]
    if baseline_errors:
        for issue in baseline_errors:
            print(issue.render(), file=sys.stderr)
        raise GuardFailure("transition requires a valid baseline")
    source_path = source_path.resolve()
    source = next((document for document in scan.documents if document.path.resolve() == source_path), None)
    if source is None:
        raise GuardFailure("source is not a lifecycle-managed document")
    document_type = scalar_text(source.metadata.get("type"))
    old_status = scalar_text(source.metadata.get("status"))
    allowed = TRANSITIONS.get(document_type, {}).get(old_status, set())
    if new_status not in allowed:
        raise GuardFailure(f"illegal transition {old_status} -> {new_status}")
    if new_status == "superseded" and not superseded_by:
        raise GuardFailure("transition to superseded requires --superseded-by ID")
    successor = find_document_by_id(scan.documents, superseded_by) if superseded_by else None
    if superseded_by and successor is None:
        raise GuardFailure(f"unknown successor id {superseded_by}")
    if successor:
        if scalar_text(successor.metadata.get("type")) != document_type:
            raise GuardFailure("successor must have the same document type")
        if is_terminal(document_type, scalar_text(successor.metadata.get("status"))):
            raise GuardFailure("successor must be non-terminal")
    timestamp = choose_timestamp(at)
    changes: dict[str, Any] = {
        "status": new_status,
        "updated_at": timestamp,
        "status_changed_at": timestamp,
    }
    if is_terminal(document_type, new_status):
        changes["archived_at"] = timestamp
    if successor:
        changes["superseded_by"] = sorted(set(list_value(source.metadata.get("superseded_by"))) | {successor.document_id})
    preview_metadata = dict(source.metadata)
    preview_metadata.update(changes)
    preview = Document(source.path, source.relative_path, source.text, preview_metadata, source.body)
    destination = expected_path(preview, repo, config)
    if destination is None:
        raise GuardFailure("cannot derive transition destination")
    if destination != source_path and destination.exists():
        raise GuardFailure(f"destination already exists: {destination}")
    print(f"Transition: {source.document_id} {old_status} -> {new_status}")
    print(f"Move: {source_path.relative_to(repo).as_posix()} -> {destination.relative_to(repo).as_posix()}")
    if dry_run:
        return destination

    use_git = tracked(repo, source_path)
    if use_git and staged(repo, source_path):
        raise GuardFailure("source has staged changes; commit or unstage them before transition")
    if successor and tracked(repo, successor.path) and staged(repo, successor.path):
        raise GuardFailure("successor has staged changes; commit or unstage them before transition")

    markdown_paths = markdown_files(repo)
    index_path, registry_path = generated_paths(repo, config)
    snapshot = capture([*markdown_paths, index_path, registry_path, destination])
    moved = False
    try:
        updated_source = update_frontmatter(source.text, dict(changes))
        updated_source = rewrite_links(updated_source, source_path, destination, source_path, destination, repo)
        source_path.write_text(updated_source, encoding="utf-8", newline="")
        if successor:
            successor_changes = {
                "supersedes": sorted(set(list_value(successor.metadata.get("supersedes"))) | {source.document_id}),
                "updated_at": timestamp,
            }
            successor.path.write_text(update_frontmatter(successor.text, successor_changes), encoding="utf-8", newline="")
        if destination != source_path:
            move_document(repo, source_path, destination, use_git)
            moved = True
        rewrite_repository_links(repo, source_path, destination)
        refresh_index(repo, config)
        _, final_issues = collect_issues(repo, config, base_ref=base_ref)
        errors = [issue for issue in final_issues if issue.severity == "ERROR"]
        if errors:
            raise GuardFailure("; ".join(issue.render() for issue in errors))
    except Exception:
        if moved and destination.exists() and not source_path.exists():
            if use_git:
                subprocess.run(
                    ["git", "-C", str(repo), "mv", "--", destination.relative_to(repo).as_posix(), source_path.relative_to(repo).as_posix()],
                    capture_output=True,
                    check=False,
                )
                subprocess.run(
                    ["git", "-C", str(repo), "restore", "--staged", "--", source_path.relative_to(repo).as_posix()],
                    capture_output=True,
                    check=False,
                )
            else:
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source_path))
        restore_files(snapshot)
        raise
    return destination


def allocate_document_id(documents: list[Document], prefix: str, created_date: str) -> str:
    """Return the next free sequence for the type/date pair instead of guessing one."""

    taken = set()
    pattern = re.compile(rf"^{prefix}-{created_date}-(\d+)$")
    for document in documents:
        match = pattern.match(document.document_id)
        if match:
            taken.add(int(match.group(1)))
    sequence = next(number for number in range(1, max(taken, default=0) + 2) if number not in taken)
    return f"{prefix}-{created_date}-{sequence:03d}"


def render_new_document(
    document_id: str,
    slug: str,
    title: str,
    document_type: str,
    status: str,
    timestamp: str,
    *,
    owner: str | None = None,
    generator: str | None = None,
) -> str:
    frontmatter = [
        "schema_version: 1",
        f"id: {document_id}",
        f"slug: {slug}",
        f"title: {title}",
        f"type: {document_type}",
        f"status: {status}",
        f"created_at: {timestamp}",
        f"updated_at: {timestamp}",
        f"status_changed_at: {timestamp}",
    ]
    if document_type == "generated":
        frontmatter.extend(
            [
                "generated: true",
                f"generated_at: {timestamp}",
                f"generator: {generator or 'codex'}",
                "source: []",
                "generation_command: null",
            ]
        )
    frontmatter.extend(
        [
            f"owner: {owner or 'null'}",
            "supersedes: []",
            "superseded_by: []",
            "related: []",
            "depends_on: []",
        ]
    )
    body = [f"# {title}", ""]
    for heading in TYPE_RULES[document_type]["headings"]:
        body.extend([f"## {heading}", ""])
    return "---\n" + "\n".join(frontmatter) + "\n---\n\n" + "\n".join(body).rstrip() + "\n"


def perform_new(
    repo: Path,
    config: dict[str, Any],
    document_type: str,
    slug: str,
    *,
    title: str | None = None,
    status: str | None = None,
    at: str | None = None,
    owner: str | None = None,
    generator: str | None = None,
    dry_run: bool = False,
) -> Path:
    rules = TYPE_RULES.get(document_type)
    if rules is None:
        raise GuardFailure(f"invalid type '{document_type}'; expected one of {', '.join(sorted(TYPE_RULES))}")
    if not SLUG_RE.fullmatch(slug):
        raise GuardFailure("slug must be lowercase ASCII kebab-case")
    status = status or str(rules["initial"])
    if status in rules["terminal"]:
        raise GuardFailure(f"cannot create a document directly in terminal status '{status}'")
    if status not in rules["live"]:
        raise GuardFailure(f"invalid {document_type} status '{status}'")

    scan, baseline_issues = collect_issues(repo, config, check_generated=False)
    baseline_errors = [issue for issue in baseline_issues if issue.severity == "ERROR"]
    if baseline_errors:
        for issue in baseline_errors:
            print(issue.render(), file=sys.stderr)
        raise GuardFailure("creating a document requires a valid baseline")
    if any(scalar_text(document.metadata.get("slug")) == slug for document in scan.documents):
        raise GuardFailure(f"slug '{slug}' is already used by a managed document")

    timestamp = choose_timestamp(at)
    created = parse_timestamp(timestamp)
    assert created is not None
    document_id = allocate_document_id(scan.documents, str(rules["prefix"]), created.strftime("%Y%m%d"))
    title = title or slug.replace("-", " ").title()
    text = render_new_document(
        document_id,
        slug,
        title,
        document_type,
        status,
        timestamp,
        owner=owner,
        generator=generator,
    )
    preview = Document(repo, "", text, yaml_mapping(split_frontmatter(text)[0], "new document"), "")
    destination = expected_path(preview, repo, config)
    if destination is None:
        raise GuardFailure("cannot derive destination for the new document")
    if destination.exists():
        raise GuardFailure(f"destination already exists: {destination}")

    print(f"Create: {document_id} ({document_type}/{status})")
    print(f"Path: {destination.relative_to(repo).as_posix()}")
    if dry_run:
        return destination

    index_path, registry_path = generated_paths(repo, config)
    snapshot = capture([index_path, registry_path])
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8", newline="\n")
        refresh_index(repo, config)
        _, final_issues = collect_issues(repo, config)
        errors = [issue for issue in final_issues if issue.severity == "ERROR"]
        if errors:
            raise GuardFailure("; ".join(issue.render() for issue in errors))
        for issue in final_issues:
            if issue.severity == "WARNING" and issue.path == destination.relative_to(repo).as_posix():
                print(issue.render())
    except Exception:
        if destination.exists():
            destination.unlink()
        restore_files(snapshot)
        raise
    return destination


def perform_link_successor(
    repo: Path,
    config: dict[str, Any],
    old_path: Path,
    successor_path: Path,
    *,
    at: str | None = None,
    dry_run: bool = False,
) -> Path:
    base_ref = baseline_ref(repo)
    scan, issues = collect_issues(repo, config, base_ref=base_ref)
    errors = [issue for issue in issues if issue.severity == "ERROR"]
    if errors:
        for issue in errors:
            print(issue.render(), file=sys.stderr)
        raise GuardFailure("link-successor requires a valid baseline")
    old = next((document for document in scan.documents if document.path.resolve() == old_path.resolve()), None)
    successor = next((document for document in scan.documents if document.path.resolve() == successor_path.resolve()), None)
    if old is None or successor is None:
        raise GuardFailure("both paths must be lifecycle-managed documents")
    if old.document_id == successor.document_id:
        raise GuardFailure("a document cannot supersede itself")
    document_type = scalar_text(old.metadata.get("type"))
    if scalar_text(successor.metadata.get("type")) != document_type:
        raise GuardFailure("successor must have the same document type")
    if is_terminal(document_type, scalar_text(successor.metadata.get("status"))):
        raise GuardFailure("successor must be non-terminal")
    old_status = scalar_text(old.metadata.get("status"))
    if old_status == "superseded":
        raise GuardFailure("old document is already superseded")
    if not is_terminal(document_type, old_status):
        return perform_transition(
            repo,
            config,
            old.path,
            "superseded",
            at=at,
            superseded_by=successor.document_id,
            dry_run=dry_run,
        )

    timestamp = choose_timestamp(at)
    print(f"Link successor: {old.document_id} <- {successor.document_id} (status remains {old_status})")
    if dry_run:
        return old.path
    for document in (old, successor):
        if tracked(repo, document.path) and staged(repo, document.path):
            raise GuardFailure(f"{document.relative_path} has staged changes")
    index_path, registry_path = generated_paths(repo, config)
    snapshot = capture([old.path, successor.path, index_path, registry_path])
    try:
        old.path.write_text(
            update_frontmatter(
                old.text,
                {
                    "superseded_by": sorted(set(list_value(old.metadata.get("superseded_by"))) | {successor.document_id}),
                    "updated_at": timestamp,
                },
            ),
            encoding="utf-8",
            newline="",
        )
        successor.path.write_text(
            update_frontmatter(
                successor.text,
                {
                    "supersedes": sorted(set(list_value(successor.metadata.get("supersedes"))) | {old.document_id}),
                    "updated_at": timestamp,
                },
            ),
            encoding="utf-8",
            newline="",
        )
        refresh_index(repo, config)
        _, final_issues = collect_issues(repo, config, base_ref=base_ref)
        errors = [issue for issue in final_issues if issue.severity == "ERROR"]
        if errors:
            raise GuardFailure("; ".join(issue.render() for issue in errors))
    except Exception:
        restore_files(snapshot)
        raise
    return old.path


def command_check(args: argparse.Namespace) -> int:
    repo = find_repo(Path(args.repo))
    config = load_config(repo, Path(args.config).resolve() if args.config else None)
    if not config["documentation"].get("enabled", True):
        print("Documentation lifecycle is disabled.")
        return 0
    scan, issues = collect_issues(repo, config, base_ref=args.base_ref)
    return print_report(scan, issues)


def command_index(args: argparse.Namespace) -> int:
    repo = find_repo(Path(args.repo))
    config = load_config(repo, Path(args.config).resolve() if args.config else None)
    changed = refresh_index(repo, config, check_only=args.check)
    if args.check and changed:
        print("ERROR [GENERATED_ARTIFACT]: index or registry is stale")
        return 1
    print("Index and registry are current." if not changed else "Index and registry refreshed.")
    return 0


def command_new(args: argparse.Namespace) -> int:
    repo = find_repo(Path(args.repo))
    config = load_config(repo, Path(args.config).resolve() if args.config else None)
    if not config["documentation"].get("enabled", True):
        raise GuardFailure("documentation lifecycle is disabled for this repository")
    destination = perform_new(
        repo,
        config,
        args.type,
        args.slug,
        title=args.title,
        status=args.status,
        at=args.at,
        owner=args.owner,
        generator=args.generator,
        dry_run=args.dry_run,
    )
    print(
        "Dry run complete; no files changed."
        if args.dry_run
        else f"Created: {destination.relative_to(repo).as_posix()}"
    )
    return 0


def command_transition(args: argparse.Namespace) -> int:
    source = Path(args.document).resolve()
    repo = find_repo(Path(args.repo).resolve() if args.repo else source)
    config = load_config(repo, Path(args.config).resolve() if args.config else None)
    destination = perform_transition(
        repo,
        config,
        source,
        args.status,
        at=args.at,
        superseded_by=args.superseded_by,
        dry_run=args.dry_run,
    )
    print(f"Transition complete: {destination.relative_to(repo).as_posix()}" if not args.dry_run else "Dry run complete; no files changed.")
    return 0


def command_link_successor(args: argparse.Namespace) -> int:
    old_path = Path(args.old_document).resolve()
    successor_path = Path(args.successor_document).resolve()
    repo = find_repo(Path(args.repo).resolve() if args.repo else old_path)
    config = load_config(repo, Path(args.config).resolve() if args.config else None)
    result = perform_link_successor(repo, config, old_path, successor_path, at=args.at, dry_run=args.dry_run)
    print(f"Successor relationship complete: {result.relative_to(repo).as_posix()}" if not args.dry_run else "Dry run complete; no files changed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="validate managed documentation")
    check.add_argument("repo", nargs="?", default=".")
    check.add_argument("--config")
    check.add_argument("--base-ref", help="compare immutable fields and transitions with a git ref")
    check.set_defaults(func=command_check)

    index = subparsers.add_parser("index", help="generate docs/INDEX.md and docs/.registry.json")
    index.add_argument("repo", nargs="?", default=".")
    index.add_argument("--config")
    index.add_argument("--check", action="store_true", help="fail instead of writing when generated files are stale")
    index.set_defaults(func=command_index)

    create = subparsers.add_parser("new", help="create a managed document with a collision-free id and canonical path")
    create.add_argument("type", choices=sorted(TYPE_RULES))
    create.add_argument("slug", help="immutable lowercase kebab-case slug")
    create.add_argument("--repo", default=".")
    create.add_argument("--config")
    create.add_argument("--title", help="human-readable title; defaults to the slug")
    create.add_argument("--status", help="initial live status; defaults to draft (plan/migration) or current (generated)")
    create.add_argument("--owner")
    create.add_argument("--generator", help="generated documents only; defaults to codex")
    create.add_argument("--at", help="ISO 8601 timestamp with timezone (primarily for deterministic automation)")
    create.add_argument("--dry-run", action="store_true")
    create.set_defaults(func=command_new)

    transition = subparsers.add_parser("transition", help="perform an atomic lifecycle status transition")
    transition.add_argument("document")
    transition.add_argument("status")
    transition.add_argument("--repo")
    transition.add_argument("--config")
    transition.add_argument("--at", help="ISO 8601 timestamp with timezone (primarily for deterministic automation)")
    transition.add_argument("--superseded-by", metavar="ID")
    transition.add_argument("--dry-run", action="store_true")
    transition.set_defaults(func=command_transition)

    successor = subparsers.add_parser("link-successor", help="link a successor without rewriting terminal history")
    successor.add_argument("old_document")
    successor.add_argument("successor_document")
    successor.add_argument("--repo")
    successor.add_argument("--config")
    successor.add_argument("--at")
    successor.add_argument("--dry-run", action="store_true")
    successor.set_defaults(func=command_link_successor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GuardFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
