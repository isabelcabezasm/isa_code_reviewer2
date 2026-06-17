from __future__ import annotations

import logging
from collections.abc import Sequence

from reviewers.agents.base import parse_review_response
from reviewers.config import AgentConfig
from reviewers.models.base import ModelClient
from reviewers.schemas import AgentName, ChangedFile, ReviewContext, ReviewResult

logger = logging.getLogger(__name__)
DEFAULT_RULES = [
    'Enforce clear naming and small functions.',
    'Flag duplication and dead code.',
    'Recommend simpler control flow.',
    'Check for proper error handling.',
    'Review type hints completeness.',
    'Flag overly complex functions.',
]


class CodeQualityReviewer:
    name: AgentName = 'code_quality'

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
            logger.exception('Code quality model request failed.')
            return ReviewResult(
                agent=self.name,
                model=agent_config.model,
                summary='Code quality review failed.',
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
                'You are an expert code quality reviewer for pull requests.',
                'Review only the changed code shown in the diff.',
                'Prioritize actionable findings that improve maintainability, readability, and long-term correctness.',
                'Evaluate the diff for all of the following:',
                '- Naming conventions: clear, descriptive, and consistent identifiers.',
                '- Function and method size: prefer focused, single-responsibility units.',
                '- Code duplication and DRY violations.',
                '- Error handling quality, including missing or inconsistent handling paths.',
                '- Dead code, unused imports, unused variables, and unreachable branches.',
                '- Complexity: deep nesting, hard-to-follow branching, long parameter lists, hidden side effects.',
                '- Design patterns and anti-patterns, including tight coupling and poor separation of concerns.',
                '- Documentation, comments, and docstrings when behavior is non-obvious or public APIs change.',
                '- Readability and maintainability, including confusing control flow or poor structure.',
                '- SOLID principle adherence where relevant.',
                '- Typing and type hints completeness and usefulness.',
                '- Potential performance issues introduced by the change.',
                'Use these review rules while evaluating the diff:',
                *[f'- {rule}' for rule in rules],
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
                '      "file_path": "path/to/file.py or null",',
                '      "line_start": 10,',
                '      "line_end": 12,',
                '      "recommendation": "specific suggested improvement",',
                '      "rule_id": "optional-stable-rule-id"',
                '    }',
                '  ]',
                '}',
                'If there are no meaningful issues, return an empty findings array and explain briefly in summary.',
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
                'Review rules:',
                *[f'- {rule}' for rule in rules],
                '',
                'Changed files and patches:',
                file_sections or '(no changed files provided)',
                '',
                'Return a JSON object with keys summary, raw_notes, and findings.',
                'Every finding must include severity, title, summary, file_path when known, line_start when known, and a specific recommendation.',
            ]
        )

    def _format_file_section(self, changed_file: ChangedFile) -> str:
        patch = changed_file.patch if changed_file.patch else '(patch unavailable)'
        return '\n'.join(
            [
                f'File: {changed_file.path}',
                f'Status: {changed_file.status}',
                f'Additions: {changed_file.additions}',
                f'Deletions: {changed_file.deletions}',
                'Patch:',
                patch,
            ]
        )

    def _parse_review_response(self, raw_response: str):
        return parse_review_response(
            agent=self.name,
            raw_response=raw_response,
            default_title='Code quality issue',
            summary_subject='Code quality',
            empty_summary='Code quality review returned no findings.',
            parse_error_summary='Code quality review could not be parsed.',
        )
