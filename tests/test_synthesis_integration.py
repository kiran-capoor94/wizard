import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from wizard.database import get_session
from wizard.models import WizardSession
from wizard.repositories import NoteRepository
from wizard.security import SecurityService
from wizard.transcript import CaptureSynthesiser, TranscriptReader

TRANSCRIPT_CONTENT = [
    {
        "type": "user",
        "message": {"role": "user", "content": "Fix the login bug in auth.py"},
        "timestamp": "2026-04-18T10:00:00.000Z",
    },
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I found the issue."},
                {"type": "tool_use", "id": "t1", "name": "Edit",
                 "input": {"file_path": "auth.py"}},
            ],
        },
        "timestamp": "2026-04-18T10:00:01.000Z",
    },
    {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1",
                         "content": "OK", "is_error": False}],
        },
        "timestamp": "2026-04-18T10:00:02.000Z",
    },
]


@pytest.fixture()
def transcript_file(tmp_path: Path) -> Path:
    p = tmp_path / "transcript.jsonl"
    with p.open("w") as f:
        for entry in TRANSCRIPT_CONTENT:
            f.write(json.dumps(entry) + "\n")
    return p


class TestSynthesisIntegration:
    @pytest.mark.asyncio
    async def test_synthetic_fallback_when_sampling_fails(self, transcript_file):
        synth = CaptureSynthesiser(
            reader=TranscriptReader(),
            note_repo=NoteRepository(),
            security=SecurityService(),
        )
        with get_session() as db:
            session = WizardSession(
                transcript_path=str(transcript_file), agent="claude-code",
            )
            db.add(session)
            db.flush()
            db.refresh(session)

            ctx = AsyncMock()
            ctx.sample.side_effect = Exception("No LLM")

            result = await synth.synthesise(db, ctx, session)
            assert result.synthesised_via == "synthetic"
            assert result.notes_created == 1

    @pytest.mark.asyncio
    async def test_no_transcript_returns_fallback(self):
        synth = CaptureSynthesiser(
            reader=TranscriptReader(),
            note_repo=NoteRepository(),
            security=SecurityService(),
        )
        with get_session() as db:
            session = WizardSession()
            db.add(session)
            db.flush()
            db.refresh(session)

            ctx = AsyncMock()
            result = await synth.synthesise(db, ctx, session)
            assert result.synthesised_via == "fallback"
            assert result.notes_created == 0
