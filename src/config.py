import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

logger = logging.getLogger(__name__)


class JsonConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(
        self,
        field,  # noqa: ARG002
        field_name,
    ) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        config_file = os.environ.get(
            "WIZARD_CONFIG_FILE",
            str(Path.home() / ".wizard" / "config.json"),
        )
        try:
            with open(config_file) as f:
                data = json.load(f)
            logger.info("Loaded config from %s", config_file)
            return data
        except FileNotFoundError:
            logger.info("No config file at %s, using defaults", config_file)
            return {}


class JiraSettings(BaseModel):
    base_url: str = ""
    project_key: str = ""
    token: str = ""
    email: str = ""


class NotionSettings(BaseModel):
    sisu_work_page_id: str = ""
    tasks_db_id: str = ""
    meetings_db_id: str = ""
    token: str = ""


class ScrubbingSettings(BaseModel):
    enabled: bool = True
    allowlist: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    name: str = "wizard"
    version: str = "1.1.0"
    db: str = str(Path.home() / ".wizard" / "wizard.db")
    jira: JiraSettings = Field(default_factory=JiraSettings)
    notion: NotionSettings = Field(default_factory=NotionSettings)
    scrubbing: ScrubbingSettings = Field(default_factory=ScrubbingSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,  # noqa: ARG003
        env_settings,  # noqa: ARG003
        dotenv_settings,  # noqa: ARG003
        file_secret_settings,  # noqa: ARG003
    ):
        return (JsonConfigSettingsSource(settings_cls),)


settings = Settings()
