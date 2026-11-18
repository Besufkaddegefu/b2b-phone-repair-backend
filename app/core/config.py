from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "B2B Phone Repair Marketplace"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = Field(..., description="Telegram Bot Token from BotFather")
    TELEGRAM_WEBHOOK_SECRET: str = Field(..., description="Secret token for webhook verification")
    TELEGRAM_WEBHOOK_URL: str = Field(..., description="Public webhook URL for Telegram")

    # Neon Database
    DATABASE_URL: str = Field(..., description="Neon PostgreSQL connection string with sslmode=require")
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # Clerk Authentication
    CLERK_PUBLISHABLE_KEY: str = ""
    CLERK_SECRET_KEY: str = ""
    CLERK_JWKS_URL: str = ""
    CLERK_WEBHOOK_SECRET: str = ""

    # Payments - Chapa
    CHAPA_SECRET_KEY: str = ""
    CHAPA_PUBLIC_KEY: str = ""
    CHAPA_WEBHOOK_SECRET: str = ""
    CHAPA_BASE_URL: str = "https://api.chapa.co/v1"

    # Payments - Telebirr
    TELEBIRR_APP_ID: str = ""
    TELEBIRR_APP_KEY: str = ""
    TELEBIRR_PUBLIC_KEY: str = ""
    TELEBIRR_BASE_URL: str = "https://api.telebirr.com"

    # Payments - CBE Birr
    CBE_WEBHOOK_SECRET: str = ""

    # Media Storage - Cloudflare R2 / S3
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_PUBLIC_URL: str = ""

    # Admin
    ADMIN_TELEGRAM_IDS: list[int] = Field(default_factory=list)
    ADMIN_CHANNEL_ID: str = ""

    @property
    def admin_telegram_ids_list(self) -> list[int]:
        if isinstance(self.ADMIN_TELEGRAM_IDS, str):
            return [int(x.strip()) for x in self.ADMIN_TELEGRAM_IDS.split(",") if x.strip()]
        return self.ADMIN_TELEGRAM_IDS


@lru_cache
def get_settings() -> Settings:
    return Settings()