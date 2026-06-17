from __future__ import annotations

import asyncio

from reviewers.agents.test_coverage import DEFAULT_RULES, TestCoverageReviewer
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
            number=99,
            head_sha="head123",
            base_sha="base123",
        ),
        title="Handle blank user names",
        body="Adds validation for empty values and updates the service flow.",
        base_branch="main",
        head_branch="feature/blank-name-check",
        files=[
            ChangedFile(
                path="reviewers/service.py",
                status="modified",
                patch=(
                    "@@ -1,2 +1,5 @@\n"
                    " def greet(name: str) -> str:\n"
                    "+    if not name:\n"
                    '+        raise ValueError("name required")\n'
                    '     return f"Hello {name}"\n'
                ),
                additions=3,
                deletions=0,
            ),
            ChangedFile(
                path="tests/test_service.py",
                status="modified",
                patch=(
                    "@@ -1,2 +1,4 @@\n"
                    ' def test_greet_happy_path() -> None:\n'
                    '     assert greet("Ada") == "Hello Ada"\n'
                    "+\n"
                    "+def test_greet_blank_name() -> None:\n"
                    "+    ...\n"
                ),
                additions=3,
                deletions=0,
            ),
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


def test_prompt_construction_separates_test_and_non_test_files() -> None:
    reviewer = TestCoverageReviewer()
    context = build_context()
    rules = ["Require regression tests for changed validation behavior."]

    system_prompt = reviewer._build_system_prompt(rules)
    user_prompt = reviewer._build_user_prompt(context, rules)

    assert "Changed code paths without corresponding test updates." in system_prompt
    assert "Missing integration test scenarios" in system_prompt
    assert '"findings": [' in system_prompt
    assert "Source files changed:" in user_prompt
    assert "Test files changed:" in user_prompt
    assert "Require regression tests for changed validation behavior." in user_prompt

    source_section = user_prompt.split("Source files changed:", maxsplit=1)[1].split(
        "Test files changed:",
        maxsplit=1,
    )[0]
    test_section = user_prompt.split("Test files changed:", maxsplit=1)[1]

    assert "File: reviewers/service.py" in source_section
    assert "File: tests/test_service.py" not in source_section
    assert "File: tests/test_service.py" in test_section


def test_parse_review_response_valid_json_normalizes_findings() -> None:
    reviewer = TestCoverageReviewer()

    findings, summary, error = reviewer._parse_review_response(
        """
        {
          "summary": "Coverage improved, but one assertion remains weak.",
          "findings": [
            {
              "severity": "warning",
              "title": "Missing error assertion details",
              "summary": "The new exception path is not asserted strongly enough.",
              "path": "tests/test_service.py",
              "line": "5",
              "recommendations": [
                "Assert the exception type.",
                "Assert the error message."
              ],
              "rule": "meaningful-assertions"
            }
          ]
        }
        """
    )

    assert error is None
    assert summary == "Coverage improved, but one assertion remains weak."
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].line_start == 5
    assert findings[0].line_end == 5
    assert findings[0].file_path == "tests/test_service.py"
    assert findings[0].recommendation == "Assert the exception type.; Assert the error message."
    assert findings[0].rule_id == "meaningful-assertions"


def test_parse_review_response_handles_malformed_json() -> None:
    reviewer = TestCoverageReviewer()

    findings, summary, error = reviewer._parse_review_response("not-json at all")

    assert findings == []
    assert summary == "Test coverage review could not be parsed."
    assert error == "Malformed JSON response from model."


def test_parse_review_response_handles_empty_response() -> None:
    reviewer = TestCoverageReviewer()

    findings, summary, error = reviewer._parse_review_response("   ")

    assert findings == []
    assert summary == "Test coverage review returned no findings."
    assert error == "Empty response from model."


def test_default_rules_are_applied_when_config_rules_missing() -> None:
    reviewer = TestCoverageReviewer()

    rules = reviewer._resolve_rules(build_config([]))

    assert rules == DEFAULT_RULES


def test_finding_normalization_maps_aliases_and_invalid_lines() -> None:
    reviewer = TestCoverageReviewer()

    finding = reviewer._normalize_finding(
        {
            "severity": "note",
            "summary": "The test name does not explain the scenario.",
            "filename": "tests/test_service.py",
            "line_start": "not-a-number",
            "line_end": 7,
            "suggestion": "Rename the test to mention the blank input case.",
        }
    )

    assert finding is not None
    assert finding.severity == "info"
    assert finding.title == "Test coverage issue"
    assert finding.file_path == "tests/test_service.py"
    assert finding.line_start is None
    assert finding.line_end is None
    assert finding.recommendation == "Rename the test to mention the blank input case."


def test_review_uses_default_rules_and_returns_normalized_result() -> None:
    reviewer = TestCoverageReviewer()
    context = build_context()
    client = StubModelClient(
        """
        ```json
        {
          "findings": [
            {
              "severity": "BLOCKER",
              "title": "Changed validation lacks regression coverage",
              "summary": "The source change adds a new ValueError path, but the test diff does not verify the message.",
              "path": "reviewers/service.py",
              "start_line": 2,
              "end_line": 3,
              "suggestion": "Add a regression test that asserts the exception message for blank inputs."
            }
          ]
        }
        ```
        """
    )

    result = asyncio.run(reviewer.review(context, build_config([]), client))

    assert result.agent == "test_coverage"
    assert result.model == "gpt-4o"
    assert result.error is None
    assert result.summary == "Identified 1 test coverage finding."
    assert result.findings[0].severity == "critical"
    assert result.findings[0].file_path == "reviewers/service.py"
    assert result.findings[0].line_start == 2
    assert result.findings[0].line_end == 3
    assert (
        result.findings[0].recommendation
        == "Add a regression test that asserts the exception message for blank inputs."
    )
    assert client.calls
    assert DEFAULT_RULES[0] in str(client.calls[0]["user_prompt"])
