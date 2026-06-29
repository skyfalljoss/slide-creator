#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

if [[ -z "${BACKUP_GCS_URI:-}" ]]; then
    echo "BACKUP_GCS_URI is required (for example, gs://my-private-bucket/backups)." >&2
    exit 1
fi

case "$BACKUP_GCS_URI" in
    gs://*) ;;
    *)
        echo "BACKUP_GCS_URI must start with gs://." >&2
        exit 1
        ;;
esac

for command in docker gzip gcloud; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Required command not found: $command" >&2
        exit 1
    fi
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="slideforge-${TIMESTAMP}.sql.gz"
TEMP_FILE="$(mktemp "${TMPDIR:-/tmp}/slideforge-backup.XXXXXXXX.sql.gz")"

cleanup() {
    rm -f "$TEMP_FILE"
}
trap cleanup EXIT

docker compose --project-directory "$ROOT_DIR" exec -T postgres \
    pg_dump --username slideforge --dbname slideforge --no-owner --no-privileges \
    | gzip -9 >"$TEMP_FILE"

gcloud storage cp "$TEMP_FILE" "${BACKUP_GCS_URI%/}/${BACKUP_NAME}"
echo "Uploaded database backup: ${BACKUP_GCS_URI%/}/${BACKUP_NAME}"
