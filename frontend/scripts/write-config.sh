#!/usr/bin/env bash
# Static-site build step (Render or Vercel): writes js/config.js from environment variables.
#   API_BASE_URL        backend URL, e.g. https://baseerah-api.onrender.com (empty = same origin)
#   USE_MOCK            "true" to run the UI on mock data (default false)
#   REQUEST_TIMEOUT_MS  request timeout in ms (default 90000)
#   CONTACT_EMAIL       optional, shown on about.html#contact
set -euo pipefail
cd "$(dirname "$0")/.."

# JSON string escaping in pure bash (no python/node needed on the build image)
json() {
  local s=${1//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/ }
  printf '"%s"' "$s"
}
mock=false; [ "${USE_MOCK:-false}" = "true" ] && mock=true
timeout=${REQUEST_TIMEOUT_MS:-90000}; timeout=${timeout//[^0-9]/}; timeout=${timeout:-90000}

cat > js/config.js <<CFG
// Generated at build time by scripts/write-config.sh. Do not put secrets here.
window.BASEERAH_CONFIG = {
  API_BASE_URL: $(json "${API_BASE_URL:-}"),
  USE_MOCK: ${mock},
  REQUEST_TIMEOUT_MS: ${timeout},
  CONTACT_EMAIL: $(json "${CONTACT_EMAIL:-}"),
};
CFG
echo "wrote js/config.js (API_BASE_URL=${API_BASE_URL:-<same origin>}, USE_MOCK=${mock})"
