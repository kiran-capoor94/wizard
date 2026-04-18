from unittest.mock import MagicMock, patch

import httpx
from notion_client.errors import APIResponseError

from wizard.cli.doctor import _check_notion_token


class TestCheckNotionToken:
    def test_empty_token_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings:
            MockSettings.return_value.notion.token.get_secret_value.return_value = ""
            passed, message = _check_notion_token()
            assert not passed
            assert "not set" in message

    def test_valid_token_passes(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.NotionSdkClient") as MockClient:
            MockSettings.return_value.notion.token.get_secret_value.return_value = "ntn_test"
            MockClient.return_value.users.me.return_value = {"id": "u1"}
            passed, message = _check_notion_token()
            assert passed
            assert "valid" in message

    def test_invalid_token_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.NotionSdkClient") as MockClient:
            MockSettings.return_value.notion.token.get_secret_value.return_value = "ntn_bad"
            MockClient.return_value.users.me.side_effect = APIResponseError(
                code="unauthorized",
                status=401,
                message="API token is invalid.",
                headers=MagicMock(),
                raw_body_text="",
            )
            passed, message = _check_notion_token()
            assert not passed
            assert "invalid" in message

    def test_network_error_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.NotionSdkClient") as MockClient:
            MockSettings.return_value.notion.token.get_secret_value.return_value = "ntn_test"
            MockClient.return_value.users.me.side_effect = httpx.ConnectError("timeout")
            passed, message = _check_notion_token()
            assert not passed
            assert "network" in message.lower() or "reach" in message.lower()
