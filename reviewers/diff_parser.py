from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

HUNK_HEADER_RE = re.compile(
    r'^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@'
)


@dataclass(frozen=True)
class DiffLine:
    kind: Literal['context', 'add', 'delete']
    content: str
    old_line: int | None
    new_line: int | None


@dataclass(frozen=True)
class DiffHunk:
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[DiffLine, ...]


def parse_unified_diff(patch: str | None) -> tuple[DiffHunk, ...]:
    if not patch:
        return ()

    hunks: list[DiffHunk] = []
    current_header: str | None = None
    current_lines: list[DiffLine] = []
    old_line = new_line = 0
    old_count = new_count = 0
    old_start = new_start = 0

    for raw_line in patch.splitlines():
        match = HUNK_HEADER_RE.match(raw_line)
        if match:
            if current_header is not None:
                hunks.append(
                    DiffHunk(
                        header=current_header,
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        lines=tuple(current_lines),
                    )
                )
            current_header = raw_line
            old_start = int(match.group('old_start'))
            new_start = int(match.group('new_start'))
            old_count = int(match.group('old_count') or '1')
            new_count = int(match.group('new_count') or '1')
            old_line = old_start
            new_line = new_start
            current_lines = []
            continue

        if current_header is None:
            continue

        prefix = raw_line[:1]
        content = raw_line[1:] if raw_line else ''
        if prefix == '+':
            current_lines.append(DiffLine(kind='add', content=content, old_line=None, new_line=new_line))
            new_line += 1
        elif prefix == '-':
            current_lines.append(DiffLine(kind='delete', content=content, old_line=old_line, new_line=None))
            old_line += 1
        else:
            current_lines.append(DiffLine(kind='context', content=raw_line[1:] if prefix == ' ' else raw_line, old_line=old_line, new_line=new_line))
            old_line += 1
            new_line += 1

    if current_header is not None:
        hunks.append(
            DiffHunk(
                header=current_header,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=tuple(current_lines),
            )
        )

    return tuple(hunks)


def truncate_patch(patch: str | None, max_chars: int) -> str | None:
    if patch is None or len(patch) <= max_chars:
        return patch

    suffix = '\n... [patch truncated]'
    allowed = max_chars - len(suffix)
    if allowed <= 0:
        return suffix.strip()

    truncated = patch[:allowed]
    if '\n' in truncated:
        truncated = truncated.rsplit('\n', 1)[0]
    return f'{truncated}{suffix}'


def normalize_patch(patch: str | None, max_chars: int) -> str | None:
    if patch is None:
        return None
    parse_unified_diff(patch)
    return truncate_patch(patch, max_chars)
