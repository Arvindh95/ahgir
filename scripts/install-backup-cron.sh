#!/bin/bash
# Installs the PicUr backup cron entry + logrotate config on a VPS.
#
# Run this ONCE on a freshly-provisioned VPS (must be root). The cron
# file itself lives in version control at scripts/cron/picur-backups
# so the schedule is auditable + reviewable, not just whatever happens
# to be on whichever box you're currently logged into.

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: this script must be run as root" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing /etc/cron.d/picur-backups..."
install -m 0644 "$SCRIPT_DIR/cron/picur-backups" /etc/cron.d/picur-backups

echo "Installing /etc/logrotate.d/picur-backups..."
cat > /etc/logrotate.d/picur-backups <<'EOF'
/var/log/picur-backups.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 0644 root root
}
EOF

# Make sure cron picks up the new file.
if command -v service >/dev/null 2>&1; then
    service cron reload 2>/dev/null || systemctl reload cron 2>/dev/null || true
fi

# Make sure the backup target exists and is private.
install -d -m 0700 /backups /backups/postgres /backups/compreface /backups/minio /backups/config

echo "Done. Cron entry installed; next run at 03:15 UTC."
echo "Tail the log with: tail -f /var/log/picur-backups.log"
