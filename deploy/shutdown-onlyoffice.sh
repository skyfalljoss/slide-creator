#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --project-directory "$ROOT_DIR")
if [[ -f "$ROOT_DIR/.env" ]]; then
    COMPOSE+=(--env-file "$ROOT_DIR/.env")
fi

running_services="$("${COMPOSE[@]}" ps --status running --services)"
if ! grep -qx "onlyoffice" <<<"$running_services"; then
    echo "ONLYOFFICE is not running; no graceful shutdown is needed."
    exit 0
fi

"${COMPOSE[@]}" exec -T onlyoffice documentserver-prepare4shutdown.sh &
shutdown_pid=$!

cleanup() {
    if kill -0 "$shutdown_pid" >/dev/null 2>&1; then
        kill "$shutdown_pid" >/dev/null 2>&1 || true
    fi
}
trap cleanup INT TERM

deadline=$((SECONDS + 300))
while kill -0 "$shutdown_pid" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
        echo "ONLYOFFICE did not become ready for shutdown within 300 seconds." >&2
        kill "$shutdown_pid" >/dev/null 2>&1 || true
        wait "$shutdown_pid" || true
        exit 1
    fi
    sleep 1
done

wait "$shutdown_pid"
trap - INT TERM
echo "ONLYOFFICE is ready to stop."
