"""Current-rule context for isolated production model calls.

The production contract and the Shorts editing profile live in the repository,
but every production model call is isolated: it sees only the stage's system
prompt and the user text that stage builds. A supervisor reading the contract
does not inject it into those calls, so Producer Brain planned, and packaging
reviewed, without the current rules in front of them.

This module renders a short, deterministic context block from canonical
sources, so a stage can carry the current rules into its request and record
exactly which revision of them it used. It holds no rules of its own: each
block is quoted verbatim from a canonical file and labelled with that file and
the digest of the text it came from. Editing a source rule changes the context
hash, and that is what invalidates a cached Producer plan. Sources are read on
every call, never at import time, so an edit landing mid-run is picked up by
the next call instead of being frozen for the process.

The context is guidance, not evidence. Case facts still come from the Producer
material and the word-timed transcript.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# The project root this module reads from. Resolved from the installed package
# location, not the process working directory.
ROOT = Path(__file__).resolve().parents[2]
MAX_CONTEXT_CHARS = 32000

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


class MissingStageSourceError(RuntimeError):
    """A required current-rule source is missing, or no longer holds its section.

    Raised before the model call it was needed for: a stage that cannot show
    the model the current rules must not silently call it anyway.
    """


@dataclass(frozen=True)
class RuleSource:
    """One labelled excerpt of a canonical source, and the stages that need it."""

    key: str
    path: str          # project-root-relative POSIX path
    heading: str       # exact heading text, without the leading #'s
    label: str         # how the block is introduced to the model
    kind: str          # "canonical contract" | "learned profile"
    stop_level: int    # the section ends at the first heading at or above this level
    stages: tuple[str, ...]   # backend call labels this excerpt applies to


# The smallest set that covers the currently isolated planning and packaging
# judgements. Sections 3 and 4 of the contract are the story and packaging
# rules; the profile's evidence table is the learned Shorts preference ledger.
# Whole documents are deliberately not shipped: cost stays bounded and an
# unrelated section cannot be mistaken for instructions.
CONTEXT_SOURCES: tuple[RuleSource, ...] = (
    RuleSource(
        key="contract.editorial",
        path="docs/SOL-PRODUCTION-CONTRACT.md",
        heading="3. Editorial execution",
        label="Sol production and delivery contract — 3. Editorial execution",
        kind="canonical contract",
        stop_level=2,
        stages=("producer_brain_v1", "package_post"),
    ),
    RuleSource(
        key="contract.packaging",
        path="docs/SOL-PRODUCTION-CONTRACT.md",
        heading="4. Presentation and packaging",
        label="Sol production and delivery contract — 4. Presentation and packaging",
        kind="canonical contract",
        stop_level=2,
        stages=("producer_brain_v1", "package_post", "thumbnail_copy_review"),
    ),
    RuleSource(
        key="profile.shorts_editing",
        path="docs/SHORTS-EDITING-PROFILE.md",
        heading="Shorts editing profile",
        label="Shorts editing profile — learned preferences and the evidence for each",
        kind="learned profile",
        stop_level=2,
        stages=("producer_brain_v1", "package_post"),
    ),
)

_HEADER = (
    "=== CURRENT PROJECT RULES "
    "(canonical project sources; guidance, not case evidence) ===\n"
    "Apply these rules to the work below. Each block is quoted verbatim from the\n"
    "project source named under it and is current as of this call. They are not\n"
    "facts about the case; the case material supplied with this task is the\n"
    "evidence."
)

_FOOTER = "=== END CURRENT PROJECT RULES ==="


@dataclass(frozen=True)
class ContextBlock:
    source: RuleSource
    file_sha256: str      # digest of the whole source file as read
    section_sha256: str   # digest of the extracted excerpt
    text: str             # the excerpt, verbatim


@dataclass(frozen=True)
class StageContext:
    """One rendered context, its digest, and the provenance behind both."""

    blocks: tuple[ContextBlock, ...]
    text: str
    sha256: str

    def applies_to(self, label: str) -> bool:
        return any(label in block.source.stages for block in self.blocks)

    def blocks_for(self, label: str) -> str:
        """The rendered context for one stage; empty when the stage needs none."""
        selected = [block for block in self.blocks if label in block.source.stages]
        return _render(selected) if selected else ""

    def request_text(self, user_text: str, label: str) -> str:
        """The user text with this stage's context ahead of it, or unchanged."""
        block = self.blocks_for(label)
        return f"{block}\n\n{user_text}" if block else user_text

    def provenance(self, label: str | None = None) -> dict[str, Any]:
        """What a model-call event records: the context hash and source hashes."""
        return {
            "sha256": _sha(self.blocks_for(label)) if label else self.sha256,
            "sources": [
                {
                    "key": block.source.key,
                    "path": block.source.path,
                    "sha256": block.file_sha256,
                    "section_sha256": block.section_sha256,
                }
                for block in self.blocks if label is None or label in block.source.stages
            ],
        }

    def cache_signature(self, label: str | None = None) -> dict[str, Any]:
        """The value a cache compares: a changed rule or changed source is a miss.

        Whole-file digests are included on purpose when no label is given. A
        cached Producer plan is only reused against the exact revision of the
        rules it was planned under, so an edit anywhere in a required source
        re-plans rather than silently reusing older reasoning.

        With a stage label, the signature covers only what that stage is shown:
        the extracted sections of its own sources, not the whole files. An edit
        outside those sections — another part of the same document, or a source
        this stage never sees — cannot invalidate the stage's cached result,
        while a change inside a consumed section still does.
        """
        if label is None:
            return {
                "context_sha256": self.sha256,
                "sources": {block.source.key: block.file_sha256 for block in self.blocks},
            }
        blocks = [block for block in self.blocks if label in block.source.stages]
        return {
            "context_sha256": _sha(_render(blocks)),
            "sources": {block.source.key: block.section_sha256 for block in blocks},
        }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_section(text: str, heading: str, stop_level: int) -> str | None:
    """The verbatim lines of one markdown section, or None when it is absent.

    The section runs from its own heading to the next heading at or above
    `stop_level`, which is how the profile's table stops at its first `##`
    while a contract section stops at the next section.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        match = _HEADING.match(line.strip())
        if match and match.group(2).strip() == heading:
            start = index
            break
    if start is None:
        return None
    body = [lines[start]]
    for line in lines[start + 1:]:
        match = _HEADING.match(line.strip())
        if match and len(match.group(1)) <= stop_level:
            break
        body.append(line)
    section = "\n".join(body).strip()
    return section or None


def _render(blocks: Sequence[ContextBlock]) -> str:
    if not blocks:
        return ""
    parts = [_HEADER]
    for number, block in enumerate(blocks, start=1):
        parts.append(f"[{number}] {block.source.label} ({block.source.kind})")
        parts.append(f"source: {block.source.path}")
        parts.append(block.text)
        parts.append("")
    parts.append(_FOOTER)
    return "\n".join(parts).strip()


def load_context(
    root: Path | str | None = None,
    sources: Sequence[RuleSource] = CONTEXT_SOURCES,
) -> StageContext:
    """Read the required sources now and render the current context.

    Missing files and missing sections are collected and raised together, all
    before any model call, so an incomplete rule handoff is a loud failure
    rather than a quietly thinner prompt.
    """
    base = Path(root) if root is not None else ROOT
    blocks: list[ContextBlock] = []
    problems: list[str] = []
    for source in sources:
        path = base / source.path
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
        except OSError as exc:
            problems.append(f"{source.path}: cannot read ({exc.strerror or exc})")
            continue
        section = _extract_section(text, source.heading, source.stop_level)
        if section is None:
            problems.append(f"{source.path}: no section headed {source.heading!r}")
            continue
        blocks.append(
            ContextBlock(
                source=source,
                file_sha256=hashlib.sha256(raw).hexdigest(),
                section_sha256=_sha(section),
                text=section,
            )
        )
    if problems:
        raise MissingStageSourceError(
            "current-rule context unavailable: " + "; ".join(problems)
        )
    rendered = _render(blocks)
    if len(rendered) > MAX_CONTEXT_CHARS:
        raise MissingStageSourceError("current-rule context exceeds bounded request budget; refine canonical sections before calling a model")
    return StageContext(blocks=tuple(blocks), text=rendered, sha256=_sha(rendered))
