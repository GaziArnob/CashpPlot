from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SME Finance Assistant"
    database_url: str = "sqlite:///./finance.db"
    secret_key: str = "change-me-in-production"
    field_encryption_key: str = ""  # Fernet key; derived from secret_key when empty
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False  # set True behind HTTPS
    cors_origins: str = "http://localhost:3000"

    # Free LLM providers, tried in this order. Unconfigured ones are skipped.
    llm_providers: str = "gemini,groq,ollama"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_enabled: bool = False
    llm_timeout_seconds: float = 15.0

    agent_max_steps: int = 5

    scheduler_enabled: bool = True  # run the daily job inside the app
    daily_job_hour: int = 7
    alerts_log_path: str = "alerts.log"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def provider_order(self) -> list[str]:
        return [p.strip().lower() for p in self.llm_providers.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
