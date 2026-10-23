# Mattermost Admin Dashboard

A self-hosted admin panel that runs **on the same LXC / VM as your Mattermost server**, on its own port (default **8090**). Open `http://<LXC-IP>:8090`, sign in with a **Mattermost System Admin** account, and manage users, teams, conversations, presence and locations from one place.

No cloud services, no external JS/CSS, no build step — a small Flask app plus a vanilla-JS front-end and a local SQLite database for history.

![Sign-in](docs/screenshots/login.png)

| Overview | Users |
|---|---|
| ![Overview](docs/screenshots/overview.png) | ![Users](docs/screenshots/users.png) |

| Chat viewer | Presence history |
|---|---|
| ![Chats](docs/screenshots/chats.png) | ![Presence](docs/screenshots/presence.png) |

| Locations | Settings |
|---|---|
| ![Locations](docs/screenshots/locations.png) | ![Settings](docs/screenshots/settings.png) |

---

## What's inside

| # | Feature | Where |
|---|---------|-------|
| 1 | **Add a user** with username, email, password and team. If the team doesn't exist you are prompted to create it first (the user is *not* created until a valid team is chosen or the team is created). | Users → **Add user** |
| 2 | **Add a team** with optional members and open / invite-only privacy. | Teams → **Create team** |
| 3 | **Lists of teams and users**, with search, status filter, team chips, member counts and export. | Users / Teams |
| 4 | **Chat viewer**: choose a user → see every other user they have DM'd → pick one → read the whole conversation. | Chats |
| 5 | **Online / offline history** per user: current status, online time, last seen, status timeline. | Presence |
| 6 | **Location right now and as a history list** (agent + login IPs), with map links and CSV export. | Locations |
| 7 | **Delete users** (deactivate or permanent) and **delete teams** (archive or permanent). | Users / Teams |
| 8 | **Add / remove any user to / from any team**, with member or team-admin role. | Users → manage teams / Teams → members |
| + | Password reset, sign-out-everywhere, promote/demote System Admins, activate/deactivate, user detail drawer with sessions and history, server-health panel, dashboard-wide audit log, CSV export, manual status poll, one-click location agent download. | everywhere |

Every action performed in the dashboard is written to a local **admin activity log** (Activity page).

---

## Quick start

On the Mattermost LXC:

```bash
# 1. copy the mm-admin folder to the LXC (scp, rsync, WinSCP, Proxmox upload…)
scp -r mm-admin root@<LXC-IP>:/root/

# 2. install
ssh root@<LXC-IP>
cd /root/mm-admin
sudo bash install.sh
```

The installer:

* checks Python ≥ 3.10 and creates a dedicated system user (`mm-admin`),
* installs the app into `/opt/mm-admin` with its own virtualenv,
* asks for the Mattermost URL (default `http://127.0.0.1:8065`) and the dashboard port (default `8090`),
* installs and starts the `mm-admin` systemd service,
* opens the port in `ufw` / `firewalld` when one is active.

Then open:

```
http://<LXC-IP>:8090
```

Sign in with your Mattermost **System Admin** username/email and password. If your account uses two-factor authentication, the dashboard asks for the 6-digit code on a second step.

> Only accounts with the **System Admin** role are allowed in. Any other account — or a wrong password — is rejected and never reaches the dashboard.

---

## Manual install (without the installer)

```bash
sudo apt install python3 python3-venv python3-pip
sudo useradd --system --home /opt/mm-admin --shell /usr/sbin/nologin mm-admin
sudo mkdir -p /opt/mm-admin && sudo cp -r . /opt/mm-admin/
cd /opt/mm-admin
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt
sudo ./venv/bin/pip install -r requirements-db.txt     # optional, for chat DB access
sudo cp .env.example .env && sudo nano .env
sudo cp deploy/mm-admin.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mm-admin
```

Run it directly for testing:

```bash
python3 app.py          # uses waitress, listens on 0.0.0.0:8090
```

Useful commands:

```bash
systemctl status mm-admin
journalctl -u mm-admin -f
systemctl restart mm-admin
curl http://127.0.0.1:8090/health
```

