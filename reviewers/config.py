from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from reviewers.schemas import AGENT_ORDER, AgentName, Severity, SEVERITY_ORDER

DEFAULT_AGENT_MODELS: dict[AgentName, tuple[str, str, Severity]] = {
    'security': ('anthropic', 'claude-3-7-sonnet-latest', 'medium'),
    'code_quality': ('openai', 'gpt-4o', 'low'),
    'test_coverage': ('openai', 'gpt-4o-mini', 'medium'),
}
DEFAULT_AGENT_RULES: dict[AgentName, list[str]] = {
    'security': [
        'Flag hardcoded secrets and tokens',
        'Check for OWASP Top 10 risks',
        'Identify unsafe deserialization and command execution',
    ],
    'code_quality': [
        'Enforce clear naming and small functions',
        'Flag duplication and dead code',
        'Recommend simpler control flow where needed',
    ],
    'test_coverage': [
        'Identify changed logic without matching tests',
        'Flag missing edge case coverage',
        'Check assertions for meaningful behavior',
    ],
}


@dataclass(frozen=True)
class ReviewSettings:
    draft_prs: bool = False
    max_files: int = 100
    max_patch_chars_per_file: int = 12000


@dataclass(frozen=True)
class CommentSettings:
    mode: Literal['sticky'] = 'sticky'
    collapse_sections: bool = True


@dataclass(frozen=True)
class AgentConfig:
    enabled: bool
    provider: str
    model: str
    severity_threshold: Severity
    rules: list[str] = field(default_factory=list)
    temperature: float = 0.0


@dataclass(frozen=True)
class ReviewConfig:
    version: int = 1
    review: ReviewSettings = field(default_factory=ReviewSettings)
    comment: CommentSettings = field(default_factory=CommentSettings)
    agents: dict[AgentName, AgentConfig] = field(default_factory=dict)


def default_config() -> ReviewConfig:
    return ReviewConfig(
        agents={
            agent_name: AgentConfig(
                enabled=True,
                provider=provider,
                model=model,
                severity_threshold=threshold,
                rules=list(DEFAULT_AGENT_RULES[agent_name]),
            )
            for agent_name, (provider, model, threshold) in DEFAULT_AGENT_MODELS.items()
        }
    )


def load_config(path: str = '.github/code-review-config.yml') -> ReviewConfig:
    config_path = Path(path)
    if not config_path.exists():
        return default_config()

    raw_data = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f'Config file {path} must contain a mapping at the top level.')

    validate_raw_config(raw_data)
    merged = _merge_with_defaults(raw_data)
    config = _materialize_config(merged)
    validate_config(config)
    return config


def validate_raw_config(raw_config: dict[str, Any]) -> None:
    agents = raw_config.get('agents')
    if agents is None:
        return
    if not isinstance(agents, dict):
        raise ValueError('The agents section must be a mapping.')

    for raw_name, raw_agent in agents.items():
        if raw_name not in AGENT_ORDER:
            raise ValueError(f'Unknown agent name: {raw_name}')
        if not isinstance(raw_agent, dict):
            raise ValueError(f'Agent config for {raw_name} must be a mapping.')
        if raw_agent.get('enabled', True):
            missing = [field_name for field_name in ('provider', 'model') if field_name not in raw_agent]
            if missing:
                joined = ', '.join(missing)
                raise ValueError(f'Enabled agent {raw_name} is missing required field(s): {joined}')


def validate_config(config: ReviewConfig) -> None:
    if config.version < 1:
        raise ValueError('Config version must be at least 1.')
    if config.review.max_files < 1:
        raise ValueError('review.max_files must be at least 1.')
    if config.review.max_patch_chars_per_file < 1:
        raise ValueError('review.max_patch_chars_per_file must be at least 1.')
    if config.comment.mode != 'sticky':
        raise ValueError('Only sticky comment mode is currently supported.')

    unknown_agents = set(config.agents).difference(AGENT_ORDER)
    if unknown_agents:
        raise ValueError(f'Unknown agent names: {sorted(unknown_agents)}')

    for agent_name in AGENT_ORDER:
        if agent_name not in config.agents:
            raise ValueError(f'Missing configuration for required agent: {agent_name}')
        agent_config = config.agents[agent_name]
        if agent_config.severity_threshold not in SEVERITY_ORDER:
            raise ValueError(
                f'Invalid severity threshold for {agent_name}: {agent_config.severity_threshold}'
            )
        if agent_config.enabled and (not agent_config.provider or not agent_config.model):
            raise ValueError(f'Enabled agent {agent_name} must define both provider and model.')


def _merge_with_defaults(raw_data: dict[str, Any]) -> dict[str, Any]:
    defaults = default_config()
    merged_agents = {
        agent_name: {
            'enabled': defaults.agents[agent_name].enabled,
            'provider': defaults.agents[agent_name].provider,
            'model': defaults.agents[agent_name].model,
            'severity_threshold': defaults.agents[agent_name].severity_threshold,
            'rules': list(defaults.agents[agent_name].rules),
            'temperature': defaults.agents[agent_name].temperature,
        }
        for agent_name in AGENT_ORDER
    }

    raw_agents = raw_data.get('agents') or {}
    for agent_name in AGENT_ORDER:
        if agent_name in raw_agents:
            merged_agents[agent_name].update(raw_agents[agent_name])

    review_section = raw_data.get('review') or {}
    comment_section = raw_data.get('comment') or {}

    return {
        'version': raw_data.get('version', defaults.version),
        'review': {
            'draft_prs': review_section.get('draft_prs', defaults.review.draft_prs),
            'max_files': review_section.get('max_files', defaults.review.max_files),
            'max_patch_chars_per_file': review_section.get(
                'max_patch_chars_per_file', defaults.review.max_patch_chars_per_file
            ),
        },
        'comment': {
            'mode': comment_section.get('mode', defaults.comment.mode),
            'collapse_sections': comment_section.get(
                'collapse_sections', defaults.comment.collapse_sections
            ),
        },
        'agents': merged_agents,
    }


def _materialize_config(raw_config: dict[str, Any]) -> ReviewConfig:
    agents: dict[AgentName, AgentConfig] = {
        cast(AgentName, agent_name): AgentConfig(
            enabled=bool(agent_values.get('enabled', True)),
            provider=str(agent_values.get('provider', '')).strip(),
            model=str(agent_values.get('model', '')).strip(),
            severity_threshold=_normalize_severity(agent_values.get('severity_threshold', 'medium')),
            rules=[str(rule).strip() for rule in agent_values.get('rules', []) if str(rule).strip()],
            temperature=float(agent_values.get('temperature', 0.0)),
        )
        for agent_name, agent_values in raw_config['agents'].items()
    }
    review = raw_config['review']
    comment = raw_config['comment']
    return ReviewConfig(
        version=int(raw_config.get('version', 1)),
        review=ReviewSettings(
            draft_prs=bool(review.get('draft_prs', False)),
            max_files=int(review.get('max_files', 100)),
            max_patch_chars_per_file=int(review.get('max_patch_chars_per_file', 12000)),
        ),
        comment=CommentSettings(
            mode=cast(Literal['sticky'], str(comment.get('mode', 'sticky')).strip() or 'sticky'),
            collapse_sections=bool(comment.get('collapse_sections', True)),
        ),
        agents=agents,
    )


def _normalize_severity(value: Any) -> Severity:
    severity = str(value).strip().lower()
    if severity not in SEVERITY_ORDER:
        raise ValueError(f'Invalid severity value: {value}')
    return cast(Severity, severity)
