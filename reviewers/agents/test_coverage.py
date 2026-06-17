from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import PurePosixPath

from reviewers.agents.base import normalize_finding_payload, parse_review_response
from reviewers.config import AgentConfig
from reviewers.models.base import ModelClient
from reviewers.schemas import AgentName, ChangedFile, ReviewContext, ReviewFinding, ReviewResult

__test__ = False
logger = logging.getLogger(__name__)
DEFAULT_RULES = [
    'Identify changed logic without matching tests.',
    'Flag missing edge case coverage.',
    'Check assertions for meaningful behavior.',
    'Call out risky refactors without regression tests.',
]


class TestCoverageReviewer:
    name: AgentName = 'test_coverage'

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
            logger.exception('Test coverage model request failed.')
            return ReviewResult(
                agent=self.name,
                model=agent_config.model,
                summary='Test coverage review failed.',
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
                'You are an expert software test reviewer for pull requests.',
                'Review only the changed code shown in the diff.',
                'Changed code paths without corresponding test updates. Missing integration test scenarios. Weak or missing assertions.',
                'Return JSON only. Do not wrap the JSON in markdown fences.',
                'Use this schema exactly:',
                '{',
                '  "summary": "short overall assessment",',
                '  "raw_notes": "optional short notes",',
                '  "findings": [',
                '    {',
                '      "severity": "critical|high|medium|low|info",',
                '      "title": "short finding title",',
                '      "summary": "why this matters in this PR",',
                '      "file_path": "path/to/test_or_source.py or null",',
                '      "line_start": 10,',
                '      "line_end": 12,',
                '      "recommendation": "specific suggested improvement",',
                '      "rule_id": "optional-stable-rule-id"',
                '    }',
                '  ]',
                '}',
                *[f'- {rule}' for rule in rules],
            ]
        )

    def _build_user_prompt(self, context: ReviewContext, rules: Sequence[str]) -> str:
        source_files = [file for file in context.files if not self._is_test_file(file.path)]
        test_files = [file for file in context.files if self._is_test_file(file.path)]
        pr_body = context.body.strip() or '(no description provided)'
        return '\n'.join(
            [
                f'PR Title: {context.title}',
                f'PR Description:\n{pr_body}',
                f'Base Branch: {context.base_branch}',
                f'Head Branch: {context.head_branch}',
                '',
                'Coverage checklist:',
                *[f'- {rule}' for rule in rules],
                '',
                'Source files changed:',
                '\n\n'.join(self._format_file_section(file) for file in source_files) or '(none)',
                '',
                'Test files changed:',
                '\n\n'.join(self._format_file_section(file) for file in test_files) or '(none)',
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
            default_title='Test coverage issue',
            summary_subject='Test coverage',
            empty_summary='Test coverage review returned no findings.',
            parse_error_summary='Test coverage review could not be parsed.',
        )

    def _normalize_finding(self, payload: object) -> ReviewFinding | None:
        return normalize_finding_payload(agent=self.name, payload=payload, default_title='Test coverage issue')

    def _is_test_file(self, path: str) -> bool:
        pure_path = PurePosixPath(path)
        return 'tests' in pure_path.parts or pure_path.name.startswith('test_') or pure_path.name.endswith('_test.py')
