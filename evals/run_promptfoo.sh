#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Ambos proveedores Python cargan .env mediante python-dotenv, que admite
# CRLF. No se ejecuta el contenido de .env como código de shell.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

if [ "${1:-}" = "view" ]; then
    shift
    view_args=()
    for arg in "$@"; do
        if [[ "$arg" == *.json ]] && [ -f "$arg" ]; then
            npx promptfoo import "$arg" --force >/dev/null 2>&1 || true
        else
            view_args+=("$arg")
        fi
    done
    exec npx promptfoo view "${view_args[@]}"
fi

exec npx promptfoo "$@"
