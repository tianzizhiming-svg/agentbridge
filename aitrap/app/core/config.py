from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Azone"
    APP_VERSION: str = "V0"
    DATABASE_URL: str = "postgresql+psycopg2://azone:azone_secret@localhost:5432/azone_dev"
    PROBE_INTERVAL_MINUTES: int = 15
    PROBE_TIMEOUT_SECONDS: int = 5
    ADMIN_SECRET_KEY: str = "AzoneGod2026!xK9$mZ7pQ3"

    class Config:
        env_file = ".env"


settings = Settings()
