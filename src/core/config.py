import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn

from .prefect_secrets import env_or_prefect_secret

load_dotenv()
class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "HyperEVM Vault Discovery"
    DEBUG: bool = False
    
    # Database Settings
    # Pydantic will validate that this is a valid Postgres URL
    # Keep this optional so imports don't fail in environments where the DB
    # url is only available at runtime (e.g. Prefect-managed execution).
    DATABASE_URL: PostgresDsn | None = Field(
        env_or_prefect_secret("DATABASE_URL", "database-url"),
        alias="DATABASE_URL",
    )
    
    # Prefect Settings
    # These are typically provided by the runtime (Prefect worker/agent).
    PREFECT_API_URL: str | None = os.getenv('PREFECT_API_URL')
    PREFECT_API_KEY: str | None = os.getenv('PREFECT_API_KEY')
    
    # Hyperliquid API Settings
    HL_BASE_URL: str = "https://api.hyperliquid.xyz/info"
    
    # Security (for Streamlit Authenticator)
    AUTH_COOKIE_NAME: str = "hyper_vault_auth"
    AUTH_SIGNATURE_KEY: str = env_or_prefect_secret("AUTH_SIGNATURE_KEY", "auth-signature-key") or "super-secret-key-change-this"
    AUTH_EXPIRY_DAYS: int = 30

    # Config for Pydantic V2
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # Ignore extra env vars not defined here
    )

# Singleton instance to be imported across the app
settings = Settings()