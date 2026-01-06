from __future__ import annotations

import os
from typing import Mapping, Optional


def load_prefect_secret(block_name: str) -> Optional[str]:
    """Load a Prefect Secret block value by name.

    Returns None if Prefect isn't available, credentials are missing, or the block
    does not exist.
    """
    try:
        from prefect.blocks.system import Secret
        from prefect.utilities.asyncutils import run_coro_as_sync

        # Prefect has both sync (`load`) and async (`aload`) variants; depending on
        # version/runner, `load()` may return an awaitable. Handle both safely.
        if hasattr(Secret, "aload"):
            block = run_coro_as_sync(Secret.aload(block_name))
        else:
            block = Secret.load(block_name)

        value = block.get()
        if value is None:
            return None
        value = str(value).strip()
        return value or None
    except Exception:
        return None


def env_or_prefect_secret(env_key: str, block_name: str, *, strip: bool = True) -> Optional[str]:
    """Return an env var if present, else try a Prefect Secret block."""
    value = os.getenv(env_key)
    if value is not None:
        value = str(value)
        return value.strip() if strip else value
    return load_prefect_secret(block_name)


def apply_prefect_secrets_to_env(mapping: Mapping[str, str], *, overwrite: bool = False) -> None:
    """Set env vars from Prefect Secret blocks.

    mapping: {ENV_VAR_NAME: prefect_secret_block_name}

    If ENV var is missing (or overwrite=True), tries to load the Prefect Secret
    block and sets os.environ[ENV_VAR_NAME] to that value.
    """
    for env_key, block_name in mapping.items():
        if not overwrite and os.getenv(env_key):
            continue
        value = load_prefect_secret(block_name)
        if value:
            os.environ[env_key] = value
