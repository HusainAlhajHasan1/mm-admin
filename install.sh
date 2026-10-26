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
MM_OS_USER="${MM_OS_USER:-mattermost}"

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
PY_MM="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"

install_venv_support() {
  # On Debian/Ubuntu "import venv" can succeed while ensurepip (which creates
  # pip inside a new virtualenv) is missing, so test ensurepip explicitly.
  python3 -c 'import ensurepip' >/dev/null 2>&1 && return 0
  warn "Python virtualenv support is incomplete (ensurepip missing) - installing it"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y >/dev/null 2>&1 || true
    apt-get install -y python3-venv python3-pip "python3${PY_MM}-venv" >/dev/null 2>&1 \
      || apt-get install -y python3-venv python3-pip >/dev/null 2>&1 \
      || true
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3-pip >/dev/null 2>&1 || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3-pip >/dev/null 2>&1 || true
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache py3-pip python3-dev >/dev/null 2>&1 || true
  fi
  python3 -c 'import ensurepip' >/dev/null 2>&1
}

install_venv_support || true
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
  for item in app.py requirements.txt requirements-db.txt templates static agent deploy tools tests README.md PUBLISH-TO-GITHUB.md LICENSE .env.example; do
    if [[ -e "${SRC_DIR}/${item}" ]]; then
      cp -a "${SRC_DIR}/${item}" "${APP_DIR}/"
    fi
  done
fi
ok "files copied"

step "Installing Python dependencies (this can take a minute)"
VENV="${APP_DIR}/venv"
VENV_PY="${VENV}/bin/python"
VENV_PIP="${VENV}/bin/pip"

# A venv without pip is useless: rebuild it rather than failing halfway.
if [[ -e "${VENV}" ]] && { [[ ! -x "${VENV_PY}" ]] || [[ ! -x "${VENV_PIP}" ]]; }; then
  warn "existing virtualenv at ${VENV} is incomplete - rebuilding it"
  rm -rf "${VENV}"
fi

if [[ ! -x "${VENV_PY}" ]]; then
  install_venv_support || true
  if ! python3 -m venv "${VENV}"; then
    rm -rf "${VENV}"
    warn "python3 -m venv failed - retrying after installing venv support"
    install_venv_support || true
    python3 -m venv "${VENV}" || true
  fi
fi

# Some Debian/Ubuntu images create the venv but skip pip entirely.
if [[ -x "${VENV_PY}" && ! -x "${VENV_PIP}" ]]; then
  warn "virtualenv was created without pip - bootstrapping it"
  "${VENV_PY}" -m ensurepip --upgrade >/dev/null 2>&1 || true
fi
# "pip" may be reachable as "python -m pip" even without the console script.
if [[ -x "${VENV_PY}" ]]; then
  if "${VENV_PY}" -m pip --version >/dev/null 2>&1; then
    VENV_PIP="${VENV_PY} -m pip"
  else
    echo
    echo "ERROR: could not create a Python virtual environment with pip."
    echo
    echo "Install the venv package for Python ${PY_MM}, then re-run this script:"
    echo "    apt-get update"
    echo "    apt-get install -y python3-venv python3${PY_MM}-venv python3-pip"
    echo
    echo "If that package does not exist on your distribution, use:"
    echo "    apt-get install -y python3-venv python3-pip"
    echo
    echo "Then remove the broken environment and try again:"
    echo "    rm -rf ${VENV} && sudo bash ${SRC_DIR}/install.sh"
    exit 1
  fi
fi

# shellcheck disable=SC2086
${VENV_PIP} install --upgrade pip >/dev/null
# shellcheck disable=SC2086
${VENV_PIP} install -r "${APP_DIR}/requirements.txt"
# shellcheck disable=SC2086
if ! ${VENV_PIP} install -r "${APP_DIR}/requirements-db.txt"; then
  warn "Optional database drivers (psycopg2-binary / PyMySQL) could not be installed."
  warn "Full DM visibility via DATABASE_URL will be unavailable until they are installed."
fi

# Verify the app can actually run before handing over to systemd.
if ! "${VENV_PY}" -c "import flask, waitress, requests" >/dev/null 2>&1; then
  echo
  echo "ERROR: the Python packages were installed but cannot be imported."
  echo "Try:  ${VENV_PIP} install -r ${APP_DIR}/requirements.txt"
  exit 1
fi
ok "dependencies ready"

step "Checking Mattermost file storage (for chat attachments)"
MM_DATA_DIR_DETECTED=""
for candidate in "${MM_DATA_DIR:-}" /opt/mattermost/data /var/opt/mattermost/data /mattermost/data; do
  if [[ -n "${candidate}" && -d "${candidate}" ]]; then
    MM_DATA_DIR_DETECTED="${candidate}"
    break
  fi
