#!/usr/bin/env bash
# Run every infra test in the container it belongs to. Called by `make test-infra`.
set -euo pipefail
cd "$(dirname "$0")/../.."
export MSYS_NO_PATHCONV=1
DC="docker compose -f infra/docker-compose.yml --project-directory ."

ip_of() {  # container IP on the private network
  docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{if eq $k "'"${COMPOSE_PROJECT_NAME:-blind-tuner}"'_private"}}{{$v.IPAddress}}{{end}}{{end}}' "$($DC ps -q "$1")"
}
PG_PROD_IP=$(ip_of pg-prod)
PG_TWIN_IP=$(ip_of pg-twin)
echo "pg-prod private IP: $PG_PROD_IP, pg-twin private IP: $PG_TWIN_IP"

echo "== ai container: isolation =="
$DC exec -T -e PG_PROD_IP="$PG_PROD_IP" -e PG_TWIN_IP="$PG_TWIN_IP" ai python -m pytest -p no:cacheprovider infra/tests/test_isolation.py -v
echo "== gateway container: no internet =="
$DC exec -T gateway python -m pytest -p no:cacheprovider infra/tests/test_private_no_internet.py -v
echo "== tools container: no internet =="
$DC run --rm -T tools python -m pytest -p no:cacheprovider infra/tests/test_private_no_internet.py -v
echo "== tools container: postgres images =="
$DC run --rm -T tools python -m pytest -p no:cacheprovider infra/tests/test_postgres.py -v
