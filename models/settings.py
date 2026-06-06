"""Type-safe .env loader — import `settings` everywhere, never instantiate Settings() again."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required — all four must be present or startup fails immediately
    ocean_api_key: SecretStr
    prospeo_api_key: SecretStr
    eazyreach_api_key: SecretStr
    brevo_api_key: SecretStr

    # Sender identity — must match a verified sender domain in Brevo
    sender_email: str
    sender_name: str

    # Optional tuning with safe defaults
    ocean_max_results: int = 10
    prospeo_seniority_filter: str = "c_suite,vp"
    request_timeout_seconds: int = 30
    max_retry_attempts: int = 3
    retry_backoff_factor: float = 2.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def seniority_list(self) -> list[str]:
        return [s.strip() for s in self.prospeo_seniority_filter.split(",")]


# Singleton — import this everywhere, never instantiate Settings() again
settings = Settings()
