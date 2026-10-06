#!/bin/sh
set -eu
umask 077
env_file=${ENV_FILE:-.env}
backup_dir=${BACKUP_DIR:-backups}
: "${DB_BACKUP_CONFIG:?Set an absolute path to the host database client option file}"
: "${DB_BACKUP_NAME:?Set the external database name to back up}"
case "$DB_BACKUP_CONFIG" in
  /*) ;;
  *) echo "DB_BACKUP_CONFIG must be an absolute path" >&2; exit 1 ;;
esac
[ -r "$DB_BACKUP_CONFIG" ] || { echo "Database option file is not readable" >&2; exit 1; }
dump_bin=${DB_DUMP_BIN:-mariadb-dump}
command -v "$dump_bin" >/dev/null 2>&1 || { echo "Install $dump_bin on the host" >&2; exit 1; }
mkdir -p "$backup_dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
db_file="$backup_dir/database-$stamp.sql"
photos_file="$backup_dir/profile-photos-$stamp.tar.gz"
# The host client connects to the external server; no database container is used.
# Keep credentials in a chmod-600 option file, never in process arguments.
"$dump_bin" --defaults-extra-file="$DB_BACKUP_CONFIG" \
  --single-transaction --quick --triggers "$DB_BACKUP_NAME" > "$db_file.partial"
mv "$db_file.partial" "$db_file"
docker compose --env-file "$env_file" run --rm --no-deps -T api \
  tar -czf - -C /app/instance/profile_photos . > "$photos_file.partial"
mv "$photos_file.partial" "$photos_file"
printf 'Saved %s and %s\n' "$db_file" "$photos_file"
