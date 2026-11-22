"""Central configuration. Everything environment-dependent lives here."""
import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./careeros.db")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or None
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        # auto: Claude when a key is present, else offline.
        # claude: require a key (startup fails without one).
        # offline: never call the API.
        self.llm_mode = os.getenv("LLM_MODE", "auto")
        self.data_dir = os.getenv("DATA_DIR", "./data")

    @property
    def claude_enabled(self) -> bool:
        if self.llm_mode == "offline":
            return False
        if self.llm_mode == "claude" and not self.anthropic_api_key:
            raise RuntimeError("LLM_MODE=claude but ANTHROPIC_API_KEY is not set")
        return bool(self.anthropic_api_key)


settings = Settings()
