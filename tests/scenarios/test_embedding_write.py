"""Verify embedding background write fires without crashing save_note."""
from unittest.mock import patch

import pytest

from wizard.tools.task_tools import write_embedding


@pytest.mark.asyncio
async def testwrite_embedding_noop_when_model_unavailable():
    """Should silently return when embed() returns None (model not downloaded)."""
    with patch("wizard.tools.task_tools.embed", return_value=None):
        await write_embedding(1, "test content")  # must not raise


@pytest.mark.asyncio
async def testwrite_embedding_noop_on_db_error(caplog):
    """Should log warning but not raise on DB failure."""
    with patch("wizard.tools.task_tools.embed", return_value=[0.1] * 384), \
         patch("wizard.tools.task_tools.engine") as mock_engine:
        mock_engine.connect.side_effect = Exception("db error")
        with caplog.at_level("WARNING", logger="wizard.tools.task_tools"):
            await write_embedding(1, "test content")  # must not raise

    # A regression that swallows the DB failure without logging would make
    # embedding-write outages invisible in production — assert the log call
    # actually fired, not just that no exception escaped.
    assert any(
        "embedding write failed for note 1" in record.message
        for record in caplog.records
    )
