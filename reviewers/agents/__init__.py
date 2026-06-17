from __future__ import annotations

from reviewers.agents.code_quality import CodeQualityReviewer
from reviewers.agents.security import SecurityReviewer
from reviewers.agents.test_coverage import TestCoverageReviewer
from reviewers.schemas import AGENT_ORDER, AgentName

_REVIEWERS = {
    'security': SecurityReviewer(),
    'code_quality': CodeQualityReviewer(),
    'test_coverage': TestCoverageReviewer(),
}


def get_reviewer(agent_name: AgentName):
    return _REVIEWERS[agent_name]


def get_reviewers() -> dict[AgentName, object]:
    return {agent_name: _REVIEWERS[agent_name] for agent_name in AGENT_ORDER}


__all__ = [
    'CodeQualityReviewer',
    'SecurityReviewer',
    'TestCoverageReviewer',
    'get_reviewer',
    'get_reviewers',
]
