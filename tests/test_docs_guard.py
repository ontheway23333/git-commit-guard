from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "docs_guard.py"
ASSETS = Path(__file__).resolve().parents[1] / "assets"
SPEC = importlib.util.spec_from_file_location("docs_guard", SCRIPT)
assert SPEC and SPEC.loader
docs_guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = docs_guard
SPEC.loader.exec_module(docs_guard)


PLAN_SECTIONS = """## Context

## Problem

## Goals

## Non-goals

## Current State

## Proposed Design

## Implementation Plan

## Validation

## Risks

## Rollback

## Progress

## Decisions
"""


def plan_text(
    document_id: str,
    slug: str,
    status: str,
    created_at: str,
    updated_at: str | None = None,
    *,
    archived_at: str | None = None,
    supersedes: list[str] | None = None,
    superseded_by: list[str] | None = None,
) -> str:
    updated_at = updated_at or created_at
    lines = [
        "---",
        "schema_version: 1",
        f"id: {document_id}",
        f"slug: {slug}",
        f"title: {slug.replace('-', ' ').title()}",
        "type: plan",
        f"status: {status}",
        f"created_at: {created_at}",
        f"updated_at: {updated_at}",
        f"status_changed_at: {updated_at}",
        f"supersedes: {supersedes or []}",
        f"superseded_by: {superseded_by or []}",
    ]
    if archived_at:
        lines.append(f"archived_at: {archived_at}")
    lines.extend(["---", "", f"# {slug.replace('-', ' ').title()}", "", PLAN_SECTIONS])
    return "\n".join(lines)


class DocsGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.repo = docs_guard.find_repo(self.repo)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "guard@example.test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Guard Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "core.autocrlf", "false"], check=True)
        self.config = docs_guard.load_config(self.repo)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, relative: str, content: str) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        return path

    def index(self) -> None:
        docs_guard.refresh_index(self.repo, self.config)

    def commit_all(self, message: str = "baseline") -> None:
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m", message], check=True)

    def test_legacy_markdown_is_exempt(self) -> None:
        self.write("docs/old-plan.md", "# Legacy\n")
        scan, issues = docs_guard.collect_issues(self.repo, self.config)
        self.assertEqual(scan.legacy_count, 1)
        self.assertFalse([issue for issue in issues if issue.severity == "ERROR"])

    def test_duplicate_id_and_path_projection_are_errors(self) -> None:
        stamp = "2026-08-14T10:00:00+08:00"
        content = plan_text("PLAN-20260814-001", "payment-refactor", "active", stamp)
        self.write("docs/plan/2026-08-14-active-payment-refactor.md", content)
        self.write("docs/plan/wrong-name.md", content)
        scan, issues = docs_guard.collect_issues(self.repo, self.config, check_generated=False)
        codes = {issue.code for issue in issues if issue.severity == "ERROR"}
        self.assertIn("DUPLICATE_ID", codes)
        self.assertIn("PATH_PROJECTION", codes)
        self.assertEqual(len(scan.documents), 2)

    def test_transition_uses_git_mv_repairs_links_and_refreshes_registry(self) -> None:
        created = "2026-08-14T10:00:00+08:00"
        source = self.write(
            "docs/plan/2026-08-14-review-payment-refactor.md",
            plan_text("PLAN-20260814-001", "payment-refactor", "review", created)
            + "\n[Reference](../reference.md)\n",
        )
        self.write("docs/reference.md", "# Reference\n")
        self.write("README.md", "[Plan](docs/plan/2026-08-14-review-payment-refactor.md)\n")
        self.index()
        self.commit_all()

        destination = docs_guard.perform_transition(
            self.repo,
            self.config,
            source,
            "completed",
            at="2026-08-30T15:42:17+08:00",
        )

        self.assertEqual(
            destination.relative_to(self.repo).as_posix(),
            "docs/archive/plan/2026/2026-08-14-completed-payment-refactor.md",
        )
        self.assertFalse(source.exists())
        self.assertIn("docs/archive/plan/2026/2026-08-14-completed-payment-refactor.md", (self.repo / "README.md").read_text(encoding="utf-8"))
        transitioned = destination.read_text(encoding="utf-8")
        self.assertIn("status: completed", transitioned)
        self.assertIn("archived_at: 2026-08-30T15:42:17+08:00", transitioned)
        self.assertIn("[Reference](../../../reference.md)", transitioned)
        registry = (self.repo / "docs/.registry.json").read_text(encoding="utf-8")
        self.assertIn(destination.relative_to(self.repo).as_posix(), registry)
        status = subprocess.run(
            ["git", "-C", str(self.repo), "status", "--short"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertRegex(status, r"(?m)^R[ M]")

    def test_manual_illegal_transition_is_detected_against_git(self) -> None:
        source = self.write(
            "docs/plan/2026-08-14-draft-payment-refactor.md",
            plan_text("PLAN-20260814-001", "payment-refactor", "draft", "2026-08-14T10:00:00+08:00"),
        )
        self.index()
        self.commit_all()
        completed = self.repo / "docs/archive/plan/2026/2026-08-14-completed-payment-refactor.md"
        completed.parent.mkdir(parents=True, exist_ok=True)
        completed.write_text(
            plan_text(
                "PLAN-20260814-001",
                "payment-refactor",
                "completed",
                "2026-08-14T10:00:00+08:00",
                "2026-08-30T15:42:17+08:00",
                archived_at="2026-08-30T15:42:17+08:00",
            ),
            encoding="utf-8",
        )
        source.unlink()
        _, issues = docs_guard.collect_issues(self.repo, self.config, base_ref="HEAD", check_generated=False)
        self.assertIn("INVALID_TRANSITION", {issue.code for issue in issues})

    def test_full_flow_without_pyyaml_uses_the_stdlib_subset_parser(self) -> None:
        original = docs_guard.yaml
        docs_guard.yaml = None
        try:
            config = docs_guard.load_config(self.repo)
            created = docs_guard.perform_new(
                self.repo, config, "plan", "payment-refactor", at="2026-08-15T10:00:00+08:00"
            )
            self.commit_all()
            destination = docs_guard.perform_transition(
                self.repo, config, created, "active", at="2026-08-16T09:00:00+08:00"
            )
            _, issues = docs_guard.collect_issues(self.repo, config, base_ref="HEAD")
        finally:
            docs_guard.yaml = original
        self.assertIn("status: active", destination.read_text(encoding="utf-8"))
        self.assertFalse([issue for issue in issues if issue.severity == "ERROR"])

    def test_yaml_subset_supports_default_config_shape(self) -> None:
        parsed = docs_guard.parse_yaml_subset(
            "version: 1\ndocumentation:\n  enabled: true\n  directories:\n    plan: plan\n  values:\n    - one\n    - two\n"
        )
        self.assertEqual(parsed["documentation"]["directories"]["plan"], "plan")
        self.assertEqual(parsed["documentation"]["values"], ["one", "two"])

    def test_cli_index_and_history_check(self) -> None:
        self.write(
            "docs/plan/2026-08-14-active-payment-refactor.md",
            plan_text("PLAN-20260814-001", "payment-refactor", "active", "2026-08-14T10:00:00+08:00"),
        )
        index_result = subprocess.run(
            [sys.executable, str(SCRIPT), "index", str(self.repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(index_result.returncode, 0, index_result.stderr)
        self.commit_all()
        check_result = subprocess.run(
            [sys.executable, str(SCRIPT), "check", str(self.repo), "--base-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(check_result.returncode, 0, check_result.stdout + check_result.stderr)
        self.assertIn("0 errors", check_result.stdout)

    @unittest.skipIf(docs_guard.yaml is None, "PyYAML is not installed")
    def test_ci_and_pre_commit_assets_are_valid_yaml(self) -> None:
        workflow = docs_guard.yaml.safe_load((ASSETS / "github-actions-docs-guard.yml").read_text(encoding="utf-8"))
        pre_commit = docs_guard.yaml.safe_load((ASSETS / "pre-commit-config.fragment.yml").read_text(encoding="utf-8"))
        self.assertIn("jobs", workflow)
        self.assertEqual(workflow["permissions"]["contents"], "read")
        self.assertEqual(pre_commit["repos"][0]["repo"], "local")

    def test_terminal_document_cannot_be_reactivated(self) -> None:
        created = "2026-08-14T10:00:00+08:00"
        completed = self.write(
            "docs/archive/plan/2026/2026-08-14-completed-payment-refactor.md",
            plan_text(
                "PLAN-20260814-001",
                "payment-refactor",
                "completed",
                created,
                "2026-08-30T15:42:17+08:00",
                archived_at="2026-08-30T15:42:17+08:00",
            ),
        )
        self.index()
        self.commit_all()
        with self.assertRaises(docs_guard.GuardFailure):
            docs_guard.perform_transition(self.repo, self.config, completed, "active")

    def test_link_successor_preserves_completed_status(self) -> None:
        created = "2026-08-14T10:00:00+08:00"
        old = self.write(
            "docs/archive/plan/2026/2026-08-14-completed-payment-refactor.md",
            plan_text(
                "PLAN-20260814-001",
                "payment-refactor",
                "completed",
                created,
                "2026-08-30T15:42:17+08:00",
                archived_at="2026-08-30T15:42:17+08:00",
            ),
        )
        new = self.write(
            "docs/plan/2026-09-20-draft-payment-refactor-v2.md",
            plan_text("PLAN-20260920-001", "payment-refactor-v2", "draft", "2026-09-20T09:00:00+08:00"),
        )
        self.index()
        self.commit_all()

        docs_guard.perform_link_successor(
            self.repo,
            self.config,
            old,
            new,
            at="2026-09-20T10:00:00+08:00",
        )

        old_text = old.read_text(encoding="utf-8")
        new_text = new.read_text(encoding="utf-8")
        self.assertIn("status: completed", old_text)
        self.assertIn('superseded_by: ["PLAN-20260920-001"]', old_text)
        self.assertIn('supersedes: ["PLAN-20260814-001"]', new_text)

    def test_new_allocates_sequential_ids_and_canonical_paths(self) -> None:
        first = docs_guard.perform_new(
            self.repo, self.config, "plan", "payment-refactor", at="2026-08-15T10:00:00+08:00"
        )
        second = docs_guard.perform_new(
            self.repo, self.config, "plan", "invoice-cleanup", at="2026-08-15T11:00:00+08:00"
        )
        generated = docs_guard.perform_new(
            self.repo, self.config, "generated", "api-audit", at="2026-08-15T12:00:00+08:00"
        )

        self.assertEqual(first.relative_to(self.repo).as_posix(), "docs/plan/2026-08-15-draft-payment-refactor.md")
        self.assertEqual(second.relative_to(self.repo).as_posix(), "docs/plan/2026-08-15-draft-invoice-cleanup.md")
        self.assertEqual(
            generated.relative_to(self.repo).as_posix(),
            "docs/generated/2026-08-15-current-api-audit.md",
        )
        self.assertIn("id: PLAN-20260815-001", first.read_text(encoding="utf-8"))
        self.assertIn("id: PLAN-20260815-002", second.read_text(encoding="utf-8"))
        self.assertIn("generated: true", generated.read_text(encoding="utf-8"))

        _, issues = docs_guard.collect_issues(self.repo, self.config)
        self.assertFalse([issue for issue in issues if issue.severity == "ERROR"])
        self.assertFalse([issue for issue in issues if issue.code == "MISSING_SECTION"])

    def test_new_rejects_duplicate_slug_and_terminal_status(self) -> None:
        docs_guard.perform_new(self.repo, self.config, "plan", "payment-refactor", at="2026-08-15T10:00:00+08:00")
        with self.assertRaises(docs_guard.GuardFailure):
            docs_guard.perform_new(self.repo, self.config, "plan", "payment-refactor", at="2026-08-15T11:00:00+08:00")
        with self.assertRaises(docs_guard.GuardFailure):
            docs_guard.perform_new(
                self.repo, self.config, "plan", "other-plan", status="completed", at="2026-08-15T11:00:00+08:00"
            )
        with self.assertRaises(docs_guard.GuardFailure):
            docs_guard.perform_new(self.repo, self.config, "plan", "Not_A_Slug", at="2026-08-15T11:00:00+08:00")

    def test_new_dry_run_writes_nothing(self) -> None:
        destination = docs_guard.perform_new(
            self.repo, self.config, "plan", "payment-refactor", at="2026-08-15T10:00:00+08:00", dry_run=True
        )
        self.assertFalse(destination.exists())
        self.assertFalse((self.repo / "docs/.registry.json").exists())

    def test_new_document_survives_a_full_lifecycle(self) -> None:
        created = docs_guard.perform_new(
            self.repo, self.config, "plan", "payment-refactor", at="2026-08-15T10:00:00+08:00"
        )
        self.commit_all()
        # Each transition stages its own `git mv`, so a milestone commit separates them.
        active = docs_guard.perform_transition(
            self.repo, self.config, created, "active", at="2026-08-16T09:00:00+08:00"
        )
        self.commit_all("draft -> active")
        review = docs_guard.perform_transition(
            self.repo, self.config, active, "review", at="2026-08-17T09:00:00+08:00"
        )
        self.commit_all("active -> review")
        completed = docs_guard.perform_transition(
            self.repo, self.config, review, "completed", at="2026-08-18T09:00:00+08:00"
        )
        self.assertEqual(
            completed.relative_to(self.repo).as_posix(),
            "docs/archive/plan/2026/2026-08-15-completed-payment-refactor.md",
        )
        _, issues = docs_guard.collect_issues(self.repo, self.config, base_ref="HEAD")
        self.assertFalse([issue for issue in issues if issue.severity == "ERROR"])

    def test_transition_works_before_the_first_commit(self) -> None:
        created = docs_guard.perform_new(
            self.repo, self.config, "plan", "payment-refactor", at="2026-08-15T10:00:00+08:00"
        )
        destination = docs_guard.perform_transition(
            self.repo, self.config, created, "active", at="2026-08-16T09:00:00+08:00"
        )
        self.assertTrue(destination.exists())
        self.assertIn("status: active", destination.read_text(encoding="utf-8"))

    def test_broken_link_into_docs_is_an_error(self) -> None:
        self.write(
            "docs/plan/2026-08-14-active-payment-refactor.md",
            plan_text("PLAN-20260814-001", "payment-refactor", "active", "2026-08-14T10:00:00+08:00")
            + "\n[Missing](./does-not-exist.md)\n",
        )
        _, issues = docs_guard.collect_issues(self.repo, self.config, check_generated=False)
        self.assertIn("BROKEN_LINK", {issue.code for issue in issues if issue.severity == "ERROR"})

    def test_history_detects_immutable_created_at_change(self) -> None:
        source = self.write(
            "docs/plan/2026-08-14-active-payment-refactor.md",
            plan_text("PLAN-20260814-001", "payment-refactor", "active", "2026-08-14T10:00:00+08:00"),
        )
        self.index()
        self.commit_all()
        source.write_text(
            source.read_text(encoding="utf-8").replace(
                "created_at: 2026-08-14T10:00:00+08:00",
                "created_at: 2026-08-15T10:00:00+08:00",
            ),
            encoding="utf-8",
        )
        _, issues = docs_guard.collect_issues(self.repo, self.config, base_ref="HEAD", check_generated=False)
        self.assertIn("IMMUTABLE_FIELD", {issue.code for issue in issues})


if __name__ == "__main__":
    unittest.main()
