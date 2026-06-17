from __future__ import annotations

import logging
from collections.abc import Sequence

from reviewers.agents.base import normalize_finding_payload, parse_review_response
from reviewers.config import AgentConfig
from reviewers.models.base import ModelClient
from reviewers.schemas import AgentName, ChangedFile, ReviewContext, ReviewFinding, ReviewResult

logger = logging.getLogger(__name__)
DEFAULT_RULES = [
    'Flag hardcoded secrets and tokens.',
    'Check for OWASP Top 10 risks.',
    'Identify unsafe deserialization and command execution.',
    'Highlight insecure authentication or authorization changes.',
]


class SecurityReviewer:
    name: AgentName = 'security'

    async def review(
        self,
        context: ReviewContext,
        agent_config: AgentConfig,
        model_client: ModelClient,
    ) -> ReviewResult:
        rules = self._resolve_rules(agent_config)
        try:
            raw_response = await model_client.review(
                model=agent_config.model,
                system_prompt=self._build_system_prompt(rules),
                user_prompt=self._build_user_prompt(context, rules),
                temperature=agent_config.temperature,
            )
        except Exception as exc:  # pragma: no cover - defensive safeguard
            logger.exception('Security model request failed.')
            return ReviewResult(
                agent=self.name,
                model=agent_config.model,
                summary='Security review failed.',
                error=str(exc),
            )

        findings, summary, error = self._parse_review_response(raw_response)
        return ReviewResult(
            agent=self.name,
            model=agent_config.model,
            findings=findings,
            summary=summary,
            raw_notes=raw_response,
            error=error,
        )

    def _resolve_rules(self, agent_config: AgentConfig) -> list[str]:
        rules = [rule.strip() for rule in agent_config.rules if rule.strip()]
        return rules or DEFAULT_RULES.copy()

    def _build_system_prompt(self, rules: Sequence[str]) -> str:
        return '\n'.join(
            [
                'You are an expert application security reviewer for pull requests.',
                'Review only the changed code shown in the diff.',
                'Focus on exploitable issues, privilege escalation, secrets exposure, and unsafe trust boundaries.',
                'Explicitly look for hardcoded secrets, OWASP Top 10 risks, unsafe deserialization, and command execution issues.',
                'Return JSON only. Do not wrap the JSON in markdown fences.',
                'Use this schema exactly with keys summary, raw_notes, and findings, where findings is an array of structured issues.',
                *[f'- {rule}' for rule in rules],
            ]
        )

    def _build_user_prompt(self, context: ReviewContext, rules: Sequence[str]) -> str:
        file_sections = '\n\n'.join(self._format_file_section(file) for file in context.files)
        pr_body = context.body.strip() or '(no description provided)'
        return '\n'.join(
            [
                f'PR Title: {context.title}',
                f'PR Description:\n{pr_body}',
                f'Base Branch: {context.base_branch}',
                f'Head Branch: {context.head_branch}',
                '',
                'Security checklist:',
                *[f'- {rule}' for rule in rules],
                '',
                'Changed files and patches:',
                file_sections or '(no changed files provided)',
            ]
        )

    def _format_file_section(self, changed_file: ChangedFile) -> str:
        return '\n'.join(
            [
                f'File: {changed_file.path}',
                f'Status: {changed_file.status}',
                f'Additions: {changed_file.additions}',
                f'Deletions: {changed_file.deletions}',
                'Patch:',
                changed_file.patch or '(patch unavailable)',
            ]
        )

    def _parse_review_response(self, raw_response: str):
        return parse_review_response(
            agent=self.name,
            raw_response=raw_response,
            default_title='Security issue',
            summary_subject='Security',
            empty_summary='Security review returned no findings.',
            parse_error_summary='Security review could not be parsed.',
        )

    def _normalize_finding(self, payload: object) -> ReviewFinding | None:
        return normalize_finding_payload(agent=self.name, payload=payload, default_title='Security issue')
