#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: RESTORE_CONFIRM_TARGET=<database> $0 gs://bucket/backup.sql.gz [database]" >&2
    exit 2
fi

BACKUP_URI="$1"
TARGET_DATABASE="${2:-slideforge_restore}"

case "$BACKUP_URI" in
    gs://*.sql.gz) ;;
    *)
        echo "Backup URI must be a gs:// object ending in .sql.gz." >&2
        exit 1
        ;;
esac

if [[ ! "$TARGET_DATABASE" =~ ^slideforge_restore(_[A-Za-z0-9]+)?$ ]]; then
    echo "Restore target must be slideforge_restore or a suffixed drill database." >&2
    exit 1
fi
if [[ "${RESTORE_CONFIRM_TARGET:-}" != "$TARGET_DATABASE" ]]; then
    echo "Set RESTORE_CONFIRM_TARGET=$TARGET_DATABASE to confirm this restore drill." >&2
    exit 1
fi

for command in docker gcloud gzip gunzip; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Required command not found: $command" >&2
        exit 1
    fi
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP_FILE="$(mktemp "${TMPDIR:-/tmp}/slideforge-restore.XXXXXXXX.sql.gz")"
DATABASE_CREATED=false
COMPOSE=(docker compose --project-directory "$ROOT_DIR")
if [[ -f "$ROOT_DIR/.env" ]]; then
    COMPOSE+=(--env-file "$ROOT_DIR/.env")
fi

cleanup() {
    status=$?
    rm -f "$TEMP_FILE"
    if [[ $status -ne 0 && "$DATABASE_CREATED" == "true" ]]; then
        "${COMPOSE[@]}" exec -T postgres \
            dropdb --username slideforge --if-exists "$TARGET_DATABASE" \
            >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

gcloud storage cp "$BACKUP_URI" "$TEMP_FILE"
gzip -t "$TEMP_FILE"

if [[ "$("${COMPOSE[@]}" exec -T postgres psql --username slideforge \
    --dbname postgres --tuples-only --no-align \
    --command "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DATABASE'")" == "1" ]]; then
    echo "Restore target already exists; refusing to overwrite it: $TARGET_DATABASE" >&2
    exit 1
fi

"${COMPOSE[@]}" exec -T postgres \
    createdb --username slideforge "$TARGET_DATABASE"
DATABASE_CREATED=true

gunzip -c "$TEMP_FILE" \
    | "${COMPOSE[@]}" exec -T postgres psql \
        --username slideforge \
        --dbname "$TARGET_DATABASE" \
        --set ON_ERROR_STOP=1 \
        --single-transaction

DATABASE_CREATED=false
echo "Restore drill completed in database: $TARGET_DATABASE"
