from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from reviewers.github_client import STICKY_COMMENT_MARKER
from reviewers.schemas import AGENT_DISPLAY_NAMES, AGENT_ORDER, ReviewFinding, ReviewResult, ReviewResultBundle, SEVERITY_ORDER


def render_review_comment(bundle: ReviewResultBundle, *, collapse_sections: bool = True) -> str:
    lines = [STICKY_COMMENT_MARKER, '# Automated PR Review', '']

    if bundle.skipped_reason:
        lines.extend(['## Review Status', '', f'- Skipped: {bundle.skipped_reason}'])
        return '\n'.join(lines).strip() + '\n'

    context = bundle.context
    lines.extend(
        [
            f'**PR:** #{context.pr.number}  ',
            f'**Commit:** `{context.pr.head_sha[:7]}`  ',
            f'**Agents run:** {", ".join(AGENT_DISPLAY_NAMES[result.agent] for result in bundle.results) or "None"}',
            '',
            '## Summary',
            '',
        ]
    )

    counts = Counter(finding.severity for result in bundle.results for finding in result.findings)
    if counts:
        for severity in SEVERITY_ORDER:
            lines.append(f'- {severity.title()}: {counts.get(severity, 0)}')
    else:
        lines.append('- No findings above threshold.')

    for result in bundle.results:
        lines.extend(['', *_render_agent_section(result, collapse_sections=collapse_sections)])

    lines.extend(['', '## Agent Errors', ''])
    if bundle.agent_errors:
        for agent_name in AGENT_ORDER:
            if agent_name in bundle.agent_errors:
                lines.append(f'- **{AGENT_DISPLAY_NAMES[agent_name]}:** {bundle.agent_errors[agent_name]}')
    else:
        lines.append('- None')

    return '\n'.join(lines).strip() + '\n'


def _render_agent_section(result: ReviewResult, *, collapse_sections: bool) -> list[str]:
    header = f'## {AGENT_DISPLAY_NAMES[result.agent]} Review — {result.model}'
    body_lines: list[str] = []
    if result.error:
        body_lines.append(f'_Agent failed:_ {result.error}')
    elif not result.findings:
        body_lines.append('No findings above threshold.')
    else:
        if result.summary:
            body_lines.extend([result.summary, ''])
        for severity in SEVERITY_ORDER:
            severity_findings = [finding for finding in result.findings if finding.severity == severity]
            if not severity_findings:
                continue
            body_lines.append(f'### {severity.title()}')
            for index, finding in enumerate(severity_findings, start=1):
                body_lines.extend(_render_finding(index, finding))
            body_lines.append('')
        while body_lines and not body_lines[-1]:
            body_lines.pop()

    if not collapse_sections:
        return [header, '', *body_lines]

    return [header, '', '<details open>', '<summary>Findings</summary>', '', *body_lines, '</details>']


def _render_finding(index: int, finding: ReviewFinding) -> Iterable[str]:
    location = _format_location(finding)
    title = f'{index}. **{finding.title}**'
    if location:
        title = f'{title} in `{location}`'
    yield title
    yield f'   - Summary: {finding.summary}'
    if finding.recommendation:
        yield f'   - Recommendation: {finding.recommendation}'
    if finding.rule_id:
        yield f'   - Rule: `{finding.rule_id}`'


def _format_location(finding: ReviewFinding) -> str | None:
    if not finding.file_path:
        return None
    if finding.line_start is None:
        return finding.file_path
    if finding.line_end is None or finding.line_end == finding.line_start:
        return f'{finding.file_path}:{finding.line_start}'
    return f'{finding.file_path}:{finding.line_start}-{finding.line_end}'
