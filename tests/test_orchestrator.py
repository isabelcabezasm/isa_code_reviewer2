from __future__ import annotations

from reviewers.config import ReviewConfig, ReviewSettings, CommentSettings, AgentConfig
from reviewers.orchestrator import apply_severity_thresholds
from reviewers.schemas import ReviewFinding, ReviewResult


def test_apply_severity_thresholds_filters_lower_priority_findings() -> None:
    config = ReviewConfig(
        review=ReviewSettings(),
        comment=CommentSettings(),
        agents={
            'security': AgentConfig(True, 'anthropic', 'claude', 'medium', []),
            'code_quality': AgentConfig(True, 'openai', 'gpt-4o', 'low', []),
            'test_coverage': AgentConfig(True, 'openai', 'gpt-4o-mini', 'high', []),
        },
    )
    results = [
        ReviewResult(
            agent='security',
            model='claude',
            findings=[
                ReviewFinding(agent='security', severity='critical', title='Critical', summary='x'),
                ReviewFinding(agent='security', severity='low', title='Low', summary='x'),
            ],
        )
    ]

    filtered = apply_severity_thresholds(results=results, config=config)

    assert [finding.severity for finding in filtered[0].findings] == ['critical']
