"""Scenario: wizard verify confirms a healthy installation."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from wizard.cli.main import app

FAKE_MCP_STDOUT = (
    json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "wizard", "version": "1.0"},
        },
    })
    + "\n"
    + json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "tools": [
                {"name": "session_start", "description": "Start a session"},
                {"name": "session_end", "description": "End a session"},
            ]
        },
    })
    + "\n"
)


def test_verify_exits_zero_on_healthy_installation():
    mock_proc = MagicMock()
    mock_proc.stdout = FAKE_MCP_STDOUT.encode()
    mock_proc.returncode = 0

    with (
        patch("wizard.cli.verify.check_config_file", return_value=(True, "Config found")),
        patch("wizard.cli.verify.check_db_file", return_value=(True, "DB found")),
        patch("wizard.cli.verify.check_db_tables", return_value=(True, "Tables OK")),
        patch("wizard.cli.verify.check_skills_installed", return_value=(True, "Skills OK")),
        patch("wizard.cli.verify.subprocess.run", return_value=mock_proc),
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["verify"])

    assert result.exit_code == 0, result.output
    assert "All checks passed" in result.output
    assert "2 tools registered" in result.output
