from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "HyperEVM Vault Discovery"
    DEBUG: bool = False
    
    # Database Settings
    # Pydantic will validate that this is a valid Postgres URL
    DATABASE_URL: PostgresDsn = Field(
        'postgresql://postgres:MhTFAfdMyVzKoyiUJbzLENdeKirpzgbp@shuttle.proxy.rlwy.net:50128/railway',
        alias="DATABASE_URL"
    )
    
    # Prefect Settings
    PREFECT_API_URL: str | None = 'https://api.prefect.cloud/api/accounts/f88e212b-d748-4dff-a1ff-df2c35a27c1c/workspaces/cc372b5d-d23a-467a-8f1e-725260210a30'
    PREFECT_API_KEY: str | None = 'pnu_QoZRT9MIULFeZvbI0oY7UOLrsmvTXR1Dxc6D'
    
    # Hyperliquid API Settings
    HL_BASE_URL: str = "https://api.hyperliquid.xyz/info"
    
    # Security (for Streamlit Authenticator)
    AUTH_COOKIE_NAME: str = "hyper_vault_auth"
    AUTH_SIGNATURE_KEY: str = "super-secret-key-change-this"
    AUTH_EXPIRY_DAYS: int = 30

    # Config for Pydantic V2
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # Ignore extra env vars not defined here
    )

# Singleton instance to be imported across the app
settings = Settings()