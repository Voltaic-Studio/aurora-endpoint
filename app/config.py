from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "aurora-endpoint"
    messages_api_base_url: str = "https://november7-730026606190.europe-west1.run.app"
    openrouter_model: str = "google/gemini-3-flash-preview"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    openrouter_api_key: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
