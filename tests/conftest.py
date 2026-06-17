from __future__ import annotations

import sys
from pathlib import Path

import pytest

from reviewers.schemas import ChangedFile, PullRequestRef, ReviewContext

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def fixture_dir() -> Path:
    return PROJECT_ROOT / 'tests' / 'fixtures'


@pytest.fixture
def sample_review_context() -> ReviewContext:
    return ReviewContext(
        pr=PullRequestRef(
            owner='octo',
            repo='code-reviewer',
            number=42,
            head_sha='abcdef1234567890',
            base_sha='1234567890abcdef',
        ),
        title='Add orchestrated PR reviews',
        body='Introduces reviewer infrastructure for GitHub Actions.',
        base_branch='main',
        head_branch='feature/pr-review',
        files=[
            ChangedFile(
                path='reviewers/orchestrator.py',
                status='modified',
                patch='@@ -1 +1,2 @@\n-print("old")\n+print("new")\n+print("again")',
                additions=2,
                deletions=1,
            )
        ],
    )
