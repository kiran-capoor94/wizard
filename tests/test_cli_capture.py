import pytest
from typer.testing import CliRunner

from wizard.cli.main import app
from wizard.database import get_session
from wizard.models import WizardSession

runner = CliRunner()


@pytest.fixture()
def open_session():
    with get_session() as db:
        s = WizardSession()
        db.add(s)
        db.flush()
        db.refresh(s)
        return s.id


class TestCaptureClose:
    def test_marks_session_with_explicit_id(self, open_session, tmp_path):
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        result = runner.invoke(app, [
            "capture", "--close",
            "--transcript", str(transcript),
            "--agent", "claude-code",
            "--session-id", str(open_session),
        ])
        assert result.exit_code == 0
        with get_session() as db:
            s = db.get(WizardSession, open_session)
            assert s.transcript_path == str(transcript)
            assert s.agent == "claude-code"
            assert s.closed_by == "hook"

    def test_finds_latest_open_session(self, open_session, tmp_path):
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        result = runner.invoke(app, [
            "capture", "--close",
            "--transcript", str(transcript),
            "--agent", "claude-code",
        ])
        assert result.exit_code == 0
        with get_session() as db:
            s = db.get(WizardSession, open_session)
            assert s.closed_by == "hook"

    def test_no_session_exits_cleanly(self, tmp_path):
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        result = runner.invoke(app, [
            "capture", "--close",
            "--transcript", str(transcript),
            "--agent", "claude-code",
        ])
        assert result.exit_code == 0
