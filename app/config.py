"""Настройки сервиса. Значения берутся из переменных окружения или из файла .env."""

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Дежурный по дедлайнам"
    # Секрет намеренно вынесен в окружение: в код такие значения не попадают никогда.
    api_token: str = "не задан"
    debug: bool = False


settings = Settings()
