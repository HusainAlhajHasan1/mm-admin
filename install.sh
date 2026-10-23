#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Mattermost Admin Dashboard — installer
# Run on the Mattermost LXC as root:   sudo bash install.sh
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/mm-admin}"
RUN_USER="${RUN_USER:-mm-admin}"
SERVICE_NAME="mm-admin"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT_DEFAULT=8090
MM_URL_DEFAULT="http://127.0.0.1:8065"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!  %s\033[0m\n' "$*"; }

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run this installer as root:  sudo bash install.sh"
  exit 1
fi

step "Checking Python 3"
if ! command -v python3 >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y && apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 python3-pip
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 python3-pip
  else
    echo "Python 3 is required. Install it and re-run this script."
    exit 1
  fi
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 or newer is required (found $(python3 -V 2>&1))."
  exit 1
fi
if ! python3 -c 'import venv' >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then apt-get install -y python3-venv; fi
fi
ok "$(python3 -V 2>&1)"

step "Creating service user '${RUN_USER}'"
if ! id "${RUN_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${RUN_USER}" 2>/dev/null \
    || adduser -S -H -h "${APP_DIR}" "${RUN_USER}"
fi
ok "user: ${RUN_USER}"

step "Installing files into ${APP_DIR}"
mkdir -p "${APP_DIR}/data"
if [[ "${SRC_DIR}" != "${APP_DIR}" ]]; then
  for item in app.py requirements.txt requirements-db.txt templates static agent deploy README.md .env.example; do
    if [[ -e "${SRC_DIR}/${item}" ]]; then
      cp -a "${SRC_DIR}/${item}" "${APP_DIR}/"
    fi
  done
fi
ok "files copied"

step "Installing Python dependencies (this can take a minute)"
if [[ ! -x "${APP_DIR}/venv/bin/python" ]]; then
  python3 -m venv "${APP_DIR}/venv"
fi
"${APP_DIR}/venv/bin/pip" install --upgrade pip >/dev/null
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
if ! "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements-db.txt"; then
  warn "Optional database drivers (psycopg2-binary / PyMySQL) could not be installed."
  warn "Full DM visibility via DATABASE_URL will be unavailable until they are installed."
fi
ok "dependencies ready"

step "Checking configuration"
if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  MM_URL="${MM_URL:-${MM_URL_DEFAULT}}"
  DASH_PORT="${DASH_PORT:-${PORT_DEFAULT}}"
  if [[ -t 0 ]]; then
    printf '    Mattermost URL [%s]: ' "${MM_URL}"
    read -r answer || true
    MM_URL="${answer:-${MM_URL}}"
    printf '    Dashboard port [%s]: ' "${DASH_PORT}"
    read -r answer || true
    DASH_PORT="${answer:-${DASH_PORT}}"
  fi
  MM_URL_ESC="$(printf '%s' "${MM_URL}" | sed -e 's/[&|]/\\&/g')"
  DASH_PORT_ESC="$(printf '%s' "${DASH_PORT}" | sed -e 's/[&|]/\\&/g')"
  sed -i "s|^MM_URL=.*|MM_URL=${MM_URL_ESC}|" "${APP_DIR}/.env"
  sed -i "s|^DASH_PORT=.*|DASH_PORT=${DASH_PORT_ESC}|" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
  ok "created ${APP_DIR}/.env"
else
  ok "keeping existing ${APP_DIR}/.env"
fi

DASH_PORT="$(grep -E '^DASH_PORT=' "${APP_DIR}/.env" | tail -1 | cut -d= -f2 | tr -d ' ' || true)"
DASH_PORT="${DASH_PORT:-${PORT_DEFAULT}}"

chown -R "${RUN_USER}:${RUN_USER}" "${APP_DIR}" 2>/dev/null || chown -R "${RUN_USER}" "${APP_DIR}"

step "Installing systemd service"
if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
  if [[ -f "${APP_DIR}/deploy/mm-admin.service" ]]; then
    sed -e "s|/opt/mm-admin|${APP_DIR}|g" \
        -e "s/^User=mm-admin/User=${RUN_USER}/" \
        -e "s/^Group=mm-admin/Group=${RUN_USER}/" \
        "${APP_DIR}/deploy/mm-admin.service" > "/etc/systemd/system/${SERVICE_NAME}.service"
  else
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Mattermost Admin Dashboard
After=network-online.target

[Service]
User=${RUN_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  fi
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
  systemctl restart "${SERVICE_NAME}"
  sleep 2
  if systemctl is-active --quiet "${SERVICE_NAME}"; then
    ok "service ${SERVICE_NAME} is running"
  else
    warn "service did not start — check: journalctl -u ${SERVICE_NAME} -n 50"
  fi
else
  warn "systemd was not detected. Start the dashboard manually with:"
  echo "    sudo -u ${RUN_USER} ${APP_DIR}/venv/bin/python ${APP_DIR}/app.py"
fi

step "Opening the firewall port (if a firewall is active)"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow "${DASH_PORT}/tcp" >/dev/null 2>&1 && ok "ufw: allowed ${DASH_PORT}/tcp"
fi
if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port="${DASH_PORT}/tcp" >/dev/null 2>&1 || true
  firewall-cmd --reload >/dev/null 2>&1 || true
  ok "firewalld: allowed ${DASH_PORT}/tcp"
fi

IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"
printf '\n\033[1;32m=========================================================\033[0m\n'
printf '\033[1;32m Mattermost Admin Dashboard is installed\033[0m\n'
printf ' Open:      http://%s:%s\n' "${IP_ADDR:-<LXC-IP>}" "${DASH_PORT}"
printf ' Sign in:   with a Mattermost System Admin account\n'
printf ' Config:    %s/.env\n' "${APP_DIR}"
printf ' Logs:      journalctl -u %s -f\n' "${SERVICE_NAME}"
printf ' Restart:   systemctl restart %s\n' "${SERVICE_NAME}"
printf '\033[1;32m=========================================================\033[0m\n\n'
