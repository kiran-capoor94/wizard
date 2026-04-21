import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

logger = logging.getLogger(__name__)


class JsonConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(
        self, field, field_name
    ) -> tuple[Any, str, bool]:  # noqa: ARG002
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


class ScrubbingSettings(BaseModel):
    enabled: bool = True
    allowlist: list[str] = Field(default_factory=list)


class NotionKSSettings(BaseModel):
    daily_parent_id: str = ""
    tasks_db_id: str = ""
    meetings_db_id: str = ""


class ObsidianKSSettings(BaseModel):
    vault_path: str = ""
    daily_notes_folder: str = "Daily"
    tasks_folder: str = "Tasks"


class KnowledgeStoreSettings(BaseModel):
    type: str = ""  # "notion" | "obsidian" | ""
    notion: NotionKSSettings = Field(default_factory=NotionKSSettings)
    obsidian: ObsidianKSSettings = Field(default_factory=ObsidianKSSettings)


class SynthesisSettings(BaseModel):
    provider: str = ""  # deprecated; kept so existing configs don't error on load
    model: str = "ollama/gemma4:latest-64k"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def migrate_provider(cls, data: object) -> object:
        if isinstance(data, dict):
            provider = data.get("provider", "")
            model = data.get("model", "")
            if provider and model and "/" not in str(model):
                data["model"] = f"{provider}/{model}"
            elif model and "/" not in str(model):
                logger.warning(
                    "SynthesisSettings: model %r has no provider prefix "
                    "(expected '<provider>/<model>', e.g. 'ollama/gemma4:latest-64k'). "
                    "LiteLLM may route incorrectly.",
                    model,
                )
        return data


class Settings(BaseSettings):
    model_config = {"extra": "ignore"}

    name: str = "wizard"
    version: str = "2.2.0"
    db: str = str(Path.home() / ".wizard" / "wizard.db")
    scrubbing: ScrubbingSettings = Field(default_factory=ScrubbingSettings)
    knowledge_store: KnowledgeStoreSettings = Field(
        default_factory=KnowledgeStoreSettings
    )
    synthesis: SynthesisSettings = Field(default_factory=SynthesisSettings)

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
