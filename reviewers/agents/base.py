from __future__ import annotations

import json
from collections.abc import Sequence
from json import JSONDecodeError
from typing import Any, Protocol, cast

from reviewers.config import AgentConfig
from reviewers.models.base import ModelClient
from reviewers.schemas import AgentName, ReviewContext, ReviewFinding, ReviewResult, Severity, SEVERITY_ORDER

SEVERITY_ALIASES: dict[str, Severity] = {
    'blocker': 'critical',
    'critical': 'critical',
    'severe': 'high',
    'high': 'high',
    'major': 'high',
    'medium': 'medium',
    'moderate': 'medium',
    'warning': 'medium',
    'warn': 'medium',
    'low': 'low',
    'minor': 'low',
    'info': 'info',
    'informational': 'info',
    'note': 'info',
}


class Reviewer(Protocol):
    name: AgentName

    async def review(
        self,
        context: ReviewContext,
        agent_config: AgentConfig,
        model_client: ModelClient,
    ) -> ReviewResult: ...


def extract_json_payload(raw_response: str) -> Any | None:
    candidates = [raw_response.strip()]
    stripped = raw_response.strip()

    if stripped.startswith('```'):
        fence_lines = [line for line in stripped.splitlines() if not line.strip().startswith('```')]
        candidates.append('\n'.join(fence_lines).strip())

    object_start = stripped.find('{')
    object_end = stripped.rfind('}')
    if object_start != -1 and object_end != -1 and object_end > object_start:
        candidates.append(stripped[object_start : object_end + 1])

    array_start = stripped.find('[')
    array_end = stripped.rfind(']')
    if array_start != -1 and array_end != -1 and array_end > array_start:
        candidates.append(stripped[array_start : array_end + 1])

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except JSONDecodeError:
            continue
    return None


def parse_review_response(
    *,
    agent: AgentName,
    raw_response: str,
    default_title: str,
    summary_subject: str,
    empty_summary: str,
    parse_error_summary: str,
) -> tuple[list[ReviewFinding], str, str | None]:
    if not raw_response or not raw_response.strip():
        return [], empty_summary, 'Empty response from model.'

    payload = extract_json_payload(raw_response)
    if payload is None:
        return [], parse_error_summary, 'Malformed JSON response from model.'

    if isinstance(payload, list):
        data: dict[str, Any] = {'summary': '', 'findings': payload}
    elif isinstance(payload, dict):
        data = payload
    else:
        return [], parse_error_summary, 'Unexpected JSON structure from model.'

    findings_payload = data.get('findings', data.get('issues', []))
    findings = normalize_findings(agent=agent, findings_payload=findings_payload, default_title=default_title)
    summary = clean_text(data.get('summary', data.get('overview', data.get('assessment'))))
    summary = summary or default_summary(findings, summary_subject)
    return findings, summary, None


def normalize_findings(*, agent: AgentName, findings_payload: Any, default_title: str) -> list[ReviewFinding]:
    if not isinstance(findings_payload, list):
        return []

    normalized: list[ReviewFinding] = []
    for item in findings_payload:
        finding = normalize_finding_payload(agent=agent, payload=item, default_title=default_title)
        if finding is not None:
            normalized.append(finding)
    return normalized


def normalize_finding_payload(
    *,
    agent: AgentName,
    payload: Any,
    default_title: str,
) -> ReviewFinding | None:
    if not isinstance(payload, dict):
        return None

    title = clean_text(payload.get('title', payload.get('name')))
    summary = clean_text(payload.get('summary', payload.get('description', payload.get('details'))))
    if not title and not summary:
        return None

    if not title:
        title = default_title
    if not summary:
        summary = title

    recommendation = clean_text(
        payload.get(
            'recommendation',
            payload.get('suggestion', payload.get('fix', payload.get('remediation', payload.get('resolution')))),
        )
    )
    if recommendation is None and isinstance(payload.get('recommendations'), list):
        recommendations = [clean_text(item) for item in payload['recommendations']]
        recommendation = '; '.join(item for item in recommendations if item)
        recommendation = recommendation or None

    line_start = coerce_int(
        payload.get('line_start', payload.get('start_line', payload.get('line', payload.get('line_number'))))
    )
    line_end = coerce_int(payload.get('line_end', payload.get('end_line')))
    if line_start is None:
        line_end = None
    elif line_end is None or line_end < line_start:
        line_end = line_start

    return ReviewFinding(
        agent=agent,
        severity=normalize_severity(payload.get('severity')),
        title=title,
        summary=summary,
        file_path=clean_text(payload.get('file_path', payload.get('file', payload.get('filename', payload.get('path'))))),
        line_start=line_start,
        line_end=line_end,
        recommendation=recommendation,
        rule_id=clean_text(payload.get('rule_id', payload.get('rule', payload.get('ruleId')))),
    )


def normalize_severity(value: Any) -> Severity:
    normalized = str(value or '').strip().lower()
    if normalized in SEVERITY_ORDER:
        return cast(Severity, normalized)
    return SEVERITY_ALIASES.get(normalized, 'medium')


def coerce_int(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def default_summary(findings: Sequence[ReviewFinding], summary_subject: str) -> str:
    if not findings:
        return f'No significant {summary_subject.lower()} findings identified.'
    count = len(findings)
    suffix = 's' if count != 1 else ''
    return f'Identified {count} {summary_subject.lower()} finding{suffix}.'
