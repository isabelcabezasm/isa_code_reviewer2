from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal['critical', 'high', 'medium', 'low', 'info']
AgentName = Literal['security', 'code_quality', 'test_coverage']

SEVERITY_ORDER: tuple[Severity, ...] = ('critical', 'high', 'medium', 'low', 'info')
SEVERITY_RANK: dict[Severity, int] = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
AGENT_ORDER: tuple[AgentName, ...] = ('security', 'code_quality', 'test_coverage')
AGENT_DISPLAY_NAMES: dict[AgentName, str] = {
    'security': 'Security',
    'code_quality': 'Code Quality',
    'test_coverage': 'Test Coverage',
}


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int
    head_sha: str
    base_sha: str


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    patch: str | None
    additions: int
    deletions: int


@dataclass(frozen=True)
class ReviewContext:
    pr: PullRequestRef
    title: str
    body: str
    base_branch: str
    head_branch: str
    files: list[ChangedFile]


@dataclass(frozen=True)
class ReviewFinding:
    agent: AgentName
    severity: Severity
    title: str
    summary: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    recommendation: str | None = None
    rule_id: str | None = None


@dataclass(frozen=True)
class ReviewResult:
    agent: AgentName
    model: str
    findings: list[ReviewFinding] = field(default_factory=list)
    summary: str = ''
    raw_notes: str = ''
    error: str | None = None


@dataclass(frozen=True)
class ReviewResultBundle:
    context: ReviewContext
    results: list[ReviewResult] = field(default_factory=list)
    comment_body: str = ''
    posted_comment_id: int | None = None
    skipped_reason: str | None = None
    agent_errors: dict[AgentName, str] = field(default_factory=dict)