---

## Configuration (`.env`)

All settings live in `/opt/mm-admin/.env`. Restart after editing (`systemctl restart mm-admin`).

| Variable | Default | Meaning |
|----------|---------|---------|
| `MM_URL` | `http://127.0.0.1:8065` | Mattermost base URL. Use `https://…` if it terminates TLS. |
| `MM_ADMIN_TOKEN` | *(empty)* | Optional System Admin **Personal Access Token**. Used by the background presence poller and agent username lookups when nobody is signed in. Recommended for 24/7 presence history. |
| `DASH_HOST` / `DASH_PORT` | `0.0.0.0` / `8090` | Where the dashboard listens. `0.0.0.0` = reachable via the LXC IP. |
| `DASH_SECRET` | *auto-generated* | Cookie-signing secret. Stored in `data/secret_key` when empty. |
| `APP_TIMEZONE` | system timezone | Timezone for all displayed/exported times. |
| `STATUS_POLL_SECONDS` | `60` | Presence polling interval (min 20). |
| `DATABASE_URL` | *(empty)* | Read-only Mattermost DB connection for **full chat visibility**. See below. |
| `LOCATION_API_KEY` | *auto-generated* | API key for the location agent. Shown in Locations → Location agent. |
| `GEOIP_ENABLED` | `1` | Allow external IP geolocation lookups (city-level). |
| `TRUST_PROXY` | `0` | Set to `1` behind nginx/traefik so real client IPs are used. |
| `DASH_INSECURE_TLS` | `0` | Accept self-signed certificates from Mattermost. |
| `DASH_COOKIE_SECURE` | `0` | Set to `1` when serving the dashboard over HTTPS. |
| `PUBLIC_URL` | *(auto)* | Base URL embedded into downloaded agent scripts. |
| `MMCTL_PATH` | *(auto-detected)* | Full path to the `mmctl` binary. Used as a fallback for operations the REST API forbids (permanent deletion). Auto-detected in `/opt/mattermost/bin/mmctl` and `PATH`. |
| `MM_OS_USER` | `mattermost` | OS user that owns the Mattermost installation. When the dashboard runs as root it calls `runuser -u <user> -- mmctl --local …`. |

### Recommended: personal access token for background tracking

