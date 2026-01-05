#!/usr/bin/env sh
set -eu

# Prefect deployments in this repo use the `git_clone` pull step.
# Some Railway build paths may omit `git`, which causes flow runs to crash.
# Install git at runtime if it's missing.
if ! command -v git >/dev/null 2>&1; then
  echo "git not found; attempting to install..." >&2
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y git
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache git
  else
    echo "No supported package manager found to install git." >&2
    exit 1
  fi
fi

exec prefect worker start --pool hyperliquid-vault-ingestion
