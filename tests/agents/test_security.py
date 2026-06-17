from __future__ import annotations

import asyncio

from reviewers.agents.security import DEFAULT_RULES, SecurityReviewer
from reviewers.config import AgentConfig
from reviewers.schemas import ChangedFile, PullRequestRef, ReviewContext


class StubModelClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, str | float]] = []

    async def review(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
            }
        )
        return self.response


def build_context() -> ReviewContext:
    return ReviewContext(
        pr=PullRequestRef(
            owner="octo",
            repo="code-reviewer",
            number=7,
            head_sha="head123",
            base_sha="base123",
        ),
        title="Add webhook processing",
        body="Introduces webhook handling and updates request validation.",
        base_branch="main",
        head_branch="feature/webhooks",
        files=[
            ChangedFile(
                path="app/webhooks.py",
                status="modified",
                patch="@@ -1,2 +1,5 @@\n+import subprocess\n+API_KEY = 'hardcoded'\n+subprocess.run(user_input, shell=True)",
                additions=3,
                deletions=0,
            )
        ],
    )


def build_config(rules: list[str] | None = None) -> AgentConfig:
    return AgentConfig(
        enabled=True,
        provider="openai",
        model="gpt-4o",
        severity_threshold="low",
        rules=rules or [],
    )


def test_prompt_construction_includes_context_and_rules() -> None:
    reviewer = SecurityReviewer()
    context = build_context()
    rules = ["Require webhook signature validation."]

    system_prompt = reviewer._build_system_prompt(rules)
    user_prompt = reviewer._build_user_prompt(context, rules)

    assert "hardcoded secrets" in system_prompt
    assert "OWASP Top 10" in system_prompt
    assert "unsafe deserialization" in system_prompt
    assert "Return JSON only" in system_prompt
    assert "PR Title: Add webhook processing" in user_prompt
    assert "Introduces webhook handling" in user_prompt
    assert "app/webhooks.py" in user_prompt
    assert "API_KEY = 'hardcoded'" in user_prompt
    assert "Require webhook signature validation." in user_prompt


def test_parse_review_response_valid_json_normalizes_findings() -> None:
    reviewer = SecurityReviewer()

    findings, summary, error = reviewer._parse_review_response(
        """
        {
          "summary": "A hardcoded credential and command injection risk were introduced.",
          "findings": [
            {
              "severity": "HIGH",
              "title": "Hardcoded API key",
              "summary": "A secret is committed directly in source code.",
              "file": "app/webhooks.py",
              "line": "2",
              "recommendation": "Load the key from a secret manager.",
              "rule": "hardcoded-secrets"
            }
          ]
        }
        """
    )

    assert error is None
    assert summary == "A hardcoded credential and command injection risk were introduced."
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].file_path == "app/webhooks.py"
    assert findings[0].line_start == 2
    assert findings[0].line_end == 2
    assert findings[0].rule_id == "hardcoded-secrets"


def test_parse_review_response_handles_malformed_json() -> None:
    reviewer = SecurityReviewer()

    findings, summary, error = reviewer._parse_review_response("not-json at all")

    assert findings == []
    assert summary == "Security review could not be parsed."
    assert error == "Malformed JSON response from model."


def test_parse_review_response_handles_empty_response() -> None:
    reviewer = SecurityReviewer()

    findings, summary, error = reviewer._parse_review_response("   ")

    assert findings == []
    assert summary == "Security review returned no findings."
    assert error == "Empty response from model."


def test_default_rules_are_applied_when_config_rules_missing() -> None:
    reviewer = SecurityReviewer()

    rules = reviewer._resolve_rules(build_config([]))

    assert rules == DEFAULT_RULES


def test_finding_normalization_maps_severity_and_lines() -> None:
    reviewer = SecurityReviewer()

    findings, summary, error = reviewer._parse_review_response(
        """
        {
          "findings": [
            {
              "severity": "warning",
              "description": "User input is passed directly to a shell command.",
              "path": "app/webhooks.py",
              "line_start": "15",
              "line_end": "7",
              "remediation": "Avoid shell=True and use an allowlist."
            },
            {
              "severity": "unknown",
              "title": "",
              "summary": "Missing auth check on admin path.",
              "file_path": "",
              "line_start": "abc"
            }
          ]
        }
        """
    )

    assert error is None
    assert summary == "Identified 2 security findings."
    assert len(findings) == 2
    assert findings[0].severity == "medium"
    assert findings[0].title == "Security issue"
    assert findings[0].line_start == 15
    assert findings[0].line_end == 15
    assert findings[0].recommendation == "Avoid shell=True and use an allowlist."
    assert findings[1].severity == "medium"
    assert findings[1].file_path is None
    assert findings[1].line_start is None


def test_review_uses_default_rules_and_returns_normalized_result() -> None:
    reviewer = SecurityReviewer()
    context = build_context()
    client = StubModelClient(
        """
        ```json
        {
          "findings": [
            {
              "severity": "BLOCKER",
              "title": "Command injection via shell=True",
              "summary": "Unsanitized user input is executed by the shell.",
              "path": "app/webhooks.py",
              "start_line": 3,
              "end_line": 3,
              "suggestion": "Pass an argument list and validate allowed commands."
            }
          ]
        }
        ```
        """
    )

    result = asyncio.run(reviewer.review(context, build_config([]), client))

    assert result.agent == "security"
    assert result.model == "gpt-4o"
    assert result.error is None
    assert result.summary == "Identified 1 security finding."
    assert result.findings[0].severity == "critical"
    assert result.findings[0].file_path == "app/webhooks.py"
    assert result.findings[0].line_start == 3
    assert result.findings[0].line_end == 3
    assert result.findings[0].recommendation == "Pass an argument list and validate allowed commands."
    assert client.calls
    assert DEFAULT_RULES[0] in str(client.calls[0]["user_prompt"])
