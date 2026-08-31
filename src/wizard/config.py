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
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Could not read config at %s (%s), using defaults", config_file, e
            )
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


class BackendConfig(BaseModel):
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    provider: str = ""  # informational only; routing is via model prefix
    description: str = ""  # human-readable label shown in logs


class SynthesisSettings(BaseModel):
    provider: str = ""  # deprecated; kept so existing configs don't error on load
    model: str = "ollama/gemma4:latest-64k"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    enabled: bool = True
    # Maximum characters to send per chunk when the model's context is exceeded.
    # Increase this to match larger local servers (e.g. Unsloth/Unsloth configured for 262144).
    context_chars: int = 200000
    # Ordered list of backends; first healthy one wins.
    # See wizard configure synthesis for interactive management.
    backends: list[BackendConfig] = Field(default_factory=list)

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


class GraphitiSettings(BaseModel):
    """Shared Graphiti graph service — Wizard talks to it over HTTP only (no
    graphiti-core dependency). Pinned server version, agreed with KiranOS:
    graphiti-core==0.22.0, image
    zepai/graphiti@sha256:76d14f30afc65d2f914637d67d0c0631a7e779e2740be1ae99b9dc0c5876d2da
    (+ neo4j 5.26.2). Both sides run this exact digest; bumps are agreed jointly.
    The service must set OPENAI_BASE_URL to a local embedder or scrubbed content
    leaves the machine (Graphiti's embedder is a separate client from the LLM)."""

    enabled: bool = False
    url: str = "http://localhost:8000"
    group_id: str = "wizard"
    timeout_seconds: float = 2.0
    health_ttl_seconds: float = 30.0
    write_timeout_seconds: float = 30.0  # /messages does per-episode LLM extraction
    backfill_batch_size: int = 25  # episodes per batch before pausing
    backfill_pause_seconds: float = 5.0  # sleep between batches so the serial worker drains


class SentrySettings(BaseModel):
    dsn: str = ""
    enabled: bool = False
    traces_sample_rate: float = 0.1
    profiles_sample_rate: float = 0.1


class ModesSettings(BaseModel):
    default: str | None = "caveman"
    allowed: list[str] = Field(
        default_factory=lambda: ["architect", "ideation", "product-owner", "caveman"]
    )


class WizardPaths(BaseModel):
    model_config = {"frozen": True}

    installed_skills: Path = Field(
        default_factory=lambda: Path.home() / ".wizard" / "skills"
    )
    package_skills: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent / "skills"
    )
    sessions_dir: Path = Field(
        default_factory=lambda: Path.home() / ".wizard" / "sessions"
    )


WIZARD_MODES: list[str] = ["architect", "ideation", "product-owner", "caveman"]


class Settings(BaseSettings):
    model_config = {"extra": "ignore"}

    name: str = "wizard"
    version: str = "2.2.3"
    db: str = str(Path.home() / ".wizard" / "wizard.db")
    scrubbing: ScrubbingSettings = Field(default_factory=ScrubbingSettings)
    knowledge_store: KnowledgeStoreSettings = Field(
        default_factory=KnowledgeStoreSettings
    )
    synthesis: SynthesisSettings = Field(default_factory=SynthesisSettings)
    graphiti: GraphitiSettings = Field(default_factory=GraphitiSettings)
    sentry: SentrySettings = Field(default_factory=SentrySettings)
    modes: ModesSettings = Field(default_factory=ModesSettings)
    paths: WizardPaths = Field(default_factory=WizardPaths)

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
