from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import cast

from reviewers.agents import get_reviewer
from reviewers.comment_renderer import render_review_comment
from reviewers.config import ReviewConfig, load_config
from reviewers.github_client import GitHubClient, load_event_payload, pull_request_number_from_event
from reviewers.models.registry import get_model_client
from reviewers.schemas import (
    AGENT_ORDER,
    AgentName,
    PullRequestRef,
    ReviewContext,
    ReviewResult,
    ReviewResultBundle,
    SEVERITY_RANK,
)

logger = logging.getLogger(__name__)


async def run_pr_review(
    *,
    config_path: str,
    github_token: str,
    repository: str,
    event_path: str,
) -> ReviewResultBundle:
    config = load_config(config_path)
    event_payload = load_event_payload(event_path)
    pr_number = pull_request_number_from_event(event_payload)
    initial_context = _context_from_event(repository=repository, event_payload=event_payload)

    if event_payload.get('pull_request', {}).get('draft') and not config.review.draft_prs:
        return ReviewResultBundle(
            context=initial_context,
            skipped_reason='Draft PR reviews are disabled by repository configuration.',
        )

    async with GitHubClient(token=github_token, repository=repository) as github_client:
        context = await fetch_context(github_client, pr_number=pr_number, config=config)
        results = await run_agents(context=context, config=config)
        filtered_results = apply_severity_thresholds(results=results, config=config)
        bundle = ReviewResultBundle(
            context=context,
            results=filtered_results,
            agent_errors={result.agent: result.error for result in filtered_results if result.error},
        )
        comment_body = render_review_comment(bundle, collapse_sections=config.comment.collapse_sections)
        comment_id = await publish_review(github_client, pr_number=pr_number, comment_body=comment_body)
        return replace(bundle, comment_body=comment_body, posted_comment_id=comment_id)


async def fetch_context(
    github_client: GitHubClient,
    *,
    pr_number: int,
    config: ReviewConfig,
) -> ReviewContext:
    return await github_client.fetch_review_context(
        pr_number,
        max_files=config.review.max_files,
        max_patch_chars_per_file=config.review.max_patch_chars_per_file,
    )


async def run_agents(*, context: ReviewContext, config: ReviewConfig) -> list[ReviewResult]:
    tasks = [
        _run_single_agent(agent_name=agent_name, context=context, config=config)
        for agent_name in AGENT_ORDER
        if config.agents[agent_name].enabled
    ]
    task_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[ReviewResult] = []
    enabled_agents: list[AgentName] = [
        agent_name for agent_name in AGENT_ORDER if config.agents[agent_name].enabled
    ]
    for agent_name, result in zip(enabled_agents, task_results, strict=True):
        if isinstance(result, Exception):
            logger.exception('Agent %s crashed.', agent_name, exc_info=result)
            results.append(
                ReviewResult(
                    agent=agent_name,
                    model=config.agents[agent_name].model,
                    summary=f'{agent_name} review failed.',
                    error=str(result),
                )
            )
        else:
            results.append(cast(ReviewResult, result))
    return results


async def publish_review(
    github_client: GitHubClient,
    *,
    pr_number: int,
    comment_body: str,
) -> int:
    return await github_client.upsert_sticky_comment(pr_number, comment_body)


def apply_severity_thresholds(*, results: list[ReviewResult], config: ReviewConfig) -> list[ReviewResult]:
    filtered: list[ReviewResult] = []
    for result in results:
        threshold = config.agents[result.agent].severity_threshold
        allowed_findings = [
            finding
            for finding in result.findings
            if SEVERITY_RANK[finding.severity] <= SEVERITY_RANK[threshold]
        ]
        filtered.append(replace(result, findings=allowed_findings))
    return filtered


async def _run_single_agent(
    *,
    agent_name: AgentName,
    context: ReviewContext,
    config: ReviewConfig,
) -> ReviewResult:
    agent_config = config.agents[agent_name]
    reviewer = get_reviewer(agent_name)
    model_client = get_model_client(agent_config.provider)
    try:
        return await reviewer.review(context, agent_config, model_client)
    except Exception as exc:  # pragma: no cover - extra protection
        logger.exception('Agent %s failed during review.', agent_name)
        return ReviewResult(
            agent=agent_name,
            model=agent_config.model,
            summary=f'{agent_name} review failed.',
            error=str(exc),
        )


def _context_from_event(*, repository: str, event_payload: dict) -> ReviewContext:
    owner, repo = repository.split('/', 1)
    pr_data = event_payload.get('pull_request', {})
    return ReviewContext(
        pr=PullRequestRef(
            owner=owner,
            repo=repo,
            number=int(pr_data.get('number', 0)),
            head_sha=str(pr_data.get('head', {}).get('sha', 'unknown')),
            base_sha=str(pr_data.get('base', {}).get('sha', 'unknown')),
        ),
        title=str(pr_data.get('title', '')),
        body=str(pr_data.get('body') or ''),
        base_branch=str(pr_data.get('base', {}).get('ref', '')),
        head_branch=str(pr_data.get('head', {}).get('ref', '')),
        files=[],
    )
