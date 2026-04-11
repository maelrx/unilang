#!/bin/bash
set -euo pipefail

ROOT=/home/hermes/projects/unilang-hermes-dev/workspace/unilang
export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"
export MINIMAX_API_KEY="$(grep '^MINIMAX_API_KEY=' "$ROOT/.env" | cut -d= -f2-)"
python3 /tmp/benchmark_e2e_minimax.py
