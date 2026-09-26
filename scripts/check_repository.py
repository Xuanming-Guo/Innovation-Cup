"""Dependency-free repository contract checks used locally and in GitHub Actions."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
BEGIN_SPEC = "<!-- BEGIN EMBEDDED SPECIFICATION -->"
END_SPEC = "<!-- END EMBEDDED SPECIFICATION -->"

REQUIRED_PATHS = (
    "README.md",
    "AGENTS.md",
    ".github/CODEOWNERS",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/SECURITY.md",
    ".github/workflows/quality.yml",
    "docs/CHANGELOG_v2.md",
    "docs/coordination_engine_master_v2.docx",
    "docs/coordination_engine_master_v2.md",
    "docs/implementation_master_prompt_v2.md",
    "docs/development/github-workflow.md",
)

FORBIDDEN_ROOT_DOCS = (
    "CHANGELOG_v2.md",
    "coordination_engine_master_v2.docx",
    "coordination_engine_master_v2.md",
    "implementation_master_prompt_v2.md",
)

BRANCH_PATTERN = re.compile(
    r"^(feat|fix|docs|refactor|test|ci|security|chore|release|build|perf)/"
    r"[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)?$"
)
PR_TITLE_PATTERN = re.compile(
    r"^(feat|fix|docs|refactor|test|ci|build|perf|security|chore|revert)"
    r"(?:\([a-z0-9-]+\))?!?: [a-z0-9].+$"
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def normalise_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").rstrip() + "\n"


def check_required_paths(errors: list[str]) -> None:
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).exists():
            errors.append(f"missing required path: {relative}")

    for relative in FORBIDDEN_ROOT_DOCS:
        if (ROOT / relative).exists():
            errors.append(f"project document must live under docs/: {relative}")


def check_embedded_spec(errors: list[str]) -> None:
    specification = ROOT / "docs/coordination_engine_master_v2.md"
    implementation = ROOT / "docs/implementation_master_prompt_v2.md"
    if not specification.exists() or not implementation.exists():
        return

    spec_text = specification.read_text(encoding="utf-8")
    implementation_text = implementation.read_text(encoding="utf-8")

    if implementation_text.count(BEGIN_SPEC) != 1 or implementation_text.count(END_SPEC) != 1:
        errors.append("implementation prompt must contain exactly one embedded-specification marker pair")
        return

    embedded = implementation_text.split(BEGIN_SPEC, 1)[1].split(END_SPEC, 1)[0]
    if normalise_newlines(embedded.strip()) != normalise_newlines(spec_text):
        errors.append(
            "embedded Part B differs from docs/coordination_engine_master_v2.md; "
            "update both authoritative copies together"
        )


def check_markdown_links(errors: list[str]) -> None:
    ignored_prefixes = ("http://", "https://", "mailto:", "#", "app://")
    excluded_directories = {".git", ".venv", "dist", "node_modules", "simulation", "target"}
    for directory, child_directories, filenames in os.walk(ROOT):
        child_directories[:] = [
            name for name in child_directories if name not in excluded_directories
        ]
        for filename in filenames:
            if not filename.lower().endswith(".md"):
                continue
            markdown = Path(directory, filename)
            text = markdown.read_text(encoding="utf-8")
            for raw_target in MARKDOWN_LINK.findall(text):
                target = raw_target.strip().strip("<>")
                if not target or target.startswith(ignored_prefixes):
                    continue
                target = unquote(target.split("#", 1)[0])
                if not target:
                    continue
                resolved = (markdown.parent / target).resolve()
                try:
                    resolved.relative_to(ROOT)
                except ValueError:
                    errors.append(
                        f"{markdown.relative_to(ROOT)}: link escapes repository: {raw_target}"
                    )
                    continue
                if not resolved.exists():
                    errors.append(
                        f"{markdown.relative_to(ROOT)}: broken relative link: {raw_target}"
                    )


def check_branch_and_pr_title(errors: list[str]) -> None:
    branch = os.environ.get("BRANCH_NAME", "").strip()
    if branch and branch != "main" and not BRANCH_PATTERN.fullmatch(branch):
        errors.append(f"branch name does not follow repository convention: {branch}")

    title = os.environ.get("PR_TITLE", "").strip()
    if title and not PR_TITLE_PATTERN.fullmatch(title):
        errors.append(f"pull-request title is not a Conventional Commit subject: {title}")


def main() -> int:
    errors: list[str] = []
    check_required_paths(errors)
    check_embedded_spec(errors)
    check_markdown_links(errors)
    check_branch_and_pr_title(errors)

    if errors:
        print("Repository contract checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Repository contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
