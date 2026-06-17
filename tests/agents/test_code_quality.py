from __future__ import annotations

import asyncio

from reviewers.agents.code_quality import CodeQualityReviewer, DEFAULT_RULES
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
            number=42,
            head_sha="head123",
            base_sha="base123",
        ),
        title="Refactor parsing flow",
        body="Simplifies response parsing and adds extra logging.",
        base_branch="main",
        head_branch="feature/refactor-parser",
        files=[
            ChangedFile(
                path="reviewers/agents/code_quality.py",
                status="modified",
                patch="@@ -1,2 +1,4 @@\n-def old():\n-    pass\n+def parse_result(payload: str) -> dict:\n+    return {}",
                additions=2,
                deletions=2,
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
    reviewer = CodeQualityReviewer()
    context = build_context()
    rules = ["Prefer small helpers.", "Keep naming descriptive."]

    system_prompt = reviewer._build_system_prompt(rules)
    user_prompt = reviewer._build_user_prompt(context, rules)

    assert "Naming conventions" in system_prompt
    assert "SOLID principle adherence" in system_prompt
    assert '"findings": [' in system_prompt
    assert "PR Title: Refactor parsing flow" in user_prompt
    assert "Simplifies response parsing" in user_prompt
    assert "reviewers/agents/code_quality.py" in user_prompt
    assert "Prefer small helpers." in user_prompt
    assert "@@ -1,2 +1,4 @@" in user_prompt


def test_parse_review_response_valid_json_normalizes_findings() -> None:
    reviewer = CodeQualityReviewer()

    findings, summary, error = reviewer._parse_review_response(
        """
        {
          "summary": "A few maintainability issues found.",
          "findings": [
            {
              "severity": "WARNING",
              "title": "Long function",
              "summary": "The function now mixes parsing and formatting responsibilities.",
              "file": "reviewers/parser.py",
              "line": "18",
              "recommendation": "Extract the formatting branch into a helper.",
              "rule": "single-responsibility"
            },
            {
              "severity": "minor",
              "summary": "Unused import remains after the refactor.",
              "file_path": "reviewers/parser.py",
              "line_start": 3
            }
          ]
        }
        """
    )

    assert error is None
    assert summary == "A few maintainability issues found."
    assert len(findings) == 2
    assert findings[0].severity == "medium"
    assert findings[0].line_start == 18
    assert findings[0].line_end == 18
    assert findings[0].rule_id == "single-responsibility"
    assert findings[1].severity == "low"
    assert findings[1].title == "Code quality issue"


def test_parse_review_response_handles_malformed_json() -> None:
    reviewer = CodeQualityReviewer()

    findings, summary, error = reviewer._parse_review_response("not-json at all")

    assert findings == []
    assert summary == "Code quality review could not be parsed."
    assert error == "Malformed JSON response from model."


def test_parse_review_response_handles_empty_response() -> None:
    reviewer = CodeQualityReviewer()

    findings, summary, error = reviewer._parse_review_response("   ")

    assert findings == []
    assert summary == "Code quality review returned no findings."
    assert error == "Empty response from model."


def test_default_rules_are_applied_when_config_rules_missing() -> None:
    reviewer = CodeQualityReviewer()

    rules = reviewer._resolve_rules(build_config([]))

    assert rules == DEFAULT_RULES


def test_review_uses_default_rules_and_returns_normalized_result() -> None:
    reviewer = CodeQualityReviewer()
    context = build_context()
    client = StubModelClient(
        """
        ```json
        {
          "findings": [
            {
              "severity": "BLOCKER",
              "title": "Nested control flow",
              "summary": "The new branch structure is hard to follow.",
              "path": "reviewers/agents/code_quality.py",
              "start_line": 27,
              "end_line": 40,
              "suggestion": "Split validation from rendering."
            }
          ]
        }
        ```
        """
    )

    result = asyncio.run(reviewer.review(context, build_config([]), client))

    assert result.agent == "code_quality"
    assert result.model == "gpt-4o"
    assert result.error is None
    assert result.summary == "Identified 1 code quality finding."
    assert result.findings[0].severity == "critical"
    assert result.findings[0].file_path == "reviewers/agents/code_quality.py"
    assert result.findings[0].line_start == 27
    assert result.findings[0].line_end == 40
    assert result.findings[0].recommendation == "Split validation from rendering."
    assert client.calls
    assert DEFAULT_RULES[0] in str(client.calls[0]["user_prompt"])
