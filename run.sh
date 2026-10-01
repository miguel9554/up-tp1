#!/usr/bin/env bash
# Run any command inside the LibreLane container.
#
# Usage: ./run.sh [command [args...]]
#   ./run.sh                          # interactive shell
#   ./run.sh yosys -V
#   ./run.sh librelane --help
#
# This directory is mounted at /work (the working directory), so use
# paths relative to it.
set -euo pipefail

LIBRELANE_TAG="${LIBRELANE_TAG:-3.0.14}"
PDK_ROOT_HOST="${PDK_ROOT_HOST:-$HOME/.ciel}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$PDK_ROOT_HOST"

# Only allocate a TTY when we actually have one (e.g. not in make/CI/pipes).
TTY_FLAGS=(-i)
[ -t 0 ] && [ -t 1 ] && TTY_FLAGS=(-it)

[ "$#" -eq 0 ] && set -- bash

exec docker run --rm "${TTY_FLAGS[@]}" \
  -u "$(id -u):$(id -g)" \
  -v "$PROJECT_DIR:/work" \
  -v "$PDK_ROOT_HOST:/pdks" \
  -e PDK_ROOT=/pdks \
  -e HOME=/tmp \
  -w /work \
  "ghcr.io/librelane/librelane:$LIBRELANE_TAG" \
  "$@"
