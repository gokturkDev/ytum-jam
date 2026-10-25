from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    llm_backend: Literal["fake", "openai"] = "fake"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    provider_concurrency: int = Field(default=3, ge=1, le=10)
    personas_file: str = ""
    objections_min: int = Field(default=1, ge=1, le=3)
    objections_max: int = Field(default=1, ge=1, le=3)
    starting_support: int | None = Field(default=None, ge=0, le=100)
    target_support: int | None = Field(default=None, ge=1, le=100)
    max_rounds: int | None = Field(default=None, ge=1, le=10)
    provider_timeout_seconds: float = Field(default=30, gt=0)
    turn_timeout_seconds: float = Field(default=75, gt=0)
    generation_timeout_seconds: float = Field(default=75, gt=0)
    max_output_tokens: int = Field(default=1200, ge=256)
    server_host: str = "127.0.0.1"
    server_port: int = Field(default=8000, ge=1, le=65535)
    client_base_url: str = "http://127.0.0.1:8000"
    client_timeout_seconds: float = Field(default=90, gt=0)
    transcript_dir: str = ""

    @model_validator(mode="after")
    def configured(self) -> "Settings":
        if self.llm_backend == "openai" and (
            not self.openai_api_key.get_secret_value().strip() or not self.openai_model.strip()
        ):
            raise ValueError("OpenAI mode requires OPENAI_API_KEY and explicit OPENAI_MODEL")
        if self.objections_min > self.objections_max:
            raise ValueError("OBJECTIONS_MIN cannot exceed OBJECTIONS_MAX")
        return self
