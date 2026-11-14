#!/bin/sh
# Build the database URL if only its parts were supplied (as on AWS, where the password comes from Secrets Manager),
# apply migrations, then start the API. Fails fast if the schema cannot be migrated.
set -eu

if [ -z "${ENERGIQ_DATABASE_URL:-}" ] && [ -n "${DB_HOST:-}" ]; then
  : "${DB_USER:?DB_USER is required when DB_HOST is set}" "${DB_PASSWORD:?DB_PASSWORD is required when DB_HOST is set}"
  ENERGIQ_DATABASE_URL="$(python - <<'PY'
import os
from urllib.parse import quote
e = os.environ
print(f"postgresql+psycopg://{quote(e['DB_USER'], safe='')}:{quote(e['DB_PASSWORD'], safe='')}"
      f"@{e['DB_HOST']}:{e.get('DB_PORT', '5432')}/{e.get('DB_NAME', 'energiq')}")
PY
)"
  export ENERGIQ_DATABASE_URL
fi

# Society artifacts (evaluation files, backtests, SHAP, deployed models). The image carries them read-only under SOCIETY_SEED_DIR; the API
# reads and writes ENERGIQ_SOCIETY_DIR on the /data volume (administrator uploads are trained there). The copy is made once: the marker is written
# only after a complete copy, so an interrupted first start is simply repeated, and a later start never touches what the application has stored there.
if [ -n "${SOCIETY_SEED_DIR:-}" ] && [ -n "${ENERGIQ_SOCIETY_DIR:-}" ] && [ -d "$SOCIETY_SEED_DIR" ] && [ ! -e "$ENERGIQ_SOCIETY_DIR/.seeded" ]; then
  echo "[entrypoint] copying the bundled society artifacts to $ENERGIQ_SOCIETY_DIR (first start only)"
  mkdir -p "$ENERGIQ_SOCIETY_DIR"
  cp -a "$SOCIETY_SEED_DIR"/. "$ENERGIQ_SOCIETY_DIR"/
  touch "$ENERGIQ_SOCIETY_DIR/.seeded"
fi

if [ "${ENERGIQ_SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "[entrypoint] applying database migrations"
  alembic -c backend/alembic.ini upgrade head
fi
exec "$@"
