from unittest.mock import MagicMock, patch

import httpx
from notion_client.errors import APIResponseError

from wizard.cli.doctor import _check_jira_token, _check_notion_token


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


class TestCheckJiraToken:
    def test_empty_token_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = ""
            s.jira.base_url = ""
            s.jira.email = ""
            passed, message = _check_jira_token()
            assert not passed
            assert "not set" in message

    def test_valid_token_passes(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.httpx") as mock_httpx:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = "jira_token"
            s.jira.base_url = "https://test.atlassian.net"
            s.jira.email = "user@example.com"
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status.return_value = None
            mock_httpx.get.return_value = mock_response
            passed, message = _check_jira_token()
            assert passed
            assert "valid" in message

    def test_invalid_token_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.httpx") as mock_httpx:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = "bad_token"
            s.jira.base_url = "https://test.atlassian.net"
            s.jira.email = "user@example.com"
            response = MagicMock()
            response.status_code = 401
            mock_httpx.get.return_value = response
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401", request=MagicMock(), response=response,
            )
            passed, message = _check_jira_token()
            assert not passed
            assert "invalid" in message

    def test_network_error_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.httpx") as mock_httpx:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = "jira_token"
            s.jira.base_url = "https://test.atlassian.net"
            s.jira.email = "user@example.com"
            mock_httpx.get.side_effect = httpx.ConnectError("timeout")
            passed, message = _check_jira_token()
            assert not passed
            assert "network" in message.lower() or "reach" in message.lower()

    def test_missing_base_url_skips_api_call(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = "jira_token"
            s.jira.base_url = ""
            s.jira.email = "user@example.com"
            passed, message = _check_jira_token()
            assert not passed
            assert "not set" in message or "not configured" in message
