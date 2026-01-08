import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the Prefect evm-pools-sync flow locally")
    p.add_argument(
        "--use-prefect-api",
        action="store_true",
        help="Use PREFECT_API_URL/PREFECT_API_KEY from the environment if set. Default is local/ephemeral execution.",
    )
    p.add_argument(
        "--no-persist",
        action="store_true",
        help="Dry-run: fetch + transform only; do not write to Postgres.",
    )
    return p.parse_args()


def _maybe_set_ephemeral_prefect_env(use_prefect_api: bool) -> None:
    if use_prefect_api:
        return
    # Ensure local execution doesn't depend on Prefect server/cloud.
    os.environ["PREFECT_API_URL"] = ""
    os.environ.pop("PREFECT_API_URL", None)
    os.environ.pop("PREFECT_API_KEY", None)
    os.environ.setdefault("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")


async def _run(persist: bool) -> int:
    from src.pipelines.flows.evm_pools import sync_evm_pools_flow

    pools_written, metrics_written = await sync_evm_pools_flow(persist=persist)
    mode = "persist" if persist else "dry-run"
    print(f"Done ({mode}): pools={pools_written} metrics={metrics_written}")
    return 0


def main() -> int:
    args = _parse_args()

    # Ensure `import src...` works when running from the repo root.
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    _maybe_set_ephemeral_prefect_env(args.use_prefect_api)
    
    persist = not args.no_persist
    return asyncio.run(_run(persist=persist))


if __name__ == "__main__":
    raise SystemExit(main())
