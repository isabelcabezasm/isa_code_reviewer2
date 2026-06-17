from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from reviewers.diff_parser import normalize_patch
from reviewers.schemas import ChangedFile, PullRequestRef, ReviewContext

GITHUB_API_URL = 'https://api.github.com'
STICKY_COMMENT_MARKER = '<!-- code-reviewer:pr-review -->'


class GitHubClient:
    def __init__(self, *, token: str, repository: str, timeout: float = 30.0) -> None:
        owner, repo = parse_repository(repository)
        self.owner = owner
        self.repo = repo
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_URL,
            timeout=timeout,
            headers={
                'Accept': 'application/vnd.github+json',
                'Authorization': f'Bearer {token}',
                'User-Agent': 'code-reviewer-action',
            },
        )

    async def __aenter__(self) -> 'GitHubClient':
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_pull_request(self, pr_number: int) -> dict[str, Any]:
        return await self._request_json('GET', f'/repos/{self.owner}/{self.repo}/pulls/{pr_number}')

    async def fetch_changed_files(
        self,
        pr_number: int,
        *,
        max_files: int,
        max_patch_chars_per_file: int,
    ) -> list[ChangedFile]:
        files: list[ChangedFile] = []
        page = 1
        while len(files) < max_files:
            data = await self._request_json(
                'GET',
                f'/repos/{self.owner}/{self.repo}/pulls/{pr_number}/files',
                params={'per_page': min(100, max_files - len(files)), 'page': page},
            )
            if not isinstance(data, list) or not data:
                break
            for item in data:
                files.append(
                    ChangedFile(
                        path=str(item['filename']),
                        status=str(item.get('status', 'modified')),
                        patch=normalize_patch(item.get('patch'), max_patch_chars_per_file),
                        additions=int(item.get('additions', 0)),
                        deletions=int(item.get('deletions', 0)),
                    )
                )
                if len(files) >= max_files:
                    break
            if len(data) < 100:
                break
            page += 1
        return files

    async def fetch_review_context(
        self,
        pr_number: int,
        *,
        max_files: int,
        max_patch_chars_per_file: int,
    ) -> ReviewContext:
        pr_data = await self.fetch_pull_request(pr_number)
        files = await self.fetch_changed_files(
            pr_number,
            max_files=max_files,
            max_patch_chars_per_file=max_patch_chars_per_file,
        )
        pr_ref = PullRequestRef(
            owner=self.owner,
            repo=self.repo,
            number=pr_number,
            head_sha=str(pr_data['head']['sha']),
            base_sha=str(pr_data['base']['sha']),
        )
        return ReviewContext(
            pr=pr_ref,
            title=str(pr_data.get('title', '')),
            body=str(pr_data.get('body') or ''),
            base_branch=str(pr_data['base']['ref']),
            head_branch=str(pr_data['head']['ref']),
            files=files,
        )

    async def upsert_sticky_comment(self, pr_number: int, body: str) -> int:
        existing_comment = await self._find_existing_comment(pr_number)
        if existing_comment is None:
            data = await self._request_json(
                'POST',
                f'/repos/{self.owner}/{self.repo}/issues/{pr_number}/comments',
                json_body={'body': body},
            )
            return int(data['id'])

        data = await self._request_json(
            'PATCH',
            f"/repos/{self.owner}/{self.repo}/issues/comments/{existing_comment['id']}",
            json_body={'body': body},
        )
        return int(data['id'])

    async def _find_existing_comment(self, pr_number: int) -> dict[str, Any] | None:
        page = 1
        while True:
            comments = await self._request_json(
                'GET',
                f'/repos/{self.owner}/{self.repo}/issues/{pr_number}/comments',
                params={'per_page': 100, 'page': page},
            )
            if not isinstance(comments, list) or not comments:
                return None
            for comment in comments:
                body = str(comment.get('body') or '')
                if STICKY_COMMENT_MARKER in body:
                    return comment
            if len(comments) < 100:
                return None
            page += 1

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._client.request(method, path, params=params, json=json_body)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network failure path
            detail = response.text.strip()
            raise RuntimeError(f'GitHub API request failed: {method} {path} -> {response.status_code} {detail}') from exc
        return response.json()


def load_event_payload(event_path: str) -> dict[str, Any]:
    payload = json.loads(Path(event_path).read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('GitHub event payload must be a JSON object.')
    return payload


def parse_repository(repository: str) -> tuple[str, str]:
    parts = repository.split('/', 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError(f'Invalid repository value: {repository}')
    return parts[0], parts[1]


def pull_request_number_from_event(event_payload: dict[str, Any]) -> int:
    pull_request = event_payload.get('pull_request')
    if not isinstance(pull_request, dict) or 'number' not in pull_request:
        raise ValueError('GitHub event payload does not contain pull_request.number.')
    return int(pull_request['number'])
