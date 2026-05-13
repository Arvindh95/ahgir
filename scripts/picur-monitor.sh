#!/bin/bash
# Periodic health probe for PicUr. Runs every 5 minutes from cron. Pings
# the public /health endpoint via nginx. If anything degrades, sends an
# alert email through the backend's own SMTP (so we reuse the Brevo creds
# already configured in .env.production — no host msmtp setup needed).
#
# Hysteresis: only emails on STATE CHANGE (healthy→unhealthy and back),
# so a sustained outage produces one email at the start and one at
# recovery, not 12 per hour. State is tracked in /var/run/picur-monitor.state.
#
# Usage from cron:
#   */5 * * * * /opt/ahgir/scripts/picur-monitor.sh >> /var/log/picur-monitor.log 2>&1

set -uo pipefail

ALERT_EMAIL="${PICUR_ALERT_EMAIL:-superadmin@picur.my}"
HEALTH_URL="${PICUR_HEALTH_URL:-http://127.0.0.1:8005/health}"
STATE_FILE="/var/run/picur-monitor.state"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Probe with a hard timeout so a hung backend can't hang the monitor.
RESP="$(curl -sS -m 10 -w '\n%{http_code}' "${HEALTH_URL}" 2>&1 || true)"
HTTP_CODE="$(echo "${RESP}" | tail -1)"
BODY="$(echo "${RESP}" | head -n -1)"

# Determine status: unhealthy if HTTP != 200 or JSON status field != healthy
STATUS="unhealthy"
DETAIL=""
if [ "${HTTP_CODE}" = "200" ]; then
    JSON_STATUS="$(echo "${BODY}" | python3 -c "import json, sys; d=json.load(sys.stdin); print(d.get('status', 'unknown'))" 2>/dev/null || echo "parse-error")"
    if [ "${JSON_STATUS}" = "healthy" ]; then
        STATUS="healthy"
    else
        STATUS="unhealthy"
        DETAIL="JSON status=${JSON_STATUS}; body=${BODY}"
    fi
else
    DETAIL="HTTP=${HTTP_CODE}; body=${BODY}"
fi

# Read previous state (default healthy on first run so we don't fire an
# alert just because the state file does not exist yet).
PREV_STATE="healthy"
if [ -f "${STATE_FILE}" ]; then
    PREV_STATE="$(cat "${STATE_FILE}")"
fi

echo "${TS} state=${STATUS} prev=${PREV_STATE} http=${HTTP_CODE}"

send_alert() {
    local subject="$1"
    local html="$2"
    # Reuse the backend's own SMTP — no host-side mail setup needed.
    docker exec picur-backend python -c "
from app.email import send_email
send_email('${ALERT_EMAIL}', '''${subject}''', '''${html}''')
" 2>&1 || echo "${TS} ALERT-SEND-FAILED ${subject}"
}

if [ "${STATUS}" != "${PREV_STATE}" ]; then
    if [ "${STATUS}" = "unhealthy" ]; then
        send_alert \
            "[PicUr ALERT] picur.my health check degraded" \
            "<h2>PicUr health check failed</h2><p><b>Time:</b> ${TS}</p><p><b>Endpoint:</b> ${HEALTH_URL}</p><p><b>HTTP:</b> ${HTTP_CODE}</p><pre style='background:#1a1a1a;padding:16px;border-radius:8px;color:#ddd;overflow:auto'>$(echo "${BODY}" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</pre><p>Check container status: <code>docker ps --filter name=picur</code></p>"
    else
        send_alert \
            "[PicUr RECOVERY] picur.my health restored" \
            "<h2>PicUr health restored</h2><p><b>Time:</b> ${TS}</p><p>All services reporting healthy again.</p>"
    fi
fi

echo "${STATUS}" > "${STATE_FILE}"
