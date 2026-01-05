# Railway (Prefect Server + Worker)

This repo includes a `Procfile` for hosting Prefect Server and a Prefect Worker on Railway.

## What the Railway “web” service is

The Railway `web` process runs **Prefect Server**.

- It exposes the **Prefect API** at `/api`.
- It also serves the **Prefect UI** in the browser.

Yes: this is where you’ll see your Prefect resources (work pools, deployments, runs, logs).

Important distinction:

- This is **not** your application’s custom dashboard UI.
- This is Prefect’s UI for orchestration/observability.

Your flows will show up there once you create deployments against that server.

## Files

- `Procfile`
  - `web`: starts Prefect Server
  - `worker`: starts Prefect Worker

## Core idea

- Prefect Server runs in the Railway `web` process.
- Prefect Worker runs in the Railway `worker` process.
- Deployments are created against that server and executed by the worker (no Prefect Cloud managed compute quota).

## Minimum required configuration

At minimum:

- `PREFECT_API_URL` on the worker: `https://<prefect-server-public-domain>/api`
- `DATABASE_URL` on the worker: the app Postgres URL (vaults/metrics tables)

Prefect Server also needs its own metadata DB URL (Prefect’s internal DB), typically configured as `PREFECT_API_DATABASE_CONNECTION_URL`.
