#!/usr/bin/env python3
"""Lint active V1 document authority, links, and legacy scope banners."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit


ACTIVE_FIXED = (
    "GOAL.md",
    "README.md",
    "NEXT_STAGES_IMPLEMENTATION_HANDOFF.md",
    "docs/architecture/V1_ARCHITECTURE.md",
    "docs/contracts/V1_ENVIRONMENT.md",
    "docs/training/PPO_AND_MODEL_PIPELINE.md",
    "docs/project/REQUIREMENTS.md",
    "docs/project/ROADMAP.md",
    "docs/project/VERIFICATION.md",
    "docs/project/LEGACY_P0_TRANSITION.md",
    "docs/project/M00_WORKTREE_PRESERVATION.md",
    "docs/project/G00_GATE_REPORT.md",
    "docs/project/M01_SOURCE_PREPARATION.md",
    "docs/project/M01_TOOLCHAIN_PROBE.md",
    "docs/project/M01_OPENTTD_BUILD_REPRODUCIBILITY.md",
    "docs/project/M01_BUILD_PROFILE_RESOURCE_PROVENANCE.md",
    "docs/project/G01_GATE_REPORT.md",
    "docs/project/M02_MAP_FEASIBILITY.md",
)
V1_ADR_NUMBERS = tuple(range(7, 14))
LEGACY_BANNER_FILES = (
    "OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md",
    "OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md",
    "00_P0_CODEX_HANDOFF_INDEX.md",
    "01_P0_EVIDENCE_GATE_AND_CONTRADICTION_REGISTER.md",
    "02_P0_PATCHES_0003_0007_IMPLEMENTATION_SPEC.md",
    "03_P0_COMMAND_AND_FIELD_MAPPING_CONTRACT.md",
    "docs/P0_SCOPE.md",
    "docs/scope/P0_SUPPORTED_SCOPE.md",
    "docs/scope/P0_FORBIDDEN_SCOPE.md",
)
REQUIRED_NAVIGATION_TARGETS = (
    "GOAL.md",
    "docs/project/REQUIREMENTS.md",
    "docs/project/requirements-v1.json",
    "docs/project/ROADMAP.md",
    "docs/architecture/V1_ARCHITECTURE.md",
    "docs/contracts/V1_ENVIRONMENT.md",
    "docs/training/PPO_AND_MODEL_PIPELINE.md",
    "docs/project/VERIFICATION.md",
    "docs/project/LEGACY_P0_TRANSITION.md",
    "NEXT_STAGES_IMPLEMENTATION_HANDOFF.md",
    "docs/project/M00_WORKTREE_PRESERVATION.md",
    "docs/project/G00_GATE_REPORT.md",
    "docs/project/M01_SOURCE_PREPARATION.md",
    "docs/project/M01_TOOLCHAIN_PROBE.md",
    "docs/project/M01_OPENTTD_BUILD_REPRODUCIBILITY.md",
    "docs/project/M01_BUILD_PROFILE_RESOURCE_PROVENANCE.md",
    "docs/project/G01_GATE_REPORT.md",
    "docs/project/M02_MAP_FEASIBILITY.md",
    "docs/decisions/",
)

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
ADR_NUMBER = re.compile(r"^(\d{4})-")
CONFLICT_PATTERNS = (
    re.compile(
        r"\b(?:version\s*1|v1)\b[^.\n]{0,100}\b(?:is|uses|targets|begins with|includes)\b"
        r"[^.\n]{0,100}\b(?:64\s*(?:by|x|×)\s*64|road[- ]freight|freight fixture|trucks? first)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:active|current)\s+(?:product\s+|project\s+)?target\s+(?:is|:)"
        r"[^.\n]{0,120}\b(?:clean[- ]room|road[- ]freight|freight port|cuda simulation)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:version\s*1|v1|active)\s+first\s+(?:environment|scenario|fixture)\s+(?:is|:)"
        r"[^.\n]{0,100}\b(?:64\s*(?:by|x|×)\s*64|road[- ]freight|truck)\b",
        re.IGNORECASE,
    ),
)


class DocLintError(ValueError):
    """An active-project documentation invariant was violated."""


@dataclass(frozen=True)
class DocLintSummary:
    active_docs: int
    local_links: int
    legacy_banners: int
    accepted_v1_adrs: int


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DocLintError(f"cannot read {path}: {exc}") from exc


def find_v1_adrs(root: pathlib.Path) -> list[pathlib.Path]:
    decision_root = root / "docs/decisions"
    by_number: dict[int, pathlib.Path] = {}
    for path in decision_root.glob("*.md"):
        match = ADR_NUMBER.match(path.name)
        if match is None:
            continue
        number = int(match.group(1))
        if number in V1_ADR_NUMBERS:
            if number in by_number:
                raise DocLintError(f"duplicate V1 ADR number {number:04d}")
            by_number[number] = path
    missing = sorted(set(V1_ADR_NUMBERS) - set(by_number))
    if missing:
        raise DocLintError(f"missing V1 ADRs: {[f'{number:04d}' for number in missing]}")
    return [by_number[number] for number in V1_ADR_NUMBERS]


def active_documents(root: pathlib.Path) -> list[pathlib.Path]:
    paths = [root / relative for relative in ACTIVE_FIXED]
    paths.extend(find_v1_adrs(root))
    for path in paths:
        if not path.is_file():
            raise DocLintError(f"missing active project document: {path.relative_to(root)}")
    return paths


def _link_destination(raw: str) -> str:
    destination = raw.strip()
    if destination.startswith("<") and ">" in destination:
        return destination[1:destination.index(">")]
    # Markdown permits a title after whitespace. Project-local paths do not contain
    # spaces, so only the first token is the destination for this repository.
    return destination.split(maxsplit=1)[0]


def check_local_links(root: pathlib.Path, documents: list[pathlib.Path]) -> int:
    root_resolved = root.resolve()
    count = 0
    for document in documents:
        for match in MARKDOWN_LINK.finditer(_read(document)):
            destination = _link_destination(match.group(1))
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc or destination.startswith("#"):
                continue
            if not parsed.path:
                continue
            decoded = unquote(parsed.path)
            if pathlib.PurePosixPath(decoded).is_absolute():
                raise DocLintError(
                    f"{document.relative_to(root)} uses absolute local link {destination!r}"
                )
            target = (document.parent / decoded).resolve()
            if not target.is_relative_to(root_resolved):
                raise DocLintError(
                    f"{document.relative_to(root)} link escapes repository: {destination!r}"
                )
            if not target.exists():
                raise DocLintError(
                    f"{document.relative_to(root)} has broken local link {destination!r}"
                )
            count += 1
    return count


def check_scope_conflicts(root: pathlib.Path, documents: list[pathlib.Path]) -> None:
    for document in documents:
        text = _read(document)
        for pattern in CONFLICT_PATTERNS:
            match = pattern.search(text)
            if match is not None:
                excerpt = " ".join(match.group(0).split())[:240]
                raise DocLintError(
                    f"{document.relative_to(root)} asserts conflicting active scope: {excerpt!r}"
                )


def check_legacy_banner(path: pathlib.Path, root: pathlib.Path) -> None:
    if not path.is_file():
        raise DocLintError(f"missing preserved legacy document: {path.relative_to(root)}")
    prefix = "\n".join(_read(path).splitlines()[:30])
    if not re.search(r"(?:Legacy|Superseded-target) .{0,20}notice", prefix, re.IGNORECASE):
        raise DocLintError(f"{path.relative_to(root)} lacks an early legacy/supersession notice")
    if "GOAL.md" not in prefix and "NEXT_STAGES_IMPLEMENTATION_HANDOFF.md" not in prefix:
        raise DocLintError(f"{path.relative_to(root)} legacy notice lacks active-authority navigation")


def check_authority_for_adr(path: pathlib.Path, root: pathlib.Path) -> None:
    first_lines = "\n".join(_read(path).splitlines()[:12])
    if not re.search(r"^- Status: Accepted\b", first_lines, re.MULTILINE | re.IGNORECASE):
        raise DocLintError(f"{path.relative_to(root)} is not accepted")


def check_authority(root: pathlib.Path, adrs: list[pathlib.Path]) -> None:
    goal = _read(root / "GOAL.md")
    if "Status: project authority" not in goal:
        raise DocLintError("GOAL.md does not declare project-authority status")
    if "32 by 32" not in goal or "passenger-bus" not in goal:
        raise DocLintError("GOAL.md does not state the V1 map/bus boundary")

    readme = _read(root / "README.md")
    for target in REQUIRED_NAVIGATION_TARGETS:
        if f"]({target})" not in readme:
            raise DocLintError(f"README.md navigation omits {target}")

    handoff = _read(root / "NEXT_STAGES_IMPLEMENTATION_HANDOFF.md")
    authority_order = (
        "1. `GOAL.md`",
        "2. `docs/project/REQUIREMENTS.md`",
        "3. `docs/project/ROADMAP.md`",
    )
    positions = [handoff.find(marker) for marker in authority_order]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise DocLintError("handoff does not preserve the canonical authority order")

    for path in adrs:
        check_authority_for_adr(path, root)


def validate(root: pathlib.Path) -> DocLintSummary:
    root = root.resolve()
    documents = active_documents(root)
    adrs = find_v1_adrs(root)
    check_authority(root, adrs)
    local_links = check_local_links(root, documents)
    check_scope_conflicts(root, documents)
    for relative in LEGACY_BANNER_FILES:
        check_legacy_banner(root / relative, root)
    return DocLintSummary(
        active_docs=len(documents),
        local_links=local_links,
        legacy_banners=len(LEGACY_BANNER_FILES),
        accepted_v1_adrs=len(adrs),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = validate(args.root)
    except (DocLintError, OSError) as exc:
        print(f"V1_DOCS=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_DOCS=PASS "
        f"active_docs={summary.active_docs} "
        f"local_links={summary.local_links} "
        f"legacy_banners={summary.legacy_banners} "
        f"accepted_v1_adrs={summary.accepted_v1_adrs}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
