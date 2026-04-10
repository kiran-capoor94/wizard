import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class JsonConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field, field_name):
        pass

    def __call__(self) -> dict[str, Any]:
        config_file = os.environ.get(
            "WIZARD_CONFIG_FILE",
            str(Path.home() / ".wizard" / "config.json"),
        )
        try:
            with open(config_file) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}


class JiraSettings(BaseModel):
    base_url: str = ""
    project_key: str = ""
    token: str = ""


class NotionSettings(BaseModel):
    daily_page_id: str = ""
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
    def settings_customise_sources(cls, settings_cls, **kwargs):
        return (JsonConfigSettingsSource(settings_cls),)


settings = Settings()
