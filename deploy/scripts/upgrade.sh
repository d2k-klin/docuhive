#!/bin/sh
# Build the checked-out release, back up the previous one, then migrate and start.
set -eu
: "${DOCUHIVE_PROD_ENV:?Set the current production env file}"
: "${1:?Pass the next release env file}"
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
compose_file="$script_dir/../compose.yml"
old_env=$DOCUHIVE_PROD_ENV
new_env=$1
old() { docker compose --env-file "$old_env" -f "$compose_file" "$@"; }
new() { docker compose --env-file "$new_env" -f "$compose_file" "$@"; }
old config --quiet
new config --quiet
new build api web
stage=backup
recover() {
  code=$?
  if [ "$code" -ne 0 ]; then
    if [ "$stage" = backup ]; then
      old start api worker worker-ocr web
    else
      echo 'Upgrade failed after migration started. Services remain stopped; follow deploy/scripts/restore.md with the pre-upgrade backup.' >&2
      new stop api worker worker-ocr web || true
    fi
  fi
  exit "$code"
}
trap recover EXIT
old stop -t 90 api worker worker-ocr web
"$script_dir/backup.sh"
stage=migrate
new run --rm migrate
new up -d --wait api worker worker-ocr web
printf '%s\n' 'Upgrade completed. Use the new env file for all later operations.'
