"""Scenario: session_end surfaces a skill_candidate when working_set is non-empty."""

from unittest.mock import AsyncMock, patch


class TestSessionEndSkillCandidate:
    async def test_skill_candidate_returned_when_working_set_nonempty(
        self, mcp_client, seed_task
    ):
        task = await seed_task(name="Skill candidate task")

        r = await mcp_client.call_tool("session_start", {})
        assert not r.is_error, r
        session_id = r.structured_content["session_id"]

        candidate_text = (
            "Systematic root-cause isolation via bisect. "
            "Apply when a regression has no obvious owner. "
            "Steps: narrow range, add tracing, confirm fix."
        )

        with patch(
            "wizard.tools.session_tools._detect_skill_candidate",
            new=AsyncMock(return_value=candidate_text),
        ):
            r = await mcp_client.call_tool("session_end", {
                "session_id": session_id,
                "summary": "Fixed the OAuth bug",
                "intent": "Bug fix",
                "working_set": [task.id],
                "state_delta": "Identified and fixed root cause",
                "open_loops": [],
                "next_actions": ["Deploy to staging"],
                "closure_status": "clean",
            })

        assert not r.is_error, r
        assert r.structured_content["skill_candidate"] == candidate_text

    async def test_skill_candidate_none_when_working_set_empty(self, mcp_client):
        r = await mcp_client.call_tool("session_start", {})
        assert not r.is_error, r
        session_id = r.structured_content["session_id"]

        with patch(
            "wizard.tools.session_tools._detect_skill_candidate",
            new=AsyncMock(side_effect=AssertionError("must not be called for empty working_set")),
        ):
            r = await mcp_client.call_tool("session_end", {
                "session_id": session_id,
                "summary": "Nothing done",
                "intent": "Idle",
                "working_set": [],
                "state_delta": "No change",
                "open_loops": [],
                "next_actions": [],
                "closure_status": "clean",
            })

        assert not r.is_error, r
        assert r.structured_content["skill_candidate"] is None
