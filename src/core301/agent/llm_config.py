"""Shared existing OpenAI-compatible configuration; never repr/log credentials."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv


class LLMConfigurationError(ValueError):
    pass


@dataclass(repr=False, frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str


def load_llm_config(project_root):
    load_dotenv(project_root / ".env", override=False)
    names = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL")
    config = {name: os.environ.get(name, "") for name in names}
    missing = [name for name, value in config.items() if not value.strip()]
    if missing:
        raise LLMConfigurationError("Missing API configuration: " + ", ".join(missing))
    return LLMConfig(*(config[name] for name in names))
