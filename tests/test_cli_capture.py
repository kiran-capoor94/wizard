"""Tests for the `wizard capture --close` CLI command."""

import datetime
import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from typer.testing import CliRunner

from wizard.cli.main import app
from wizard.models import WizardSession
from wizard.schemas import SynthesisResult

runner = CliRunner()


@pytest.fixture()
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


class TestCollectTranscripts:
    def test_returns_empty_when_no_transcript_path(self, capture_engine):
        from wizard.cli.main import _collect_transcripts
        with _session_for(capture_engine) as db:
            s = WizardSession()  # no transcript_path
            db.add(s)
            db.flush()
            db.refresh(s)
            result = _collect_transcripts(s)
        assert result == []

    def test_returns_only_main_when_no_siblings(self, tmp_path, capture_engine):
        from wizard.cli.main import _collect_transcripts
        transcript = tmp_path / "main.jsonl"
        transcript.write_text("{}\n")
        with _session_for(capture_engine) as db:
            s = WizardSession(transcript_path=str(transcript))
            db.add(s)
            db.flush()
            db.refresh(s)
            result = _collect_transcripts(s)
        assert result == [transcript]

    def test_includes_siblings_created_after_session(self, tmp_path, capture_engine):
        from wizard.cli.main import _collect_transcripts

        transcript = tmp_path / "main.jsonl"
        transcript.write_text("{}\n")
        sibling = tmp_path / "sub-agent.jsonl"
        sibling.write_text("{}\n")

        with _session_for(capture_engine) as db:
            # Session created 5 seconds ago, sibling has current mtime
            s = WizardSession(
                transcript_path=str(transcript),
                created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5),
            )
            db.add(s)
            db.flush()
            db.refresh(s)
            result = _collect_transcripts(s)

        assert transcript in result
        assert sibling in result

    def test_excludes_siblings_created_before_session(self, tmp_path, capture_engine):
        from wizard.cli.main import _collect_transcripts

        old_sibling = tmp_path / "old.jsonl"
        old_sibling.write_text("{}\n")
        # Force old_sibling mtime to epoch
        os.utime(str(old_sibling), (0, 0))

        transcript = tmp_path / "main.jsonl"
        transcript.write_text("{}\n")

        with _session_for(capture_engine) as db:
            s = WizardSession(
                transcript_path=str(transcript),
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
            db.add(s)
            db.flush()
            db.refresh(s)
            result = _collect_transcripts(s)

        assert transcript in result
        assert old_sibling not in result


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

    def test_stores_agent_session_id_when_not_already_set(self, open_session, capture_engine, tmp_path):
        """--agent-session-id is stored on session when not already set."""
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
                "--agent-session-id", "test-uuid-1234",
            ])

        assert result.exit_code == 0, result.output
        with _session_for(capture_engine) as db:
            s = db.get(WizardSession, open_session)
            assert s.agent_session_id == "test-uuid-1234"

    def test_does_not_overwrite_existing_agent_session_id(self, capture_engine, tmp_path):
        """--agent-session-id does not overwrite a value already set by session_start."""
        with _session_for(capture_engine) as db:
            s = WizardSession(agent_session_id="original-uuid")
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
                "--agent-session-id", "new-uuid-should-not-overwrite",
            ])

        with _session_for(capture_engine) as db:
            s = db.get(WizardSession, sid)
            assert s.agent_session_id == "original-uuid"

    def test_synthesises_via_collect_transcripts(self, open_session, capture_engine, tmp_path):
        """capture calls synthesise_path once per path from _collect_transcripts."""
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        fake_result = SynthesisResult(notes_created=1, task_ids_touched=[], synthesised_via="ollama")

        def fake_get_session():
            return _session_for(capture_engine)

        with patch("wizard.cli.main.get_db_session", fake_get_session), \
             patch("wizard.cli.main.settings") as mock_settings, \
             patch("wizard.cli.main._collect_transcripts", return_value=[transcript]) as mock_collect, \
             patch("wizard.cli.main.OllamaSynthesiser.synthesise_path", return_value=fake_result) as mock_sp:
            mock_settings.synthesis.enabled = True
            mock_settings.synthesis.base_url = "http://localhost:11434"
            mock_settings.synthesis.model = "gemma4:latest-64k"
            mock_settings.scrubbing.allowlist = []
            mock_settings.scrubbing.enabled = True
            result = runner.invoke(app, [
                "capture", "--close",
                "--transcript", str(transcript),
                "--agent", "claude-code",
                "--session-id", str(open_session),
            ])

        assert result.exit_code == 0, result.output
        mock_collect.assert_called_once()
        mock_sp.assert_called_once()
