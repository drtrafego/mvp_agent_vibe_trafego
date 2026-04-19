from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Meta
    META_ACCESS_TOKEN: str
    META_PHONE_NUMBER_ID: str = "115216611574100"
    META_VERIFY_TOKEN: str
    META_APP_SECRET: str = ""

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_LOCK_TTL: int = 90  # segundos

    # LLM
    LLM_PROVIDER: str = "gemini"  # gemini | anthropic | openai
    GOOGLE_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = ""  # se vazio, usa default do provider

    # Google Calendar
    GOOGLE_CALENDAR_ID: str = "primary"
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""  # JSON string

    # Output
    BOT_SEND_URL: str
    BOT_SEND_TOKEN: str = ""

    # Notify
    NOTIFY_PHONE: str = "5491151133210"

    # Follow-up
    FOLLOWUP_INTERVAL_MINUTES: int = 30
    FOLLOWUP_FU0_DELAY_HOURS: int = 2

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def llm_model_resolved(self) -> str:
        """Retorna modelo default por provider se LLM_MODEL nao definido."""
        if self.LLM_MODEL:
            return self.LLM_MODEL
        defaults = {
            "gemini": "gemini-2.0-flash",
            "anthropic": "claude-sonnet-4-6",
            "openai": "gpt-4o-mini",
        }
        return defaults.get(self.LLM_PROVIDER, "gemini-2.0-flash")


settings = Settings()
