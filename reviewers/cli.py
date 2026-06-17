from __future__ import annotations

import asyncio
import logging
import os
from typing import cast

from reviewers.orchestrator import run_pr_review

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def main() -> int:
    github_token = os.getenv('GITHUB_TOKEN')
    event_path = os.getenv('GITHUB_EVENT_PATH')
    repository = os.getenv('GITHUB_REPOSITORY')

    missing = [
        name
        for name, value in (
            ('GITHUB_TOKEN', github_token),
            ('GITHUB_EVENT_PATH', event_path),
            ('GITHUB_REPOSITORY', repository),
        )
        if not value
    ]
    if missing:
        logger.error('Missing required environment variables: %s', ', '.join(missing))
        return 1

    github_token = cast(str, github_token)
    event_path = cast(str, event_path)
    repository = cast(str, repository)

    try:
        bundle = asyncio.run(
            run_pr_review(
                config_path='.github/code-review-config.yml',
                github_token=github_token,
                repository=repository,
                event_path=event_path,
            )
        )
    except Exception:
        logger.exception('PR review run failed.')
        return 1

    if bundle.skipped_reason:
        logger.info('PR review skipped: %s', bundle.skipped_reason)
        return 0

    if bundle.agent_errors:
        logger.warning('PR review completed with agent errors: %s', ', '.join(sorted(bundle.agent_errors)))
    else:
        logger.info('PR review completed successfully.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