done
if [[ -n "${MM_DATA_DIR_DETECTED}" ]]; then
  ok "file storage: ${MM_DATA_DIR_DETECTED}"
  if ! runuser -u "${RUN_USER}" -- test -r "${MM_DATA_DIR_DETECTED}" 2>/dev/null; then
    if getent group mattermost >/dev/null 2>&1; then
      usermod -aG mattermost "${RUN_USER}" 2>/dev/null && \
        ok "added ${RUN_USER} to the 'mattermost' group (needed to read attachments)" || \
        warn "could not add ${RUN_USER} to the mattermost group"
    fi
  fi
  if runuser -u "${RUN_USER}" -- test -r "${MM_DATA_DIR_DETECTED}" 2>/dev/null; then
    ok "attachments readable by ${RUN_USER}"
  else
    warn "attachments are NOT readable by ${RUN_USER} - images will show as missing."
    warn "Fix with:  usermod -aG mattermost ${RUN_USER} && systemctl restart mm-admin"
    warn "Or set MM_DATA_DIR in ${APP_DIR}/.env if your data lives elsewhere."
  fi
else
  warn "Mattermost data directory not found - attachments will not be shown."
  warn "Set MM_DATA_DIR in ${APP_DIR}/.env (Mattermost FileSettings.Directory)."
fi

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
  if [[ -n "${MM_DATA_DIR_DETECTED}" ]]; then
    if grep -qE '^#?[[:space:]]*MM_DATA_DIR=' "${APP_DIR}/.env"; then
      sed -i "s|^#\{0,1\}[[:space:]]*MM_DATA_DIR=.*|MM_DATA_DIR=${MM_DATA_DIR_DETECTED}|" "${APP_DIR}/.env"
    else
      printf '\n# Mattermost data directory (chat attachments)\nMM_DATA_DIR=%s\n' \
        "${MM_DATA_DIR_DETECTED}" >> "${APP_DIR}/.env"
    fi
  fi
  chmod 600 "${APP_DIR}/.env"
  ok "created ${APP_DIR}/.env"
else
  ok "keeping existing ${APP_DIR}/.env"
fi

DASH_PORT="$(grep -E '^DASH_PORT=' "${APP_DIR}/.env" | tail -1 | cut -d= -f2 | tr -d ' ' || true)"
DASH_PORT="${DASH_PORT:-${PORT_DEFAULT}}"

chown -R "${RUN_USER}:${RUN_USER}" "${APP_DIR}" 2>/dev/null || chown -R "${RUN_USER}" "${APP_DIR}"

step "Checking for mmctl (optional)"
MMCTL_BIN=""
for candidate in "${MMCTL_PATH:-}" /opt/mattermost/bin/mmctl /usr/local/bin/mmctl /usr/bin/mmctl; do
  if [[ -n "${candidate}" && -x "${candidate}" ]]; then
    MMCTL_BIN="${candidate}"
    break
  fi
done
SUDOERS_FILE=/etc/sudoers.d/mm-admin-mmctl
if [[ -n "${MMCTL_BIN}" ]]; then
  ok "mmctl found: ${MMCTL_BIN} (used for permanent deletions the API refuses)"
  TMP_SUDOERS="$(mktemp)"
  {
    echo "# Let the dashboard run mmctl as the Mattermost OS user (permanent deletes)."
    echo "${RUN_USER} ALL=(${MM_OS_USER}) NOPASSWD: ${MMCTL_BIN}"
  } > "${TMP_SUDOERS}"
  if command -v visudo >/dev/null 2>&1; then
    if visudo -cf "${TMP_SUDOERS}" >/dev/null 2>&1; then
      install -m 0440 -o root -g root "${TMP_SUDOERS}" "${SUDOERS_FILE}"
      ok "sudoers rule installed: ${SUDOERS_FILE}"
    else
      warn "sudoers rule rejected by visudo - mmctl fallback stays unavailable"
      MMCTL_BIN=""
    fi
  else
    install -m 0440 -o root -g root "${TMP_SUDOERS}" "${SUDOERS_FILE}"
    ok "sudoers rule installed: ${SUDOERS_FILE}"
  fi
  rm -f "${TMP_SUDOERS}"
else
  rm -f "${SUDOERS_FILE}"
  ok "mmctl not found - permanent deletes rely on the Mattermost API flags"
fi

step "Installing systemd service"
if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
  if [[ -f "${APP_DIR}/deploy/mm-admin.service" ]]; then
    sed -e "s|/opt/mm-admin|${APP_DIR}|g" \
        -e "s/^User=mm-admin/User=${RUN_USER}/" \
        -e "s/^Group=mm-admin/Group=${RUN_USER}/" \
        "${APP_DIR}/deploy/mm-admin.service" > "/tmp/${SERVICE_NAME}.service.tmp"
    if [[ -n "${MMCTL_BIN}" ]]; then
      # sudo needs the privilege bit, so hardening is relaxed only in this case
      sed -i "s/^NoNewPrivileges=true/NoNewPrivileges=false/" "/tmp/${SERVICE_NAME}.service.tmp"
      sed -i "/^EnvironmentFile=/a Environment=MM_OS_USER=${MM_OS_USER}" "/tmp/${SERVICE_NAME}.service.tmp"
      ok "service may call mmctl through sudo (NoNewPrivileges off)"
    fi
    mv "/tmp/${SERVICE_NAME}.service.tmp" "/etc/systemd/system/${SERVICE_NAME}.service"
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
