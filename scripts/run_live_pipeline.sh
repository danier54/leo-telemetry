#!/usr/bin/env bash
set -euo pipefail

cd /workspaces/leo-telemetry

export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-30}"
export MIN_REQUEST_INTERVAL_SECONDS="${MIN_REQUEST_INTERVAL_SECONDS:-5}"
export DECODE_POLL_INTERVAL_SECONDS="${DECODE_POLL_INTERVAL_SECONDS:-2}"
export DEMUX_POLL_INTERVAL_SECONDS="${DEMUX_POLL_INTERVAL_SECONDS:-2}"
export EXPORTER_POLL_INTERVAL_SECONDS="${EXPORTER_POLL_INTERVAL_SECONDS:-1}"
export EXPORTER_PORT="${EXPORTER_PORT:-8000}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

if [ -z "${SATNOGS_API_TOKEN:-}" ]; then
  echo "SATNOGS_API_TOKEN is not set; starting ingest in local fallback mode."
else
  echo "SATNOGS_API_TOKEN detected; using authenticated SatNOGS requests."
fi

python - <<'PY' >/tmp/leo-redis-check.log 2>&1
import socket
s = socket.socket()
try:
    s.connect(('127.0.0.1', 6379))
    print('redis-ok')
except Exception as exc:
    print(f'redis-fail:{exc}')
finally:
    s.close()
PY

if ! grep -q 'redis-ok' /tmp/leo-redis-check.log; then
  echo "Redis is not reachable on localhost:6379. Trying to start a local container..."
  if command -v docker >/dev/null 2>&1; then
    docker rm -f leo-redis >/dev/null 2>&1 || true
    docker run --name leo-redis -p 6379:6379 -d redis:7-alpine >/tmp/leo-redis-start.log 2>&1 || {
      echo "Failed to start Redis with Docker."
      cat /tmp/leo-redis-start.log
      exit 1
    }
    for attempt in $(seq 1 10); do
      python - <<'PY' >/tmp/leo-redis-check.log 2>&1
import socket
s = socket.socket()
try:
    s.connect(('127.0.0.1', 6379))
    print('redis-ok')
except Exception as exc:
    print(f'redis-fail:{exc}')
finally:
    s.close()
PY
      if grep -q 'redis-ok' /tmp/leo-redis-check.log; then
        break
      fi
      sleep 1
    done
  else
    echo "Redis is not reachable on localhost:6379. Start it first with:"
    echo "  docker run --name leo-redis -p 6379:6379 -d redis:7-alpine"
    exit 1
  fi
fi

if ! grep -q 'redis-ok' /tmp/leo-redis-check.log; then
  echo "Redis is still not reachable on localhost:6379."
  exit 1
fi

python scripts/run_live_pipeline.py > /tmp/leo-launcher.log 2>&1 &

sleep 3

echo "Started live pipeline. Logs:"
echo "  /tmp/leo-ingest.log"
echo "  /tmp/leo-decode.log"
echo "  /tmp/leo-demux.log"
echo "  /tmp/leo-exporter.log"
echo ""
echo "Check Prometheus metrics with:"
echo "  curl -s 'http://127.0.0.1:9090/api/v1/query?query=leo_telemetry_readings_total'"
