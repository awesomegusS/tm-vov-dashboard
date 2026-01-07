import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn
from pydantic import model_validator

from .prefect_secrets import env_or_prefect_secret

load_dotenv()


def _read_text_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


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

    # HyperEVM / On-chain fallback (ERC-4626)
    # Used to fetch vault TVL on-chain when DeFi Llama does not include a target protocol.
    HYPEREVM_RPC_URL: str | None = Field(
        env_or_prefect_secret("HYPEREVM_RPC_URL", "hyperevm-rpc-url"),
        alias="HYPEREVM_RPC_URL",
    )
    # JSON list of target ERC-4626 vaults to ingest.
    # Example:
    # [
    #   {"protocol": "Felix", "vault_address": "0x...", "name": "Felix USDC Vault"},
    #   {"protocol": "Hyperlend", "vault_address": "0x..."}
    # ]
    # Option A (recommended locally): point to a JSON file in-repo.
    # Default: data/erc4626-targets-hyperbeat.json
    ERC4626_TARGET_VAULTS_FILE: str | None = Field(
        env_or_prefect_secret("ERC4626_TARGET_VAULTS_FILE", "erc4626-target-vaults-file"),
        alias="ERC4626_TARGET_VAULTS_FILE",
    )

    # Option B (recommended in deployments): supply JSON directly (env var or Prefect Secret).
    ERC4626_TARGET_VAULTS_JSON: str | None = Field(
        env_or_prefect_secret("ERC4626_TARGET_VAULTS_JSON", "erc4626-target-vaults-json"),
        alias="ERC4626_TARGET_VAULTS_JSON",
    )

    # Optional: if the ERC-4626 vault's underlying asset is USDC, we can treat totalAssets as USD.
    # Provide the canonical USDC contract address on HyperEVM to make this check reliable.
    HYPEREVM_USDC_ADDRESS: str | None = Field(
        env_or_prefect_secret("HYPEREVM_USDC_ADDRESS", "hyperevm-usdc-address"),
        alias="HYPEREVM_USDC_ADDRESS",
    )
    
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

    @model_validator(mode="after")
    def _load_erc4626_targets_from_file_if_needed(self):
        if self.ERC4626_TARGET_VAULTS_JSON:
            return self

        # 1) If user provided a file path (env var or Prefect Secret), read it.
        if self.ERC4626_TARGET_VAULTS_FILE:
            raw = _read_text_file(Path(self.ERC4626_TARGET_VAULTS_FILE).expanduser())
            if raw:
                self.ERC4626_TARGET_VAULTS_JSON = raw
                return self

        # 2) Local dev fallback: read the repo's default targets file if it exists.
        repo_root = Path(__file__).resolve().parents[2]
        default_path = repo_root / "data" / "erc4626-targets-hyperbeat.json"
        raw = _read_text_file(default_path)
        if raw:
            self.ERC4626_TARGET_VAULTS_JSON = raw

        return self

# Singleton instance to be imported across the app
settings = Settings()