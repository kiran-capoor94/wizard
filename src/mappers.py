import logging

from .models import MeetingCategory, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)

_JIRA_STATUS_MAP: dict[str, TaskStatus] = {
    "to do": TaskStatus.TODO,
    "in progress": TaskStatus.IN_PROGRESS,
    "blocked": TaskStatus.BLOCKED,
    "done": TaskStatus.DONE,
}

_JIRA_PRIORITY_MAP: dict[str, TaskPriority] = {
    "highest": TaskPriority.HIGH,
    "high": TaskPriority.HIGH,
    "medium": TaskPriority.MEDIUM,
    "low": TaskPriority.LOW,
    "lowest": TaskPriority.LOW,
}

_NOTION_STATUS_MAP: dict[str, TaskStatus] = {
    "not started": TaskStatus.TODO,
    "in progress": TaskStatus.IN_PROGRESS,
    "blocked": TaskStatus.BLOCKED,
    "done": TaskStatus.DONE,
    "archive": TaskStatus.ARCHIVED,
}

_NOTION_PRIORITY_MAP: dict[str, TaskPriority] = {
    "high": TaskPriority.HIGH,
    "medium": TaskPriority.MEDIUM,
    "low": TaskPriority.LOW,
}

_LOCAL_TO_JIRA_STATUS: dict[str, str] = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "blocked": "Blocked",
    "done": "Done",
    "archived": "Done",
}

_LOCAL_TO_NOTION_STATUS: dict[str, str] = {
    "todo": "Not started",
    "in_progress": "In progress",
    "blocked": "Blocked",
    "done": "Done",
    "archived": "Archive",
}

_NOTION_MEETING_CATEGORY_MAP: dict[str, MeetingCategory] = {
    "standup": MeetingCategory.STANDUP,
    "planning": MeetingCategory.PLANNING,
    "retro": MeetingCategory.RETRO,
    "presentation": MeetingCategory.GENERAL,
    "customer call": MeetingCategory.GENERAL,
}

_LOCAL_TO_NOTION_MEETING_CATEGORY: dict[str, str | None] = {
    "standup": "Standup",
    "planning": "Planning",
    "retro": "Retro",
    "one_on_one": None,
    "general": None,
}


class StatusMapper:
    @staticmethod
    def jira_to_local(jira_status: str) -> TaskStatus:
        result = _JIRA_STATUS_MAP.get(jira_status.lower())
        if result is None:
            logger.warning("Unknown Jira status '%s', falling back to TODO", jira_status)
            return TaskStatus.TODO
        return result

    @staticmethod
    def notion_to_local(notion_status: str) -> TaskStatus:
        result = _NOTION_STATUS_MAP.get(notion_status.lower())
        if result is None:
            logger.warning("Unknown Notion status '%s', falling back to TODO", notion_status)
            return TaskStatus.TODO
        return result

    @staticmethod
    def local_to_jira(status: TaskStatus) -> str:
        return _LOCAL_TO_JIRA_STATUS[status.value]

    @staticmethod
    def local_to_notion(status: TaskStatus) -> str:
        return _LOCAL_TO_NOTION_STATUS[status.value]


class PriorityMapper:
    @staticmethod
    def jira_to_local(jira_priority: str) -> TaskPriority:
        result = _JIRA_PRIORITY_MAP.get(jira_priority.lower())
        if result is None:
            logger.warning("Unknown Jira priority '%s', falling back to MEDIUM", jira_priority)
            return TaskPriority.MEDIUM
        return result

    @staticmethod
    def notion_to_local(notion_priority: str) -> TaskPriority:
        result = _NOTION_PRIORITY_MAP.get(notion_priority.lower())
        if result is None:
            logger.warning("Unknown Notion priority '%s', falling back to MEDIUM", notion_priority)
            return TaskPriority.MEDIUM
        return result

    @staticmethod
    def local_to_notion(priority: TaskPriority) -> str:
        return priority.value.capitalize()


class MeetingCategoryMapper:
    @staticmethod
    def notion_to_local(notion_category: str) -> MeetingCategory:
        result = _NOTION_MEETING_CATEGORY_MAP.get(notion_category.lower())
        if result is None:
            logger.warning("Unknown Notion meeting category '%s', falling back to GENERAL", notion_category)
            return MeetingCategory.GENERAL
        return result

    @staticmethod
    def local_to_notion(category: MeetingCategory) -> str | None:
        return _LOCAL_TO_NOTION_MEETING_CATEGORY.get(category.value)
