import logging

from src.mappers import StatusMapper, PriorityMapper, MeetingCategoryMapper
from src.models import TaskStatus, TaskPriority, MeetingCategory


class TestStatusMapperJiraToLocal:
    def test_known_statuses(self):
        assert StatusMapper.jira_to_local("to do") == TaskStatus.TODO
        assert StatusMapper.jira_to_local("in progress") == TaskStatus.IN_PROGRESS
        assert StatusMapper.jira_to_local("blocked") == TaskStatus.BLOCKED
        assert StatusMapper.jira_to_local("done") == TaskStatus.DONE

    def test_case_insensitive(self):
        assert StatusMapper.jira_to_local("To Do") == TaskStatus.TODO
        assert StatusMapper.jira_to_local("IN PROGRESS") == TaskStatus.IN_PROGRESS

    def test_unknown_falls_back_to_todo(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = StatusMapper.jira_to_local("unknown-status")
        assert result == TaskStatus.TODO
        assert "unknown-status" in caplog.text


class TestStatusMapperNotionToLocal:
    def test_known_statuses(self):
        assert StatusMapper.notion_to_local("not started") == TaskStatus.TODO
        assert StatusMapper.notion_to_local("in progress") == TaskStatus.IN_PROGRESS
        assert StatusMapper.notion_to_local("blocked") == TaskStatus.BLOCKED
        assert StatusMapper.notion_to_local("done") == TaskStatus.DONE
        assert StatusMapper.notion_to_local("archive") == TaskStatus.ARCHIVED

    def test_case_insensitive(self):
        assert StatusMapper.notion_to_local("Not Started") == TaskStatus.TODO

    def test_unknown_falls_back_to_todo(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = StatusMapper.notion_to_local("unknown")
        assert result == TaskStatus.TODO
        assert "unknown" in caplog.text


class TestStatusMapperLocalToExternal:
    def test_local_to_jira(self):
        assert StatusMapper.local_to_jira(TaskStatus.TODO) == "To Do"
        assert StatusMapper.local_to_jira(TaskStatus.IN_PROGRESS) == "In Progress"
        assert StatusMapper.local_to_jira(TaskStatus.BLOCKED) == "Blocked"
        assert StatusMapper.local_to_jira(TaskStatus.DONE) == "Done"
        assert StatusMapper.local_to_jira(TaskStatus.ARCHIVED) == "Done"

    def test_local_to_notion(self):
        assert StatusMapper.local_to_notion(TaskStatus.TODO) == "Not started"
        assert StatusMapper.local_to_notion(TaskStatus.IN_PROGRESS) == "In progress"
        assert StatusMapper.local_to_notion(TaskStatus.BLOCKED) == "Blocked"
        assert StatusMapper.local_to_notion(TaskStatus.DONE) == "Done"
        assert StatusMapper.local_to_notion(TaskStatus.ARCHIVED) == "Archive"


class TestPriorityMapperJiraToLocal:
    def test_known_priorities(self):
        assert PriorityMapper.jira_to_local("highest") == TaskPriority.HIGH
        assert PriorityMapper.jira_to_local("high") == TaskPriority.HIGH
        assert PriorityMapper.jira_to_local("medium") == TaskPriority.MEDIUM
        assert PriorityMapper.jira_to_local("low") == TaskPriority.LOW
        assert PriorityMapper.jira_to_local("lowest") == TaskPriority.LOW

    def test_case_insensitive(self):
        assert PriorityMapper.jira_to_local("HIGH") == TaskPriority.HIGH

    def test_unknown_falls_back_to_medium(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = PriorityMapper.jira_to_local("critical")
        assert result == TaskPriority.MEDIUM
        assert "critical" in caplog.text


class TestPriorityMapperNotionToLocal:
    def test_known_priorities(self):
        assert PriorityMapper.notion_to_local("high") == TaskPriority.HIGH
        assert PriorityMapper.notion_to_local("medium") == TaskPriority.MEDIUM
        assert PriorityMapper.notion_to_local("low") == TaskPriority.LOW

    def test_case_insensitive(self):
        assert PriorityMapper.notion_to_local("High") == TaskPriority.HIGH

    def test_unknown_falls_back_to_medium(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = PriorityMapper.notion_to_local("urgent")
        assert result == TaskPriority.MEDIUM
        assert "urgent" in caplog.text


class TestPriorityMapperLocalToNotion:
    def test_all_priorities(self):
        assert PriorityMapper.local_to_notion(TaskPriority.HIGH) == "High"
        assert PriorityMapper.local_to_notion(TaskPriority.MEDIUM) == "Medium"
        assert PriorityMapper.local_to_notion(TaskPriority.LOW) == "Low"


class TestMeetingCategoryMapperNotionToLocal:
    def test_known_categories(self):
        assert MeetingCategoryMapper.notion_to_local("standup") == MeetingCategory.STANDUP
        assert MeetingCategoryMapper.notion_to_local("planning") == MeetingCategory.PLANNING
        assert MeetingCategoryMapper.notion_to_local("retro") == MeetingCategory.RETRO

    def test_known_general_mappings(self):
        assert MeetingCategoryMapper.notion_to_local("presentation") == MeetingCategory.GENERAL
        assert MeetingCategoryMapper.notion_to_local("customer call") == MeetingCategory.GENERAL

    def test_case_insensitive(self):
        assert MeetingCategoryMapper.notion_to_local("Standup") == MeetingCategory.STANDUP

    def test_unknown_falls_back_to_general(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = MeetingCategoryMapper.notion_to_local("xyz-unknown")
        assert result == MeetingCategory.GENERAL
        assert "xyz-unknown" in caplog.text


class TestMeetingCategoryMapperLocalToNotion:
    def test_mappable_categories(self):
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.STANDUP) == "Standup"
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.PLANNING) == "Planning"
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.RETRO) == "Retro"

    def test_unmappable_returns_none(self):
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.ONE_ON_ONE) is None
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.GENERAL) is None
