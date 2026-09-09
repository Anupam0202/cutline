#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${1:?Usage: ./scripts/smoke_test.sh https://service-url}"
JAR="$(mktemp)"; trap 'rm -f "${JAR}"' EXIT
curl --fail --silent --show-error "${BASE_URL}/health/live" | grep -q '"ok"'
curl --fail --silent --show-error "${BASE_URL}/health/ready" | grep -q '"ready"'
CAPABILITIES="$(curl --fail --silent --show-error --cookie-jar "${JAR}" "${BASE_URL}/api/capabilities")"
printf '%s' "${CAPABILITIES}" | grep -q '"LIVE"'
printf '%s' "${CAPABILITIES}" | grep -q '"Parallel Search"'
printf '%s' "${CAPABILITIES}" | grep -q '"Gemini on Vertex AI"'
echo "Smoke checks passed."
