from __future__ import annotations

from reviewers.comment_renderer import render_review_comment
from reviewers.schemas import ReviewFinding, ReviewResult, ReviewResultBundle


def test_render_review_comment_groups_findings(sample_review_context) -> None:
    bundle = ReviewResultBundle(
        context=sample_review_context,
        results=[
            ReviewResult(
                agent='security',
                model='claude-3-7-sonnet-latest',
                summary='Found one security issue.',
                findings=[
                    ReviewFinding(
                        agent='security',
                        severity='high',
                        title='Unsanitized shell input',
                        summary='User input reaches shell execution without validation.',
                        file_path='reviewers/github_client.py',
                        line_start=88,
                        line_end=92,
                        recommendation='Avoid shell execution or validate the input.',
                    )
                ],
            ),
            ReviewResult(agent='code_quality', model='gpt-4o', summary='No notable issues.'),
        ],
        agent_errors={'test_coverage': 'provider API key is missing'},
    )

    rendered = render_review_comment(bundle, collapse_sections=False)

    assert '<!-- code-reviewer:pr-review -->' in rendered
    assert '## Security Review — claude-3-7-sonnet-latest' in rendered
    assert '### High' in rendered
    assert '`reviewers/github_client.py:88-92`' in rendered
    assert '## Agent Errors' in rendered
    assert 'provider API key is missing' in rendered
