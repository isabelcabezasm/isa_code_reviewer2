from __future__ import annotations

from reviewers.diff_parser import normalize_patch, parse_unified_diff


def test_parse_unified_diff_returns_hunks() -> None:
    patch = '@@ -1,2 +1,3 @@\n line one\n-line two\n+line three\n+line four'

    hunks = parse_unified_diff(patch)

    assert len(hunks) == 1
    assert hunks[0].old_start == 1
    assert hunks[0].new_count == 3
    assert hunks[0].lines[1].kind == 'delete'
    assert hunks[0].lines[2].kind == 'add'


def test_normalize_patch_truncates_large_patches() -> None:
    patch = '@@ -1 +1 @@\n' + ('+x\n' * 20)

    normalized = normalize_patch(patch, max_chars=40)

    assert normalized is not None
    assert normalized.endswith('... [patch truncated]')
