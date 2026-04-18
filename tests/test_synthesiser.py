from wizard.repositories import NoteRepository
from wizard.security import SecurityService
from wizard.transcript import CaptureSynthesiser, TranscriptEntry, TranscriptReader


def _make_entries() -> list[TranscriptEntry]:
    return [
        TranscriptEntry(role="user", content="Fix the login bug"),
        TranscriptEntry(role="tool_call", content='{"file_path":"src/auth.py"}', tool_name="Read"),
        TranscriptEntry(role="tool_result", content="def login(): ..."),
        TranscriptEntry(role="assistant", content="Found the issue in the login function."),
        TranscriptEntry(role="tool_call", content='{"file_path":"src/auth.py"}', tool_name="Edit"),
        TranscriptEntry(role="tool_result", content="File updated"),
        TranscriptEntry(role="assistant", content="Fixed the login bug by correcting token validation."),
    ]


def _make_synth() -> CaptureSynthesiser:
    return CaptureSynthesiser(
        reader=TranscriptReader(),
        note_repo=NoteRepository(),
        security=SecurityService(),
    )


class TestBuildSynthesisPrompt:
    def test_includes_entries(self):
        synth = _make_synth()
        prompt = synth._build_synthesis_prompt(_make_entries(), tasks=[])
        assert "Fix the login bug" in prompt
        assert "Read" in prompt
        assert "Edit" in prompt

    def test_includes_task_list(self):
        synth = _make_synth()

        class FakeTask:
            id = 8
            name = "Fix login bug"

        prompt = synth._build_synthesis_prompt(_make_entries(), tasks=[FakeTask()])
        assert "8" in prompt
        assert "Fix login bug" in prompt


class TestChunkEntries:
    def test_single_chunk(self):
        synth = _make_synth()
        entries = _make_entries()
        chunks = synth._chunk_entries(entries, max_chars=100_000)
        assert len(chunks) == 1
        assert chunks[0] == entries

    def test_splits_large_transcript(self):
        synth = _make_synth()
        entries = [TranscriptEntry(role="user", content="x" * 1000) for _ in range(10)]
        chunks = synth._chunk_entries(entries, max_chars=3000)
        assert len(chunks) > 1
        assert sum(len(c) for c in chunks) == 10


class TestSyntheticFallback:
    def test_produces_summary(self):
        synth = _make_synth()
        summary, via = synth._synthetic_summary(_make_entries())
        assert "7 transcript entries" in summary
        assert "Edit" in summary
        assert "Read" in summary
        assert via == "synthetic"
