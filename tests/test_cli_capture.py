"""Tests for the `wizard capture --close` CLI command."""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine
from typer.testing import CliRunner

from wizard.cli.main import app
from wizard.models import WizardSession

runner = CliRunner()


@pytest.fixture(scope="module")
def capture_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@contextmanager
def _session_for(engine):
    with Session(engine) as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


@pytest.fixture()
def open_session(capture_engine):
    with _session_for(capture_engine) as db:
        s = WizardSession()
        db.add(s)
        db.flush()
        db.refresh(s)
        return s.id


class TestCaptureClose:
    def test_marks_session_with_explicit_id(self, open_session, capture_engine, tmp_path):
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")

        def fake_get_session():
            return _session_for(capture_engine)

        with patch("wizard.cli.main.get_db_session", fake_get_session), \
             patch("wizard.cli.main.settings") as mock_settings:
            mock_settings.synthesis.enabled = False
            mock_settings.scrubbing.allowlist = []
            mock_settings.scrubbing.enabled = True
            result = runner.invoke(app, [
                "capture", "--close",
                "--transcript", str(transcript),
                "--agent", "claude-code",
                "--session-id", str(open_session),
            ])

        assert result.exit_code == 0, result.output
        with _session_for(capture_engine) as db:
            s = db.get(WizardSession, open_session)
            assert s.transcript_path == str(transcript)
            assert s.agent == "claude-code"
            assert s.closed_by == "hook"

    def test_finds_latest_unsynthesised_session(self, open_session, capture_engine, tmp_path):
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")

        def fake_get_session():
            return _session_for(capture_engine)

        with patch("wizard.cli.main.get_db_session", fake_get_session), \
             patch("wizard.cli.main.settings") as mock_settings:
            mock_settings.synthesis.enabled = False
            mock_settings.scrubbing.allowlist = []
            mock_settings.scrubbing.enabled = True
            result = runner.invoke(app, [
                "capture", "--close",
                "--transcript", str(transcript),
                "--agent", "claude-code",
            ])

        assert result.exit_code == 0, result.output
        with _session_for(capture_engine) as db:
            s = db.get(WizardSession, open_session)
            assert s.closed_by == "hook"

    def test_no_session_exits_cleanly(self, capture_engine, tmp_path):
        """No unsynthesised session within 24h -- exits 0 with a message."""
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")

        # Mark all sessions as synthesised so none match
        with _session_for(capture_engine) as db:
            from sqlmodel import select
            for s in db.exec(select(WizardSession)).all():
                s.is_synthesised = True
                db.add(s)

        def fake_get_session():
            return _session_for(capture_engine)

        with patch("wizard.cli.main.get_db_session", fake_get_session), \
             patch("wizard.cli.main.settings") as mock_settings:
            mock_settings.synthesis.enabled = False
            result = runner.invoke(app, [
                "capture", "--close",
                "--transcript", str(transcript),
                "--agent", "claude-code",
            ])

        assert result.exit_code == 0
        assert "No unsynthesised" in result.output

    def test_preserves_user_closed_by(self, capture_engine, tmp_path):
        """closed_by='user' must not be overwritten to 'hook'."""
        with _session_for(capture_engine) as db:
            s = WizardSession(closed_by="user")
            db.add(s)
            db.flush()
            db.refresh(s)
            sid = s.id

        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")

        def fake_get_session():
            return _session_for(capture_engine)

        with patch("wizard.cli.main.get_db_session", fake_get_session), \
             patch("wizard.cli.main.settings") as mock_settings:
            mock_settings.synthesis.enabled = False
            mock_settings.scrubbing.allowlist = []
            mock_settings.scrubbing.enabled = True
            runner.invoke(app, [
                "capture", "--close",
                "--transcript", str(transcript),
                "--agent", "claude-code",
                "--session-id", str(sid),
            ])

        with _session_for(capture_engine) as db:
            s = db.get(WizardSession, sid)
            assert s.closed_by == "user"
