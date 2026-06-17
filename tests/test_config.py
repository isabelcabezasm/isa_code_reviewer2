from __future__ import annotations

from pathlib import Path

import pytest

from reviewers.config import load_config


def test_load_config_reads_fixture_defaults(fixture_dir: Path) -> None:
    config = load_config(str(fixture_dir / 'code-review-config.yml'))

    assert config.review.draft_prs is True
    assert config.review.max_files == 25
    assert config.comment.collapse_sections is False
    assert config.agents['security'].provider == 'anthropic'
    assert config.agents['code_quality'].severity_threshold == 'medium'
    assert config.agents['test_coverage'].enabled is False


def test_load_config_uses_default_config_when_file_missing() -> None:
    config = load_config('/workspaces/code_reviewer/tests/fixtures/does-not-exist.yml')

    assert config.agents['security'].enabled is True
    assert config.agents['code_quality'].model == 'gpt-4o'
    assert config.agents['test_coverage'].severity_threshold == 'medium'


def test_load_config_rejects_enabled_agents_missing_provider() -> None:
    broken_path = Path('/workspaces/code_reviewer/tests/fixtures/broken-config.yml')
    broken_path.write_text(
        'version: 1\nagents:\n  security:\n    enabled: true\n    model: claude\n',
        encoding='utf-8',
    )
    try:
        with pytest.raises(ValueError, match='missing required field'):
            load_config(str(broken_path))
    finally:
        broken_path.unlink(missing_ok=True)
