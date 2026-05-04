"""Verify embedding background write fires without crashing save_note."""
from unittest.mock import patch

import pytest

from wizard.tools.task_tools import _write_embedding


@pytest.mark.asyncio
async def test_write_embedding_noop_when_model_unavailable():
    """Should silently return when embed() returns None (model not downloaded)."""
    with patch("wizard.tools.task_tools.embed", return_value=None):
        await _write_embedding(1, "test content")  # must not raise


@pytest.mark.asyncio
async def test_write_embedding_noop_on_db_error():
    """Should log warning but not raise on DB failure."""
    with patch("wizard.tools.task_tools.embed", return_value=[0.1] * 384), \
         patch("wizard.tools.task_tools.engine") as mock_engine:
        mock_engine.connect.side_effect = Exception("db error")
        await _write_embedding(1, "test content")  # must not raise
