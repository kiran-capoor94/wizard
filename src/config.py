import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def _config_path() -> Path:
    if override := os.getenv("WIZARD_CONFIG_FILE"):
        return Path(override)
    if os.getenv("WIZARD_ENV", "development") == "production":
        return Path.home() / ".wizard" / "config.json"
    return Path(__file__).parent.parent / "config.json"


class Settings(BaseSettings):
    name: str = Field(default="Wizard MCP Server")
    version: str = Field(default="1.2.0")
    log_level: str = Field(default="INFO")

    db: str = Field(default="wizard.db")

    model_config = SettingsConfigDict(json_file=_config_path())

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (JsonConfigSettingsSource(settings_cls),)


settings = Settings()
