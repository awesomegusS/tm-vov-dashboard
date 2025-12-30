#!/usr/bin/env python3
"""Create Prefect v3 deployments (via Python) using remote code storage.

This follows the Prefect docs pattern:

	flow.from_source(source=..., entrypoint=...).deploy(...)

Using remote storage (git) fixes Prefect-managed pool failures where the
runtime container does not include your repository.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any
from prefect.schedules import Cron


DEFAULT_SOURCE = "https://github.com/awesomegusS/tm-vov-dashboard.git"


@dataclass(frozen=True)
class DeploymentSpec:
	name: str
	entrypoint: str
	cron: str


DEPLOYMENTS: tuple[DeploymentSpec, ...] = (
	DeploymentSpec(
		name="hourly-vault-summaries",
		entrypoint="src/pipelines/flows/upsert_vaults.py:upsert_vaults_flow",
		cron="0 * * * *",
	),
	DeploymentSpec(
		name="4h-vault-details",
		entrypoint="src/pipelines/flows/upsert_vault_metrics.py:upsert_vault_metrics_flow",
		cron="0 */4 * * *",
	),
)


def _build_source(source: str, ref: str | None) -> Any:
	"""Return a `source` value compatible with `flow.from_source`.

	Prefect accepts a string URL directly; if a ref is provided and the installed
	Prefect exposes a `GitRepository` source object, use it.
	"""
	if not ref:
		return source

	try:
		# Prefect v3 includes GitRepository storage helper in most installs.
		from prefect.runner.storage import GitRepository  # type: ignore

		return GitRepository(url=source, reference=ref)
	except Exception:
		# Fall back to plain URL (ref ignored) rather than failing hard.
		return source


def deploy_from_source(
	*,
	source: str,
	ref: str | None,
	work_pool_name: str,
	work_queue_name: str | None,
	image: str | None,
	timezone: str | None,
) -> None:
	from prefect import flow

	src = _build_source(source, ref)

	errors: list[str] = []
	for spec in DEPLOYMENTS:
		try:
			remote_flow = flow.from_source(source=src, entrypoint=spec.entrypoint)

			deploy_kwargs: dict[str, Any] = {
				"name": spec.name,
				"work_pool_name": work_pool_name,
				"schedules": [Cron(spec.cron, timezone=timezone)]
			}
			if work_queue_name:
				deploy_kwargs["work_queue_name"] = work_queue_name

			# For managed pools, image is typically set in the pool's base job template.
			# If provided, pass as a job variable (matches Prefect docs: job_variables).
			if image:
				deploy_kwargs["job_variables"] = {"image": image}

			remote_flow.deploy(**deploy_kwargs)
			print(f"Deployed {spec.name}")
		except Exception as exc:
			errors.append(f"{spec.name}: {exc}")

	if errors:
		msg = "One or more deployments failed:\n" + "\n".join(f"- {e}" for e in errors)
		raise SystemExit(msg)


def main() -> None:
	p = argparse.ArgumentParser(description="Create Prefect deployments via remote code storage (git).")
	p.add_argument(
		"--work-pool",
		required=True,
		help="Prefect work pool name (e.g. hyperliquid-vault-ingestion)",
	)
	p.add_argument(
		"--work-queue",
		default=None,
		help="Optional work queue name (for managed pools this is often 'default')",
	)
	p.add_argument(
		"--source",
		default=DEFAULT_SOURCE,
		help=f"Remote code storage source (git URL, s3://, gs://, az://). Default: {DEFAULT_SOURCE}",
	)
	p.add_argument(
		"--ref",
		default=None,
		help="Optional git ref (branch/tag/commit). Used when supported by your Prefect install.",
	)
	p.add_argument(
		"--image",
		default=None,
		help="Optional image override via job variables (use allowlisted prefecthq/* for managed pools).",
	)
	p.add_argument(
		"--timezone",
		default="UTC",
		help="Schedule timezone for the cron (default: UTC).",
	)
	args = p.parse_args()

	deploy_from_source(
		source=args.source,
		ref=args.ref,
		work_pool_name=args.work_pool,
		work_queue_name=args.work_queue,
		image=args.image,
		timezone=args.timezone,
	)


if __name__ == "__main__":
	main()
