"""Tests for standalone functions and Notion schema types."""




class TestNotionTitle:
    def test_extracts_plain_text(self):
        from wizard.schemas import NotionTitle
        prop = {"title": [{"plain_text": "Test Title"}]}
        assert NotionTitle.model_validate(prop).text == "Test Title"

    def test_returns_none_for_empty(self):
        from wizard.schemas import NotionTitle
        assert NotionTitle.model_validate({"title": []}).text is None

    def test_returns_none_for_missing(self):
        from wizard.schemas import NotionTitle
        assert NotionTitle.model_validate({}).text is None


class TestNotionRichText:
    def test_extracts_plain_text(self):
        from wizard.schemas import NotionRichText
        prop = {"rich_text": [{"plain_text": "Test summary"}]}
        assert NotionRichText.model_validate(prop).text == "Test summary"

    def test_returns_none_for_empty(self):
        from wizard.schemas import NotionRichText
        assert NotionRichText.model_validate({"rich_text": []}).text is None


class TestNotionSelect:
    def test_extracts_name(self):
        from wizard.schemas import NotionSelect
        prop = {"select": {"name": "In Progress"}}
        assert NotionSelect.model_validate(prop).name == "In Progress"

    def test_returns_none_for_null(self):
        from wizard.schemas import NotionSelect
        assert NotionSelect.model_validate({"select": None}).name is None


class TestNotionMultiSelect:
    def test_extracts_names(self):
        from wizard.schemas import NotionMultiSelect
        prop = {"multi_select": [{"name": "Tag1"}, {"name": "Tag2"}]}
        assert NotionMultiSelect.model_validate(prop).names == ["Tag1", "Tag2"]

    def test_returns_empty_for_empty(self):
        from wizard.schemas import NotionMultiSelect
        assert NotionMultiSelect.model_validate({"multi_select": []}).names == []


class TestNotionUrl:
    def test_extracts_url(self):
        from wizard.schemas import NotionUrl
        prop = {"url": "https://example.com"}
        assert NotionUrl.model_validate(prop).url == "https://example.com"

    def test_returns_none_for_null(self):
        from wizard.schemas import NotionUrl
        assert NotionUrl.model_validate({"url": None}).url is None


class TestNotionDate:
    def test_extracts_start(self):
        from wizard.schemas import NotionDate
        prop = {"date": {"start": "2026-04-15"}}
        assert NotionDate.model_validate(prop).start == "2026-04-15"

    def test_returns_none_for_null(self):
        from wizard.schemas import NotionDate
        assert NotionDate.model_validate({"date": None}).start is None


class TestNotionStatus:
    def test_extracts_name(self):
        from wizard.schemas import NotionStatus
        prop = {"status": {"name": "Active"}}
        assert NotionStatus.model_validate(prop).name == "Active"

    def test_returns_none_for_null(self):
        from wizard.schemas import NotionStatus
        assert NotionStatus.model_validate({"status": None}).name is None


class TestIsDailyPageTitle:
    def test_returns_true_for_valid_daily_title(self):
        from wizard.integrations import _is_daily_page_title
        assert _is_daily_page_title("Wednesday 9 April 2025") is True
        assert _is_daily_page_title("Monday 1 January 2024") is True
        assert _is_daily_page_title("Friday 15 April 2026") is True

    def test_returns_false_for_non_daily_titles(self):
        from wizard.integrations import _is_daily_page_title
        assert _is_daily_page_title("SISU IQ Design") is False
        assert _is_daily_page_title("") is False
        assert _is_daily_page_title("2024-01-01") is False
        assert _is_daily_page_title("Meeting Notes") is False
        assert _is_daily_page_title("9 April 2025") is False  # missing weekday


def test_extract_jira_key_from_url():
    """_extract_jira_key should extract issue key from Jira URL"""
    from wizard.integrations import _extract_jira_key

    assert _extract_jira_key("https://org.atlassian.net/browse/ENG-123") == "ENG-123"
    assert _extract_jira_key("https://jira.company.com/browse/PROJ-456") == "PROJ-456"
    assert _extract_jira_key(None) is None
    assert _extract_jira_key("") is None
    assert _extract_jira_key("not-a-url") is None


def test_extract_krisp_id_from_url():
    """_extract_krisp_id should extract last path segment from Krisp URL"""
    from wizard.integrations import extract_krisp_id

    assert extract_krisp_id("https://krisp.ai/m/abc123") == "abc123"
    assert extract_krisp_id("https://krisp.ai/m/abc123/") == "abc123"
    assert extract_krisp_id("https://krisp.ai/m/abc123?foo=bar") == "abc123"
    assert extract_krisp_id(None) is None
    assert extract_krisp_id("") is None
