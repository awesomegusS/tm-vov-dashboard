#!/usr/bin/env python3
"""Create Prefect v3 deployments.

By default, this script deploys using *local code* (no pull steps). This is the
most reliable approach on Railway when the worker is built from this repo.

Optionally, you can deploy using remote code storage (git clone pull steps)
with `--use-remote-source`.
"""

from __future__ import annotations

import argparse
import importlib
import os
from dataclasses import dataclass
from typing import Any
from prefect.schedules import Cron



DEFAULT_SOURCE = os.getenv("PREFECT_DEPLOY_SOURCE")


@dataclass(frozen=True)
class DeploymentSpec:
	name: str
	entrypoint: str
	cron: str


DEPLOYMENTS: tuple[DeploymentSpec, ...] = (
	DeploymentSpec(
		name="hourly-vault-metrics",
		entrypoint="src/pipelines/flows/upsert_vaults.py:upsert_vault_metrics_flow",
		cron="0 * * * *",
	),
	DeploymentSpec(
		name="4h-top-500",
		entrypoint="src/pipelines/flows/upsert_vaults.py:update_top_500_flow",
		cron="0 */4 * * *",
	),
)


def _import_flow_from_entrypoint(entrypoint: str):
	"""Import and return a Prefect `Flow` from an entrypoint.

	Supports both:
	- `src/pipelines/flows/foo.py:bar`
	- `src.pipelines.flows.foo:bar`
	"""
	module_part, flow_attr = entrypoint.split(":", 1)
	module_part = module_part.replace(".py", "")
	module_part = module_part.replace("/", ".")
	module = importlib.import_module(module_part)
	return getattr(module, flow_attr)


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
	use_remote_source: bool,
	source: str,
	ref: str | None,
	work_pool_name: str,
	work_queue_name: str | None,
	image: str | None,
	timezone: str | None,
) -> None:
	from prefect import flow

	src = _build_source(source, ref) if use_remote_source else None

	errors: list[str] = []
	for spec in DEPLOYMENTS:
		try:
			if use_remote_source:
				if not source:
					raise ValueError("--source is required when using --use-remote-source")
				deploy_flow = flow.from_source(source=src, entrypoint=spec.entrypoint)
			else:
				deploy_flow = _import_flow_from_entrypoint(spec.entrypoint)

			deploy_kwargs: dict[str, Any] = {
				"name": spec.name,
				"work_pool_name": work_pool_name,
				"schedules": [Cron(spec.cron, timezone=(timezone or "UTC"))],
			}
			if work_queue_name:
				deploy_kwargs["work_queue_name"] = work_queue_name

			# For managed pools, image is typically set in the pool's base job template.
			# If provided, pass as a job variable (matches Prefect docs: job_variables).
			if image:
				deploy_kwargs["job_variables"] = {"image": image}

			deploy_flow.deploy(**deploy_kwargs)
			print(f"Deployed {spec.name}")
		except Exception as exc:
			errors.append(f"{spec.name}: {exc}")

	if errors:
		msg = "One or more deployments failed:\n" + "\n".join(f"- {e}" for e in errors)
		raise SystemExit(msg)


def main() -> None:
	p = argparse.ArgumentParser(description="Create Prefect deployments (local code).")
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
		"--use-remote-source",
		# action="store_true",
		default=True,
		help="Use remote code storage pull steps (git clone). Default is local-code deployments.",
	)
	p.add_argument(
		"--source",
		default=DEFAULT_SOURCE,
		help=(
			"Remote code storage source (git URL, s3://, gs://, az://). "
			"Required when using --use-remote-source."
		),
	)
	p.add_argument(
		"--ref",
		default=None,
		help="Optional git ref (branch/tag/commit). Used only with --use-remote-source.",
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

	if args.use_remote_source and not args.source:
		raise SystemExit(
			"Missing deployment code storage source. Set PREFECT_DEPLOY_SOURCE or pass --source."
		)

	deploy_from_source(
		use_remote_source=args.use_remote_source,
		source=args.source,
		ref=args.ref,
		work_pool_name=args.work_pool,
		work_queue_name=args.work_queue,
		image=args.image,
		timezone=args.timezone,
	)


if __name__ == "__main__":
	main()