Presence history is collected by a background poller. It uses `MM_ADMIN_TOKEN` if set; otherwise it reuses the session token from the last admin login (valid up to Mattermost's session lifetime, typically 30 days). For reliable, long-running history create a PAT:

1. Mattermost → **System Console → Integrations → Integration Management** → enable personal access tokens.
2. Profile → **Security → Personal Access Tokens** → create one (System Admin account).
3. Put it in `.env`:
   ```
   MM_ADMIN_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
4. `sudo systemctl restart mm-admin`

---

## Reading other users' chats — important

Mattermost's API **does not allow a System Admin to read other users' direct messages** unless the admin is a member of that channel. This is a deliberate privacy feature; even the System Console can't open someone else's DM. Trying it returns `403 You do not have the appropriate permissions`.

This dashboard therefore supports two chat sources:

### A. Direct read-only database access (recommended — full visibility)

Point `DATABASE_URL` at the Mattermost database with a **SELECT-only** account. The dashboard opens the connection in read-only mode and only reads `Posts`, `Channels` and `ChannelMembers` for direct-message channels.

**PostgreSQL**

```bash
# 1. create a read-only role (choose a strong password)
sudo -u postgres psql -d mattermost <<'SQL'
CREATE ROLE mm_dash LOGIN PASSWORD 'CHANGE_ME_STRONG';
GRANT CONNECT ON DATABASE mattermost TO mm_dash;
GRANT USAGE ON SCHEMA public TO mm_dash;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mm_dash;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mm_dash;
SQL
```

```ini
# /opt/mm-admin/.env
DATABASE_URL=postgresql://mm_dash:CHANGE_ME_STRONG@127.0.0.1:5432/mattermost
```

**MySQL / MariaDB**

```sql
CREATE USER 'mm_dash'@'localhost' IDENTIFIED BY 'CHANGE_ME_STRONG';
GRANT SELECT ON mattermost.* TO 'mm_dash'@'localhost';
FLUSH PRIVILEGES;
```

```ini
DATABASE_URL=mysql://mm_dash:CHANGE_ME_STRONG@127.0.0.1:3306/mattermost
```

The Mattermost database credentials themselves are in `/opt/mattermost/config/config.json` under `SqlSettings.DataSource` (or `/etc/mattermost/config.json` depending on your install).

After editing `.env`, restart the service. The Settings page shows **Database connected** when it works.

> ⚠️ **Privacy / policy:** reading private conversations is sensitive. With database access the dashboard deliberately bypasses Mattermost's DM privacy model. Make sure this is allowed in your organisation, inform your users, and keep the dashboard behind a trusted network or VPN.

### B. REST API only (default, limited)

Without `DATABASE_URL` the dashboard uses the normal API. You can still see the list of people a user has DM'd in many cases, but opening the conversation of two other users will usually fail with `403`, and the UI explains why. Chats where the admin is a participant work normally. This mode requires no database credentials.

---

## Online / offline history

A background poller asks Mattermost for the status of every active user every `STATUS_POLL_SECONDS` and stores **only changes** (`online`, `away`, `dnd`, `offline`) in the local SQLite database.

* Online time counts `online`, `away` and `dnd` as connected.
* History begins when the dashboard first runs with a valid token (PAT or admin session). It cannot reconstruct the past.
* Use **Presence → Poll statuses now** to take an immediate snapshot.
* Each user row has a timeline (24 h / 7 d / 30 d) and a detail panel with status intervals and durations.

---

## Location tracking

Three independent sources feed the Locations page:

1. **Dashboard login** — when an admin signs in, the client IP is recorded and geolocated (useful when accessing from outside the LAN).
2. **Mattermost login audit** — *Locations → Location agent → Import login IPs* reads login events with IPs from the Mattermost audit log (via the API when available, or from the `audits` table when `DATABASE_URL` is set). Audit logging must be enabled on the Mattermost side.
3. **Location agent (optional)** — a tiny Python script on a user's computer reports its public IP every few minutes, which yields a city-level position. This is the most reliable way to know where a user is *right now*.

> IP geolocation is approximate (city / ISP level, not GPS). VPNs, proxies and mobile networks will shift the result. When a device is on the same LAN, the dashboard records it as **Local network** instead of inventing a location.

### Installing the agent

In the dashboard: **Locations → Location agent**. The download already contains your dashboard URL and API key.

**Linux / macOS**

```bash
sudo mkdir -p /opt/mm-location-agent
sudo cp ~/Downloads/mm-location-agent.py /opt/mm-location-agent/
sudo tee /etc/default/mm-location-agent >/dev/null <<'EOF'
DASH_URL=http://192.168.1.50:8090
API_KEY=paste-the-key-from-the-dashboard
USERNAME=mattermost-username
INTERVAL=300
EOF
sudo tee /etc/systemd/system/mm-location-agent.service >/dev/null <<'EOF'
[Unit]
Description=Mattermost Location Agent
After=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/default/mm-location-agent
ExecStart=/usr/bin/python3 /opt/mm-location-agent/mm-location-agent.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now mm-location-agent
journalctl -u mm-location-agent -f     # verify the first ping
```

**Windows**

1. Install Python 3 from python.org (tick “Add Python to PATH”).
2. Save the downloaded `mm-location-agent.py` to `C:\mm-agent\`.
3. Test it in PowerShell:
   ```powershell
   python C:\mm-agent\mm-location-agent.py --url http://192.168.1.50:8090 --key KEY --username jdoe
   ```
4. Create a **Task Scheduler** task → *At log on* → program `python`, arguments `C:\mm-agent\mm-location-agent.py`, start in `C:\mm-agent`.

**One-shot mode** (e.g. cron every 10 minutes):

```bash
*/10 * * * * python3 /opt/mm-location-agent/mm-location-agent.py --url http://LXC:8090 --key KEY --username jdoe --once
```

The agent only sends the Mattermost username, public IP, hostname and OS. It never reads messages, files, keystrokes or screens. If you have GPS coordinates (e.g. a field device), pass `--lat 49.4521 --lon 11.0767`.

---

## Day-to-day usage

### Add a user

1. **Users → Add user**.
2. Fill username, email, password (or press **Generate**), optional first/last name.
3. Type the team handle in **Team** (autocomplete lists existing teams).
4. If the team doesn't exist, the form shows **Create team “…”** — create the team, and the form is ready again. The user is created only after a valid team exists.
5. Choose **Member** or **Team admin**, optionally grant **System Admin**.
6. Share the generated password with the user securely.

### Create a team

**Teams → Create team**: display name, handle (auto-derived), open or invite-only, and an optional searchable list of members to seed the team.

### Read a conversation

1. **Chats** → pick a user on the left.
2. The middle column lists everyone that user has DM'd, with last-message previews.
3. Click a person → the full conversation opens. **Load older messages** pages backwards.
4. Request from the user: “show me his chats with X” maps directly onto this flow.

With database mode, the request runs as a read-only SQL query on the DM channel; the admin does not need to be a member.

### Presence

**Presence** → choose 24 h / 7 d / 30 d → click a row for a large timeline, intervals and durations. **Poll statuses now** forces a fresh snapshot.

### Locations

* **Latest locations** — last known position per user, IP, coordinates link, source and age; optional 30-second auto-refresh.
* **History** — filter by user or source, page through records, export CSV.
* **Import login IPs** — pull historical login locations from the Mattermost audit log.

### Remove a user / team

* **Deactivate** (recommended): the account can't log in, sessions are revoked, messages and files are kept. Reversible.
* **Delete permanently**: requires `ServiceSettings.EnableAPIUserDeletion = true` in Mattermost; otherwise the dashboard explains the problem and suggests `mmctl user delete <user> --confirm`.
* **Delete team**: archives it (hidden from users, data kept). *Permanent* requires `ServiceSettings.EnableAPITeamDeletion = true`.

If either flag is disabled, the dashboard automatically retries the permanent delete through **`mmctl`** when the binary is available (it is auto-detected at `/opt/mattermost/bin/mmctl`, `PATH`, or `MMCTL_PATH`). No extra setup is needed on a standard Mattermost install running as root; otherwise the dialog tells you exactly what to enable.

### Other per-user actions

From the user drawer (**Users → click a row**):

* **Sign out everywhere** – revokes every Mattermost session for that user without touching the account.
* **Make admin / Remove admin** – grants or removes the System Admin role (you cannot demote yourself).
* **Reset password** – sets a new password, with a generator and copy button.
* **Deactivate / Activate** – reversible account lock.
* **Delete user** – deactivate or permanent delete (see above).

### Move a user between teams

* **Users** → team icon on the user row: add/remove any team, with roles.
* **Teams** → **Manage members**: add by username, remove, see team admins.

---

## Security notes

* Login is verified against Mattermost itself. The admin's **password is never stored**; only the session token returned by Mattermost is kept in a signed, HTTP-only cookie (12-hour lifetime).
* CSRF tokens are required for all state-changing requests; login attempts are rate-limited per IP (8 failures / 10 minutes).
* The dashboard binds to `0.0.0.0` so it is reachable at the LXC IP. Keep it on a trusted network, or expose it through a VPN/reverse proxy with HTTPS:
  * set `DASH_COOKIE_SECURE=1` and `TRUST_PROXY=1`;
  * example nginx:
    ```nginx
    server {
        listen 443 ssl;
        server_name admin.example.com;
        ssl_certificate     /etc/ssl/fullchain.pem;
        ssl_certificate_key /etc/ssl/privkey.pem;
        location / {
            proxy_pass http://127.0.0.1:8090;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
    }
    ```
* The dashboard runs as an unprivileged `mm-admin` system user; data lives in `/opt/mm-admin/data/admin.db` (SQLite, WAL).
* The optional DB connection is opened **read-only** and ideally uses a `SELECT`-only role.
* The agent API key can submit location pings; treat it as a password. Rotate it by deleting the `location_api_key` row in `data/admin.db` (or set `LOCATION_API_KEY` in `.env`) and re-downloading the agent.
* Every dashboard action is logged under **Activity**.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Cannot reach Mattermost at …` | Check `MM_URL`, `systemctl status mattermost`, `curl http://127.0.0.1:8065/api/v4/system/ping`. |
| TLS / certificate error | `DASH_INSECURE_TLS=1` for self-signed Mattermost, then restart. |
| “This account is not a Mattermost System Admin” | Use an account with the System Admin role (System Console → User Management → Roles). |
| MFA loop | Enter the current 6-digit code on the second step; code reuse is not allowed. |
| Chats show `403` or “no conversations” | Mattermost blocks DM access via API — configure `DATABASE_URL` (see above). |
| Presence timeline empty | The poller needs a token: set `MM_ADMIN_TOKEN` or keep an admin signed in; check `journalctl -u mm-admin`. |
| No location data | Check the agent key/URL; audit logging may be off; LAN devices show “Local network”. |
| Port unreachable from LAN | `DASH_HOST=0.0.0.0`, `ufw allow 8090/tcp`, or firewalld port; Proxmox firewall rules. |
| Permanent delete refuses | Enable `EnableAPIUserDeletion` / `EnableAPITeamDeletion` in Mattermost, install `mmctl` (auto-detected) so the dashboard can fall back to it, or use deactivate/archive. |
| Login succeeds but pages 401 | Mattermost session expired — sign in again. |
| Logged out randomly after changing config | `DASH_SECRET` changed; that's expected. |
| Database configured but `db_ok=false` | Wrong URL/credentials, driver missing (`pip install psycopg2-binary` / `PyMySQL`), or DB not reachable from the LXC. |

Logs: `journalctl -u mm-admin -n 100 --no-pager`. Health probe: `GET /health`.

---

## Updating

```bash
# copy the new version over /opt/mm-admin (keep .env and data/)
sudo systemctl stop mm-admin
sudo cp -r mm-admin/* /opt/mm-admin/        # or re-run install.sh from the new folder
sudo /opt/mm-admin/venv/bin/pip install -r /opt/mm-admin/requirements.txt
sudo systemctl start mm-admin
```

The SQLite schema is created automatically and is backward-compatible.

## Uninstalling

```bash
sudo systemctl disable --now mm-admin
sudo rm /etc/systemd/system/mm-admin.service
sudo rm -rf /opt/mm-admin
sudo userdel mm-admin 2>/dev/null || true
# optional: drop the read-only DB role
# sudo -u postgres psql -c 'DROP ROLE mm_dash;'
```

---

## File layout

```
mm-admin/
├── app.py                     Flask backend (APIs, auth, poller, geolocation)
├── requirements.txt           Flask, waitress, requests
├── requirements-db.txt        psycopg2-binary, PyMySQL (optional)
├── install.sh                 installer for the LXC
├── .env.example               configuration template
├── templates/
│   ├── login.html             Mattermost-admin sign-in page
│   └── index.html             dashboard shell
├── static/
│   ├── style.css              dark UI, no external assets
│   └── app.js                 single-page front-end
├── agent/
│   └── mm-location-agent.py   optional location agent (stdlib only)
├── deploy/
│   ├── mm-admin.service       dashboard systemd unit
│   └── mm-location-agent.service
└── data/                      created at runtime (SQLite + secret)
```

---

## Technical notes

* Mattermost REST API v4 is used for authentication, users, teams, memberships, statuses and settings. The chat viewer uses either `/channels/{id}/posts` (API mode, limited) or direct read-only SQL (`posts`, `channels`, `channelmembers`).
* The dashboard is not a Mattermost plugin and needs no changes to the Mattermost deployment (unless you want full DM visibility, which requires DB access).
* All timestamps are stored as UTC epochs; display uses `APP_TIMEZONE`.
* SQLite runs in WAL mode and survives restarts. Deleting `data/admin.db` resets presence/location history and regenerates the agent key.

---

*Built for internal administration. Review your organisation's privacy rules before enabling chat and location monitoring, and inform the people affected.*
