from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Azone"
    APP_VERSION: str = "V0"
    DATABASE_URL: str = "postgresql+psycopg2://USER:PASSWORD@localhost:5432/azone_dev"
    PROBE_INTERVAL_MINUTES: int = 15
    PROBE_TIMEOUT_SECONDS: int = 5
    ADMIN_SECRET_KEY: str = "CHANGE_ME_OR_SET_ENV"

    class Config:
        env_file = ".env"


settings = Settings()
