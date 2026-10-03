#!/usr/bin/env bash
# Host dev server for the LOCAL web app (live Ask, history, database and slow-log pages) against the
# running Compose stack. The gateway and ai ports are not published, so their container IPs are read
# from Docker (the host can reach Compose's internal bridges on Linux). Port: $1 or 5173.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-5173}"
ip() { # $1 container, $2 compose network: the address on that network
  local f="{{(index .NetworkSettings.Networks \"blind-tuner_$2\").IPAddress}}"
  { docker inspect -f "$f" "$1" 2>/dev/null || sg docker -c "docker inspect -f '$f' $1"; } | tr -d '[:space:]'; }
GW=$(ip blind-tuner-gateway-1 boundary)
AI=$(ip blind-tuner-ai-1 boundary)
echo "gateway http://$GW:8000  ai http://$AI:8100  web http://localhost:$PORT"
mkdir -p .bt-history
export BT_LOCAL=1 NEXT_PUBLIC_BT_LOCAL=1 BT_CONFIG=../../config.yaml \
  GATEWAY_URL="http://$GW:8000" AI_URL="http://$AI:8100" \
  BT_WEB_HOSTS="localhost:$PORT,127.0.0.1:$PORT" \
  BT_HISTORY_DIR="$PWD/.bt-history" BT_PLANS_SAMPLE="$PWD/../../data/plans/web_sample.json"
exec npx next dev --port "$PORT"
