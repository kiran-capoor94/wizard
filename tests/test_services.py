"""Tests for wizard.services.SyncService."""

from unittest.mock import MagicMock, PropertyMock

from wizard.services import SyncService


def test_sync_all_skips_unconfigured_sources():
    """sync_all returns skipped=True for sources whose client is not configured."""
    jira = MagicMock()
    type(jira).is_configured = PropertyMock(return_value=False)

    notion = MagicMock()
    type(notion).is_configured = PropertyMock(return_value=False)

    security = MagicMock()
    db = MagicMock()

    svc = SyncService(jira=jira, notion=notion, security=security)
    results = svc.sync_all(db)

    assert len(results) == 3
    for r in results:
        assert r.skipped is True
        assert r.ok is True
        assert r.error == "not configured"


def test_sync_all_skips_jira_but_syncs_notion():
    """sync_all skips unconfigured Jira but calls configured Notion syncs."""
    jira = MagicMock()
    type(jira).is_configured = PropertyMock(return_value=False)

    notion = MagicMock()
    type(notion).is_configured = PropertyMock(return_value=True)
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = []

    security = MagicMock()
    db = MagicMock()
    db.exec.return_value.first.return_value = None

    svc = SyncService(jira=jira, notion=notion, security=security)
    results = svc.sync_all(db)

    assert len(results) == 3
    # Jira should be skipped
    assert results[0].source == "jira"
    assert results[0].skipped is True
    assert results[0].ok is True
    # Notion sources should have been attempted (ok=True since empty data)
    assert results[1].source == "notion_tasks"
    assert results[1].skipped is False
    assert results[2].source == "notion_meetings"
    assert results[2].skipped is False
