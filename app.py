#!/usr/bin/env python3
"""
Mattermost Admin Dashboard
==========================
A self-hosted admin panel that runs on the same LXC/VM as your Mattermost server.

Features
--------
* Login with a real Mattermost System Admin account (validated against the server,
  MFA supported). Nothing is stored except the session token.
* Create users (with team), create teams (optionally seed members),
  add/remove users to/from teams, reset passwords, deactivate / delete users,
  delete/archive teams.
* User + team browser.
* Read user DM conversations (direct read-only database connection recommended,
  API fallback for channels the admin can access).
* Online / offline history (recorded by a background status poller).
* Location history (login IP geolocation + optional lightweight agent).
* Dashboard audit log.

Run
---
    python3 app.py
or via waitress through `install.sh` / systemd.

Configuration is read from environment variables or a `.env` file next to app.py
(see .env.example).
"""

from __future__ import annotations

import csv
import io
import ipaddress
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse, unquote

import requests
from flask import (Flask, Response, jsonify, make_response, redirect,
                   render_template, request, send_file, session)
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _load_dotenv(path: str) -> None:
    """Tiny .env loader (no external dependency)."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


_load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on", "y")


MM_URL = _env("MM_URL", "http://127.0.0.1:8065").rstrip("/")
if not MM_URL.startswith(("http://", "https://")):
    MM_URL = "http://" + MM_URL
MM_API = MM_URL + "/api/v4"
MM_ADMIN_TOKEN = _env("MM_ADMIN_TOKEN")  # optional Personal Access Token for background tracking
DASH_PORT = _env_int("DASH_PORT", _env_int("PORT", 8090))
DASH_HOST = _env("DASH_HOST", "0.0.0.0")


def _system_timezone() -> str:
    """Prefer the timezone configured on the host so timestamps match the server."""
    for path in ("/etc/timezone",):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                value = fh.read().strip()
            if value:
                return value
        except OSError:
            pass
    try:
        import time as _time
        if _time.tzname:
            return _env("TZ", "UTC")
    except Exception:
        pass
    return "UTC"


APP_TZ = _env("APP_TIMEZONE", _system_timezone() or "UTC")
try:
    TZ = ZoneInfo(APP_TZ)
except Exception:
    APP_TZ = "UTC"
    TZ = ZoneInfo("UTC")
DB_PATH = _env("DB_PATH", os.path.join(DATA_DIR, "admin.db"))
GEOIP_ENABLED = _env_bool("GEOIP_ENABLED", True)
STATUS_POLL_SECONDS = max(20, _env_int("STATUS_POLL_SECONDS", 60))
TRUST_PROXY = _env_bool("TRUST_PROXY", False)
VERIFY_TLS = not _env_bool("DASH_INSECURE_TLS", False)
COOKIE_SECURE = _env_bool("DASH_COOKIE_SECURE", False)
DATABASE_URL = _env("DATABASE_URL")  # optional read-only Mattermost DB (PostgreSQL / MySQL)
AGENT_URL_HINT = _env("PUBLIC_URL", "")  # optional public base URL shown to agents
MMCTL_PATH = _env("MMCTL_PATH", "")  # optional path to mmctl for operations the API forbids
MM_OS_USER = _env("MM_OS_USER", "mattermost")  # OS user that owns the Mattermost install
MM_DATA_DIR = _env("MM_DATA_DIR", "")  # FileSettings.Directory (default: auto-detect)
APP_VERSION = "1.3.0"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)) or DATA_DIR, exist_ok=True)


def _load_or_create_secret() -> str:
    env_secret = _env("DASH_SECRET")
    if env_secret:
        return env_secret
    path = os.path.join(DATA_DIR, "secret_key")
    try:
        if os.path.isfile(path):
            return open(path, "r", encoding="utf-8").read().strip()
        secret = secrets.token_urlsafe(48)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(secret)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return secret
    except OSError:
        return secrets.token_urlsafe(48)


app = Flask(__name__)
app.secret_key = _load_or_create_secret()
app.config.update(
    SESSION_COOKIE_NAME="mmdash_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    JSON_SORT_KEYS=False,
    TEMPLATES_AUTO_RELOAD=True,
    SEND_FILE_MAX_AGE_DEFAULT=0,
)
app.jinja_env.auto_reload = True

ASSET_VERSION = str(int(time.time()))


# --------------------------------------------------------------------------- #
# SQLite helpers
# --------------------------------------------------------------------------- #

_db_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def db_query(sql: str, args: tuple = ()) -> list[dict]:
    with _db_lock:
        con = _connect()
        try:
            rows = con.execute(sql, args).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()


def db_one(sql: str, args: tuple = ()) -> dict | None:
    rows = db_query(sql, args)
    return rows[0] if rows else None


def db_scalar(sql: str, args: tuple = (), default=None):
    row = db_one(sql, args)
    if not row:
        return default
    return list(row.values())[0]


def db_exec(sql: str, args: tuple = ()) -> int:
    with _db_lock:
        con = _connect()
        try:
            cur = con.execute(sql, args)
            con.commit()
            return cur.lastrowid or 0
        finally:
            con.close()


def init_db() -> None:
    with _db_lock:
        con = _connect()
        try:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS kv (
                    k TEXT PRIMARY KEY,
                    v TEXT
                );
                CREATE TABLE IF NOT EXISTS status_state (
                    user_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    changed_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS status_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ts INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_status_events_user_ts
                    ON status_events(user_id, ts);
                CREATE INDEX IF NOT EXISTS idx_status_events_ts
                    ON status_events(ts);
                CREATE TABLE IF NOT EXISTS location_pings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    username TEXT,
                    ts INTEGER NOT NULL,
                    ip TEXT,
                    is_private INTEGER DEFAULT 0,
                    lat REAL,
                    lon REAL,
                    accuracy REAL,
                    city TEXT,
                    region TEXT,
                    country TEXT,
                    country_code TEXT,
                    isp TEXT,
                    source TEXT,
                    hostname TEXT,
                    raw TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_location_user_ts
                    ON location_pings(user_id, ts);
                CREATE INDEX IF NOT EXISTS idx_location_ts
                    ON location_pings(ts);
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    actor TEXT,
                    actor_id TEXT,
                    action TEXT NOT NULL,
                    target TEXT,
                    details TEXT,
                    ip TEXT
                );
                """
            )
            con.commit()
        finally:
            con.close()

    if kv_get("tracking_since") is None:
        kv_set("tracking_since", str(int(time.time())))
    if kv_get("location_api_key") is None:
        kv_set("location_api_key", secrets.token_urlsafe(24))


def kv_get(key: str, default=None):
    row = db_one("SELECT v FROM kv WHERE k=?", (key,))
    return row["v"] if row else default


def kv_set(key: str, value: str) -> None:
    db_exec(
        "INSERT INTO kv(k, v) VALUES(?, ?) "
        "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (key, str(value)),
    )


init_db()
LOCATION_API_KEY = _env("LOCATION_API_KEY") or kv_get("location_api_key") or ""
if _env("LOCATION_API_KEY"):
    kv_set("location_api_key", LOCATION_API_KEY)

TRACKING_SINCE = int(kv_get("tracking_since") or time.time())


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #

def now_ts() -> int:
    return int(time.time())


def local_str(ts: int | float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(int(ts), TZ).strftime("%Y-%m-%d %H:%M:%S")


def ms_to_s(value) -> int:
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return value // 1000 if value > 10_000_000_000 else value


def chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def client_ip() -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
        real = request.headers.get("X-Real-IP", "")
        if real:
            return real.strip()
    return (request.remote_addr or "").strip()


_mm_session = requests.Session()
_mm_adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=32)
_mm_session.mount("http://", _mm_adapter)
_mm_session.mount("https://", _mm_adapter)


# --------------------------------------------------------------------------- #
# Mattermost API client
# --------------------------------------------------------------------------- #

class MMError(Exception):
    def __init__(self, status: int, message: str, mm_id: str | None = None,
                 details: str | None = None, login_required: bool = False):
        super().__init__(message)
        self.status = status
        self.message = message
        self.mm_id = mm_id
        self.details = details
        self.login_required = login_required


_UNSET = object()


def mm_request(method: str, path: str, token=_UNSET, params: dict | None = None,
               json_body=None, timeout: int = 25) -> requests.Response:
    if token is _UNSET:
        token = session.get("token")
    if not token:
        raise MMError(401, "You are not signed in.", "no_session", login_required=True)
    url = MM_API + path
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = _mm_session.request(method, url, headers=headers, params=params,
                                   json=json_body, timeout=timeout, verify=VERIFY_TLS)
    except requests.exceptions.SSLError:
        raise MMError(502, f"TLS error talking to Mattermost ({MM_URL}). "
                           "Set DASH_INSECURE_TLS=1 for self-signed certificates.")
    except requests.exceptions.ConnectionError:
        raise MMError(502, f"Cannot connect to Mattermost at {MM_URL}. Is the service running?")
    except requests.RequestException:
        raise MMError(502, f"Mattermost at {MM_URL} did not respond in time.")
    if resp.status_code >= 400:
        data: dict = {}
        try:
            data = resp.json()
        except ValueError:
            pass
        msg = (data.get("message") or "").strip() or resp.text.strip()[:300] or f"HTTP {resp.status_code}"
        raise MMError(resp.status_code, msg, data.get("id"), data.get("detailed_error"))
    return resp


_service_lock = threading.Lock()


def get_service_token() -> str | None:
    """Token used by background pollers / agent endpoints (no request context)."""
    if MM_ADMIN_TOKEN:
        return MM_ADMIN_TOKEN
    return kv_get("service_token")


def set_service_token(token: str) -> None:
    if MM_ADMIN_TOKEN or not token:
        return
    with _service_lock:
        kv_set("service_token", token)


class TTLCache:
    def __init__(self):
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: float):
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            ts, value = item
            if time.time() - ts > ttl:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value) -> None:
        with self._lock:
            self._store[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_cache = TTLCache()


def invalidate_caches() -> None:
    _cache.clear()


def handle_mm_errors(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except MMError as exc:
            if exc.status == 401 and session.get("token"):
                session.clear()
            payload = {
                "ok": False,
                "message": exc.message,
                "mm_id": exc.mm_id,
                "details": exc.details,
            }
            if exc.login_required or exc.status == 401:
                payload["login_required"] = True
            return jsonify(payload), exc.status
    return wrapper


# --------------------------------------------------------------------------- #
# Mattermost data access
# --------------------------------------------------------------------------- #

def mm_paged(path: str, per_page: int = 200, max_pages: int = 50,
             params: dict | None = None, token=_UNSET) -> list:
    items: list = []
    for page in range(max_pages):
        query = dict(params or {})
        query.update({"per_page": per_page, "page": page})
        resp = mm_request("GET", path, token=token, params=query)
        data = resp.json()
        if isinstance(data, dict):
            for key in ("teams", "users", "posts", "channels", "members"):
                if key in data:
                    data = data[key]
                    break
            else:
                data = []
        if not isinstance(data, list):
            break
        items.extend(data)
        if len(data) < per_page:
            break
    return items


def fetch_all_users(include_inactive: bool = False, token=_UNSET) -> list[dict]:
    users = mm_paged("/users", params={"active": "true"}, token=token, max_pages=20)
    if include_inactive:
        try:
            inactive = mm_paged("/users", params={"inactive": "true"}, token=token, max_pages=20)
            seen = {u["id"] for u in users}
            users.extend([u for u in inactive if u["id"] not in seen])
        except MMError:
            pass
    return users


def fetch_all_teams(token=_UNSET) -> list[dict]:
    teams = mm_paged("/teams", per_page=100, token=token, max_pages=10)
    return [t for t in teams if not t.get("delete_at")]


def fetch_team_members(team_id: str, token=_UNSET) -> list[dict]:
    try:
        return mm_paged(f"/teams/{team_id}/members", token=token, max_pages=10)
    except MMError:
        return []


def teams_snapshot(force: bool = False, token=_UNSET) -> dict:
    cached = None if force else _cache.get("teams_snapshot", ttl=20)
    if cached is not None:
        return cached
    # Resolve the token once, in the request thread: Flask's session proxy is not
    # available inside worker threads.
    if token is _UNSET:
        token = session.get("token")
    teams = fetch_all_teams(token=token)
    members_by_team: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_team_members, t["id"], token): t["id"] for t in teams}
        for fut, tid in futures.items():
            try:
                members_by_team[tid] = fut.result()
            except Exception:
                members_by_team[tid] = []
    teams_by_user: dict[str, list[str]] = {}
    for team in teams:
        member_ids = []
        for m in members_by_team.get(team["id"], []):
            uid = m.get("user_id")
            if not uid:
                continue
            member_ids.append(uid)
            teams_by_user.setdefault(uid, []).append(team["id"])
        team["member_ids"] = member_ids
        team["member_count"] = len(member_ids)
        # keep payload small
        for m in members_by_team.get(team["id"], []):
            if "roles" in m:
                team.setdefault("roles_by_user", {})[m["user_id"]] = m["roles"]
    snapshot = {"teams": teams, "teams_by_user": teams_by_user}
    _cache.set("teams_snapshot", snapshot)
    return snapshot


def fetch_statuses(user_ids: list[str], token=_UNSET) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for chunk in chunks([u for u in user_ids if u], 100):
        try:
            resp = mm_request("POST", "/users/status/ids", token=token, json_body=chunk)
            for item in resp.json():
                if item.get("user_id"):
                    out[item["user_id"]] = item
        except MMError:
            continue
    return out


def count_users_from_header(inactive: bool | None = None) -> int | None:
    params = {"per_page": 1}
    if inactive is True:
        params["inactive"] = "true"
    elif inactive is False:
        params["active"] = "true"
    try:
        resp = mm_request("GET", "/users", params=params)
        header = resp.headers.get("X-Total-Count") or resp.headers.get("x-total-count")
        if header is not None:
            return int(header)
    except (MMError, ValueError):
        return None
    return None


def server_info(force: bool = False) -> dict:
    cached = None if force else _cache.get("server_info", ttl=120)
    if cached is not None:
        return cached
    info = {"mm_url": MM_URL, "site_name": "", "version": "", "edition": "", "site_url": ""}
    try:
        resp = mm_request("GET", "/config")
        cfg = resp.json()
        info["version"] = resp.headers.get("X-Version-Id", "")
        info["site_name"] = (cfg.get("TeamSettings") or {}).get("SiteName") or ""
        info["site_url"] = (cfg.get("ServiceSettings") or {}).get("SiteURL") or ""
    except MMError:
        pass
    _cache.set("server_info", info)
    return info


# --------------------------------------------------------------------------- #
# Presence tracking
# --------------------------------------------------------------------------- #

def status_state_map() -> dict[str, dict]:
    rows = db_query("SELECT user_id, status, changed_at FROM status_state")
    return {r["user_id"]: r for r in rows}


def record_statuses(statuses: dict[str, dict]) -> int:
    now = now_ts()
    previous = status_state_map()
    changes = 0
    for uid, item in statuses.items():
        new_status = (item.get("status") or "offline").lower()
        prev = previous.get(uid)
        if prev and prev["status"] == new_status:
            continue
        db_exec(
            "INSERT INTO status_events(user_id, status, ts) VALUES(?,?,?)",
            (uid, new_status, now),
        )
        db_exec(
            "INSERT INTO status_state(user_id, status, changed_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET status=excluded.status, changed_at=excluded.changed_at",
            (uid, new_status, now),
        )
        changes += 1
    return changes


def run_status_poll() -> dict:
    token = get_service_token()
    ids = _cache.get("poll_user_ids", ttl=300)
    if not ids:
        try:
            users = fetch_all_users(include_inactive=False, token=token)
        except MMError as exc:
            return {"ok": False, "message": exc.message}
        ids = [u["id"] for u in users if not u.get("delete_at")]
        _cache.set("poll_user_ids", ids)
    if not ids:
        return {"ok": True, "updated": 0, "users": 0}
    statuses = fetch_statuses(ids, token=token)
    updated = record_statuses(statuses)
    return {"ok": True, "updated": updated, "users": len(statuses)}


def _poller_loop() -> None:
    # give the server a moment to boot
    time.sleep(3)
    while True:
        try:
            if get_service_token():
                run_status_poll()
        except Exception as exc:  # keep the poller alive no matter what
            app.logger.warning("status poll failed: %s", exc)
        time.sleep(STATUS_POLL_SECONDS)


_poller_started = False
_poller_lock = threading.Lock()


def start_poller() -> None:
    global _poller_started
    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True
    threading.Thread(target=_poller_loop, name="status-poller", daemon=True).start()


def compute_presence(hours: int = 24) -> dict[str, dict]:
    """Return per-user aggregated online time + intervals for the given window."""
    now = now_ts()
    start = now - hours * 3600
    events: dict[str, list[tuple[int, str]]] = {}
    rows = db_query(
        "SELECT user_id, status, ts FROM status_events WHERE ts >= ? ORDER BY user_id, ts",
        (start,),
    )
    for r in rows:
        events.setdefault(r["user_id"], []).append((r["ts"], r["status"]))
    baseline = db_query(
        "SELECT e.user_id, e.status, e.ts FROM status_events e "
        "JOIN (SELECT user_id, MAX(ts) AS mts FROM status_events WHERE ts < ? GROUP BY user_id) x "
        "ON e.user_id = x.user_id AND e.ts = x.mts",
        (start,),
    )
    for r in baseline:
        events.setdefault(r["user_id"], []).insert(0, (r["ts"], r["status"]))
    result: dict[str, dict] = {}
    for uid, evs in events.items():
        evs.sort()
        intervals = []
        online_seconds = 0
        for idx, (ts, status) in enumerate(evs):
            seg_start = max(ts, start)
            seg_end = evs[idx + 1][0] if idx + 1 < len(evs) else now
            if seg_end < seg_start:
                continue
            connected = status in ("online", "away", "dnd")
            if seg_end > seg_start:
                intervals.append({
                    "status": status,
                    "start": seg_start,
                    "end": min(seg_end, now),
                    "seconds": min(seg_end, now) - seg_start,
                })
                if connected:
                    online_seconds += min(seg_end, now) - seg_start
        last = evs[-1] if evs else None
        result[uid] = {
            "intervals": [i for i in intervals if i["end"] > i["start"]],
            "online_seconds": int(online_seconds),
            "last_status": last[1] if last else "offline",
            "last_change": last[0] if last else None,
            "last_seen": now if last and last[1] in ("online", "away", "dnd") else (last[0] if last else None),
        }
    return result


# --------------------------------------------------------------------------- #
# Geolocation
# --------------------------------------------------------------------------- #

_geo_lock = threading.Lock()
_geo_cache: dict[str, tuple[float, dict]] = {}


def is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)
    except ValueError:
        return True


def geolocate(ip: str) -> dict:
    ip = (ip or "").strip()
    if not ip or is_private_ip(ip) or not GEOIP_ENABLED:
        return {}
    with _geo_lock:
        cached = _geo_cache.get(ip)
        if cached and time.time() - cached[0] < 6 * 3600:
            return cached[1]
    result: dict = {}
    try:
        r = requests.get(f"https://ipwho.is/{ip}", timeout=7, verify=True,
                         headers={"User-Agent": "mm-admin-dashboard/1.0"})
        if r.ok:
            data = r.json()
            if data.get("success"):
                conn = data.get("connection") or {}
                result = {
                    "city": data.get("city") or "",
                    "region": data.get("region") or "",
                    "country": data.get("country") or "",
                    "country_code": data.get("country_code") or "",
                    "lat": data.get("latitude"),
                    "lon": data.get("longitude"),
                    "isp": conn.get("isp") or conn.get("org") or "",
                }
    except requests.RequestException:
        pass
    if not result:
        try:
            r = requests.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,countryCode,regionName,city,lat,lon,isp"},
                timeout=7,
                headers={"User-Agent": "mm-admin-dashboard/1.0"},
            )
            if r.ok:
                data = r.json()
                if data.get("status") == "success":
                    result = {
                        "city": data.get("city") or "",
                        "region": data.get("regionName") or "",
                        "country": data.get("country") or "",
                        "country_code": data.get("countryCode") or "",
                        "lat": data.get("lat"),
                        "lon": data.get("lon"),
                        "isp": data.get("isp") or "",
                    }
        except requests.RequestException:
            pass
    with _geo_lock:
        _geo_cache[ip] = (time.time(), result)
    return result


def record_location(user_id: str | None, username: str | None, ip: str | None = None,
                    lat=None, lon=None, accuracy=None, source: str = "manual",
                    hostname: str | None = None, raw=None, min_gap: int = 300,
                    allow_private: bool = True) -> int | None:
    ip = (ip or "").strip().split(",")[0].strip()
    if ip.startswith("::ffff:"):
        ip = ip[7:]
    private = is_private_ip(ip) if ip else True
    if private and not allow_private:
        return None
    now = now_ts()
    if lat is None or lon is None:
        if not ip:
            return None
        geo = geolocate(ip)
        if not geo:
            if private:
                geo = {"city": "Local network", "region": "", "country": "", "country_code": "",
                       "lat": None, "lon": None, "isp": ""}
            else:
                geo = {}
        lat = geo.get("lat")
        lon = geo.get("lon")
        city = geo.get("city") or ""
        region = geo.get("region") or ""
        country = geo.get("country") or ""
        country_code = geo.get("country_code") or ""
        isp = geo.get("isp") or ""
    else:
        geo = geolocate(ip) if (ip and not private) else {}
        city = geo.get("city") or ""
        region = geo.get("region") or ""
        country = geo.get("country") or ""
        country_code = geo.get("country_code") or ""
        isp = geo.get("isp") or ""
    # De-duplicate identical consecutive pings from the same source
    if ip:
        existing = db_one(
            "SELECT id, ts FROM location_pings WHERE COALESCE(user_id, username) IS ? "
            "AND ip = ? AND source = ? AND ts >= ? ORDER BY ts DESC LIMIT 1",
            (user_id or username, ip, source, now - min_gap),
        )
        if existing:
            return existing["id"]
    return db_exec(
        "INSERT INTO location_pings(user_id, username, ts, ip, is_private, lat, lon, accuracy, "
        "city, region, country, country_code, isp, source, hostname, raw) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, username, now, ip, 1 if private else 0, lat, lon, accuracy,
         city, region, country, country_code, isp, source, hostname,
         json.dumps(raw, ensure_ascii=False)[:2000] if raw else None),
    )


def latest_locations(limit: int = 200) -> list[dict]:
    return db_query(
        "SELECT * FROM ("
        "  SELECT *, ROW_NUMBER() OVER (PARTITION BY COALESCE(user_id, username) "
        "  ORDER BY ts DESC, id DESC) AS rn FROM location_pings"
        ") WHERE rn = 1 ORDER BY ts DESC LIMIT ?",
        (limit,),
    )


# --------------------------------------------------------------------------- #
# Read-only Mattermost database (for full DM visibility)
# --------------------------------------------------------------------------- #

def _dialect() -> tuple[str, str] | None:
    if not DATABASE_URL:
        return None
    scheme = DATABASE_URL.split(":", 1)[0].lower()
    if scheme in ("postgres", "postgresql"):
        return ("postgres", DATABASE_URL)
    if scheme in ("mysql", "mariadb"):
        return ("mysql", DATABASE_URL)
    return None


def _db_connect():
    info = _dialect()
    if not info:
        raise MMError(400, "No Mattermost database is configured. Set DATABASE_URL in .env "
                           "to enable full chat access.")
    kind, url = info
    try:
        if kind == "postgres":
            import psycopg2  # type: ignore
            conn = psycopg2.connect(url, connect_timeout=6)
            conn.set_session(readonly=True, autocommit=True)
            return kind, conn
        import pymysql  # type: ignore
        parsed = urlparse(url)
        conn = pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=(parsed.path or "/mattermost").lstrip("/"),
            connect_timeout=6,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
        return kind, conn
    except ImportError as exc:
        raise MMError(500, f"Database driver missing ({exc}). Re-run install.sh to install "
                           "psycopg2-binary / PyMySQL.")
    except Exception as exc:
        raise MMError(502, f"Cannot connect to the Mattermost database: {exc}")


def db_rows(sql_pg: str, sql_mysql: str, params: tuple = ()) -> list[dict]:
    kind, conn = _db_connect()
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql_pg if kind == "postgres" else sql_mysql, params)
            rows = cur.fetchall()
        except Exception as exc:
            raise MMError(502, f"Mattermost database query failed: {exc}")
        if kind == "postgres":
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in rows]
        return [dict(row) for row in rows]
    finally:
        try:
            conn.close()
        except Exception:
            pass


def chat_backend_info(test: bool = False) -> dict:
    info = {"mode": "api", "configured": bool(DATABASE_URL), "db_ok": False,
            "dialect": (_dialect() or [None])[0], "error": None}
    if DATABASE_URL:
        info["mode"] = "db"
        if test:
            try:
                db_rows("SELECT 1 AS ok", "SELECT 1 AS ok")
                info["db_ok"] = True
            except MMError as exc:
                info["error"] = exc.message
    return info


def db_chat_partners(user_id: str) -> list[dict]:
    partners = db_rows(
        "SELECT c.id, c.name, c.lastpostat FROM channels c "
        "JOIN channelmembers cm ON cm.channelid = c.id "
        "WHERE cm.userid = %s AND c.type = 'D' AND c.deleteat = 0 "
        "ORDER BY c.lastpostat DESC LIMIT 300",
        "SELECT c.Id AS id, c.Name AS name, c.LastPostAt AS lastpostat FROM Channels c "
        "JOIN ChannelMembers cm ON cm.ChannelId = c.Id "
        "WHERE cm.UserId = %s AND c.Type = 'D' AND c.DeleteAt = 0 "
        "ORDER BY c.LastPostAt DESC LIMIT 300",
        (user_id,),
    )
    if not partners:
        return []

    def last_msg(channel: dict) -> dict:
        rows = db_rows(
            "SELECT userid, message, createat, deleteat, props FROM posts "
            "WHERE channelid = %s ORDER BY createat DESC LIMIT 1",
            "SELECT UserId AS userid, Message AS message, CreateAt AS createat, "
            "DeleteAt AS deleteat, Props AS props FROM Posts WHERE ChannelId = %s "
            "ORDER BY CreateAt DESC LIMIT 1",
            (channel["id"],),
        )
        last = rows[0] if rows else None
        if last and not (last.get("message") or "").strip():
            last["message"] = props_display_text(last.get("props"))[0]
        channel["last_message"] = last
        counts = db_rows(
            "SELECT COUNT(*) AS n FROM posts WHERE channelid = %s AND deleteat > 0",
            "SELECT COUNT(*) AS n FROM Posts WHERE ChannelId = %s AND DeleteAt > 0",
            (channel["id"],),
        )
        channel["deleted_count"] = int((counts[0]["n"] if counts else 0) or 0)
        return channel

    with ThreadPoolExecutor(max_workers=8) as pool:
        partners = list(pool.map(last_msg, partners))
    out = []
    for p in partners:
        parts = (p.get("name") or "").split("__")
        other = next((x for x in parts if x and x != user_id), None)
        if not other:
            continue
        p["partner_id"] = other
        p["last_post_at"] = ms_to_s((p.get("last_message") or {}).get("createat")
                                    or p.get("lastpostat"))
        last = p.get("last_message") or {}
        p["preview"] = (last.get("message") or "")[:120]
        p["preview_deleted"] = bool(last.get("deleteat"))
        p["deleted_count"] = p.get("deleted_count") or 0
        out.append(p)
    out.sort(key=lambda x: x.get("last_post_at") or 0, reverse=True)
    return out


def media_root() -> str | None:
    """Directory where Mattermost keeps uploaded files (FileSettings.Directory)."""
    candidates = [MM_DATA_DIR] if MM_DATA_DIR else []
    candidates += ["/opt/mattermost/data", "/var/opt/mattermost/data",
                   "/mattermost/data", "/srv/mattermost/data"]
    for cand in candidates:
        if cand and os.path.isdir(cand) and os.access(cand, os.R_OK | os.X_OK):
            return cand
    return None


def safe_media_path(rel_path: str) -> str | None:
    """Resolve a fileinfo.path inside the media root, refusing traversal."""
    root = media_root()
    if not root or not rel_path:
        return None
    root_real = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_real, rel_path.lstrip("/\\")))
    if target != root_real and not target.startswith(root_real + os.sep):
        return None
    return target if os.path.isfile(target) else None


def shape_file(row: dict) -> dict:
    size = row.get("size") or 0
    mime = row.get("mimetype") or ""
    return {
        "id": row.get("id"),
        "name": row.get("name") or "attachment",
        "ext": (row.get("extension") or "").lower(),
        "size": int(size or 0),
        "mime": mime,
        "width": row.get("width") or 0,
        "height": row.get("height") or 0,
        "is_image": mime.startswith("image/") or (row.get("extension") or "").lower() in
                    ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"),
        "deleted": bool(row.get("deleteat")),
    }


def db_files_for_posts(post_ids: list[str]) -> dict:
    """post_id -> [attachment metadata] from the fileinfo table."""
    if not post_ids:
        return {}
    marks = ",".join(["%s"] * len(post_ids))
    rows = db_rows(
        f"SELECT id, postid, name, extension, size, mimetype, width, height, deleteat, path "
        f"FROM fileinfo WHERE postid IN ({marks}) ORDER BY createat ASC",
        f"SELECT Id AS id, PostId AS postid, Name AS name, Extension AS extension, "
        f"Size AS size, MimeType AS mimetype, Width AS width, Height AS height, "
        f"DeleteAt AS deleteat, Path AS path FROM FileInfo WHERE PostId IN ({marks}) "
        f"ORDER BY CreateAt ASC",
        tuple(post_ids),
    )
    out: dict = {}
    for r in rows:
        entry = shape_file(r)
        entry["path"] = r.get("path") or ""
        out.setdefault(r["postid"], []).append(entry)
    return out


def props_display_text(raw) -> tuple[str, dict]:
    """Plugin posts (e.g. Calls) keep their visible text in `props`, not `message`.
    Return a human-readable string from props plus the parsed dict."""
    props: dict = {}
    if isinstance(raw, dict):
        props = raw
    elif isinstance(raw, (str, bytes)) and str(raw).strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                props = parsed
        except (ValueError, TypeError):
            props = {}
    for key in ("call", "content", "text", "title", "message", "body", "description"):
        val = props.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip(), props
    return "", props


def db_chat_posts(channel_id: str, page: int = 0, per_page: int = 60) -> dict:
    ch = db_rows(
        "SELECT id, name, type FROM channels WHERE id = %s",
        "SELECT Id AS id, Name AS name, Type AS type FROM Channels WHERE Id = %s",
        (channel_id,),
    )
    if not ch:
        raise MMError(404, "Channel not found.")
    if ch[0].get("type") != "D":
        raise MMError(400, "Only direct-message channels are supported.")
    total = db_rows(
        "SELECT COUNT(*) AS n FROM posts WHERE channelid = %s",
        "SELECT COUNT(*) AS n FROM Posts WHERE ChannelId = %s",
        (channel_id,),
    )[0]["n"]
    deleted_total = db_rows(
        "SELECT COUNT(*) AS n FROM posts WHERE channelid = %s AND deleteat > 0",
        "SELECT COUNT(*) AS n FROM Posts WHERE ChannelId = %s AND DeleteAt > 0",
        (channel_id,),
    )[0]["n"]
    rows = db_rows(
        "SELECT id, createat, userid, message, deleteat, type, rootid, updateat, props "
        "FROM posts WHERE channelid = %s ORDER BY createat DESC LIMIT %s OFFSET %s",
        "SELECT Id AS id, CreateAt AS createat, UserId AS userid, Message AS message, "
        "DeleteAt AS deleteat, Type AS type, RootId AS rootid, UpdateAt AS updateat, "
        "Props AS props FROM Posts WHERE ChannelId = %s "
        "ORDER BY CreateAt DESC LIMIT %s OFFSET %s",
        (channel_id, per_page, page * per_page),
    )
    files_by_post = {}
    try:
        files_by_post = db_files_for_posts([r["id"] for r in rows])
    except MMError:
        files_by_post = {}   # older schema / no permission: chat still works

    posts = []
    for r in rows:
        msg = (r.get("message") or "").strip()
        props_text, props = props_display_text(r.get("props"))
        posts.append({
            "files": files_by_post.get(r["id"], []),
            "id": r["id"],
            "create_at": ms_to_s(r["createat"]),
            "user_id": r["userid"],
            "message": msg or props_text,
            "deleted": bool(r.get("deleteat")),
            "delete_at": ms_to_s(r.get("deleteat")) or 0,
            "type": r.get("type") or "",
            "is_system": (r.get("type") or "").startswith("system_"),
            # True when the server kept the original text for a deleted post
            "text_available": bool(msg or props_text),
            "from_props": bool(not msg and props_text),
            "props": props,
        })
    posts.reverse()
    return {
        "channel_id": channel_id,
        "channel_name": ch[0].get("name"),
        "posts": posts,
        "page": page,
        "per_page": per_page,
        "total": int(total or 0),
        "deleted_total": int(deleted_total or 0),
        "has_more": (page + 1) * per_page < int(total or 0),
        "mode": "db",
    }


def chat_partners_via_api(user_id: str) -> tuple[list[dict], str | None]:
    warning = None
    try:
        channels = mm_paged(f"/users/{user_id}/channels", per_page=200, max_pages=5)
    except MMError as exc:
        raise MMError(exc.status, f"Cannot list channels for this user: {exc.message}")
    dm_channels = [c for c in channels if c.get("type") == "D" and not c.get("delete_at")]
    out = []
    for ch in dm_channels:
        parts = (ch.get("name") or "").split("__")
        other = next((x for x in parts if x and x != user_id), None)
        if not other:
            continue
        entry = {
            "id": ch["id"],
            "channel_id": ch["id"],
            "partner_id": other,
            "last_post_at": ms_to_s(ch.get("last_post_at")),
            "preview": "",
            "last_message": None,
        }
        try:
            resp = mm_request("GET", f"/channels/{ch['id']}/posts", params={"page": 0, "per_page": 1})
            data = resp.json()
            order = data.get("order") or []
            if order:
                post = (data.get("posts") or {}).get(order[0]) or {}
                entry["preview"] = (post.get("message") or "")[:120]
                entry["preview_deleted"] = bool(post.get("delete_at"))
                entry["deleted_count"] = None  # the API does not expose totals
                entry["last_post_at"] = ms_to_s(post.get("create_at")) or entry["last_post_at"]
        except MMError as exc:
            if exc.status == 403:
                warning = ("The Mattermost API does not allow a System Admin to read other users' "
                           "direct messages. Configure DATABASE_URL to enable full chat access.")
        out.append(entry)
    out.sort(key=lambda x: x.get("last_post_at") or 0, reverse=True)
    return out, warning


def chat_posts_via_api(channel_id: str, page: int = 0, per_page: int = 60) -> dict:
    try:
        resp = mm_request("GET", f"/channels/{channel_id}/posts",
                          params={"page": page, "per_page": per_page})
    except MMError as exc:
        if exc.status == 403:
            raise MMError(403, "Access denied by Mattermost. A System Admin cannot read direct "
                               "messages they are not part of through the REST API. Add "
                               "DATABASE_URL in .env to read chats directly from the database.")
        raise
    data = resp.json()
    posts = []
    for pid in (data.get("order") or []):
        p = (data.get("posts") or {}).get(pid) or {}
        msg = (p.get("message") or "").strip()
        props_text, props = props_display_text(p.get("props"))
        api_files = (p.get("metadata") or {}).get("files") or []
        files = [shape_file({"id": f.get("id"), "name": f.get("name"),
                             "extension": f.get("extension"), "size": f.get("size"),
                             "mimetype": f.get("mime_type"), "width": f.get("width"),
                             "height": f.get("height"), "deleteat": 0})
                 for f in api_files]
        posts.append({
            "files": files,
            "id": p.get("id"),
            "create_at": ms_to_s(p.get("create_at")),
            "user_id": p.get("user_id"),
            "message": msg or props_text,
            "deleted": bool(p.get("delete_at")),
            "delete_at": ms_to_s(p.get("delete_at")) or 0,
            "type": p.get("type") or "",
            "is_system": (p.get("type") or "").startswith("system_"),
            "text_available": bool(msg or props_text),
            "from_props": bool(not msg and props_text),
            "props": props,
        })
    posts.reverse()
    return {"channel_id": channel_id, "posts": posts, "page": page, "per_page": per_page,
            "has_more": len(posts) == per_page, "total": None,
            "deleted_total": sum(1 for x in posts if x["deleted"]), "mode": "api"}


# --------------------------------------------------------------------------- #
# mmctl bridge (optional)
# --------------------------------------------------------------------------- #

def find_mmctl() -> str | None:
    """Locate the mmctl binary so the dashboard can run operations the REST API
    forbids (permanent deletion, direct password resets, etc.)."""
    candidates = [MMCTL_PATH] if MMCTL_PATH else []
    candidates += ["/opt/mattermost/bin/mmctl", "/usr/local/bin/mmctl", "/usr/bin/mmctl",
                   "/usr/local/sbin/mmctl", "mmctl"]
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.sep in candidate:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        else:
            found = shutil.which(candidate)
            if found:
                return found
    # mmctl is often reachable through the system user "mattermost"
    if shutil.which("runuser") and os.path.exists("/opt/mattermost/bin/mmctl"):
        return "/opt/mattermost/bin/mmctl"
    return None


def mmctl_available() -> bool:
    return find_mmctl() is not None


def run_mmctl(args: list[str], timeout: int = 45) -> tuple[bool, str]:
    """Run mmctl with --local (needs to run as the mattermost OS user)."""
    binary = find_mmctl()
    if not binary:
        return False, ("mmctl was not found on this server. Set MMCTL_PATH in .env or install "
                       "mmctl next to your Mattermost binary.")
    base = [binary, "--local"]
    commands: list[list[str]] = [base + args]
    if os.geteuid() == 0 and shutil.which("runuser"):
        # mmctl --local must run as the Mattermost system user
        commands.append(["runuser", "-u", MM_OS_USER, "--"] + base + args)
    elif os.geteuid() != 0 and shutil.which("sudo"):
        # install.sh grants this one command through a sudoers drop-in
        commands.append(["sudo", "-n", "-u", MM_OS_USER, "--"] + base + args)
    last_error = ""
    for command in commands:
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            last_error = f"{command[0]} not found"
            continue
        except subprocess.TimeoutExpired:
            last_error = "mmctl timed out"
            continue
        except Exception as exc:
            last_error = str(exc)
            continue
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if proc.returncode == 0:
            return True, output
        last_error = output or f"mmctl exited with code {proc.returncode}"
    return False, last_error


# --------------------------------------------------------------------------- #
# Audit log (dashboard actions)
# --------------------------------------------------------------------------- #

def username_of(state: dict | None, fallback: str) -> str:
    return (state or {}).get("username") or fallback


def probe_user(user_id: str) -> dict:
    """Current state of a user on the Mattermost server: exists? delete_at?"""
    try:
        data = mm_request("GET", f"/users/{user_id}").json()
    except MMError as exc:
        if exc.status == 404:
            return {"exists": False, "delete_at": 0, "username": None}
        raise
    return {"exists": True,
            "delete_at": int(data.get("delete_at") or 0),
            "username": data.get("username"),
            "active": not bool(data.get("delete_at"))}


def probe_team(team_id: str) -> dict:
    try:
        data = mm_request("GET", f"/teams/{team_id}").json()
    except MMError as exc:
        if exc.status == 404:
            return {"exists": False, "delete_at": 0, "name": None}
        raise
    return {"exists": True,
            "delete_at": int(data.get("delete_at") or 0),
            "name": data.get("name"),
            "active": not bool(data.get("delete_at"))}


def log_admin(action: str, target: str = "", details: str | dict | int = "") -> None:
    if isinstance(details, (dict, list)):
        details = json.dumps(details, ensure_ascii=False)
    elif not isinstance(details, str):
        details = str(details or "")
    db_exec(
        "INSERT INTO audit_log(ts, actor, actor_id, action, target, details, ip) "
        "VALUES(?,?,?,?,?,?,?)",
        (now_ts(), session.get("username"), session.get("user_id"), action,
         target, details[:1000], client_ip()),
    )


# --------------------------------------------------------------------------- #
# Auth helpers
# --------------------------------------------------------------------------- #

def api_login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("token"):
            return jsonify({"ok": False, "login_required": True,
                            "message": "Please sign in."}), 401
        return fn(*args, **kwargs)
    return wrapper


_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _login_lock:
        attempts = [t for t in _login_attempts.get(ip, []) if now - t < 600]
        _login_attempts[ip] = attempts
        return len(attempts) >= 8


def _note_attempt(ip: str, success: bool) -> None:
    now = time.time()
    with _login_lock:
        if success:
            _login_attempts.pop(ip, None)
        else:
            _login_attempts.setdefault(ip, []).append(now)


_MFA_HINTS = ("mfa", "multi-factor", "multifactor")


def _is_mfa_error(status: int, payload: dict) -> bool:
    text = f"{payload.get('id', '')} {payload.get('message', '')}".lower()
    return status == 401 and any(h in text for h in _MFA_HINTS)


@app.before_request
def _guard_api():
    if request.path.startswith("/api/"):
        if request.path in ("/api/login", "/api/track/location"):
            return None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            token = request.headers.get("X-CSRF-Token", "")
            if not session.get("csrf") or not secrets.compare_digest(str(session.get("csrf")), token):
                return jsonify({"ok": False, "message": "Invalid or missing CSRF token."}), 403
        if request.path != "/api/session" and not session.get("token"):
            return jsonify({"ok": False, "login_required": True,
                            "message": "Please sign in."}), 401
    return None


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #

@app.get("/")
def index():
    if not session.get("token"):
        return render_template("login.html", mm_url=MM_URL, version=APP_VERSION,
                               asset_version=ASSET_VERSION)
    boot = {
        "csrf": session.get("csrf"),
        "user": {
            "id": session.get("user_id"),
            "username": session.get("username"),
            "name": session.get("name"),
            "roles": session.get("roles"),
        },
        "mm_url": MM_URL,
        "tz": APP_TZ,
        "version": APP_VERSION,
        "chat_mode": "db" if DATABASE_URL else "api",
        "poll_seconds": STATUS_POLL_SECONDS,
    }
    return render_template("index.html", boot=boot, version=APP_VERSION,
                           asset_version=ASSET_VERSION)


@app.get("/health")
def health():
    return jsonify({"ok": True, "version": APP_VERSION, "mm_url": MM_URL,
                    "db": bool(DATABASE_URL)})


# --------------------------------------------------------------------------- #
# Auth routes
# --------------------------------------------------------------------------- #

@app.post("/api/login")
def api_login():
    ip = client_ip()
    if _rate_limited(ip):
        return jsonify({"ok": False, "message": "Too many failed attempts. "
                                                "Wait a few minutes and try again."}), 429
    data = request.get_json(silent=True) or {}
    login_id = (data.get("login_id") or "").strip()
    password = data.get("password") or ""
    mfa_code = (data.get("mfa_code") or "").strip()
    if not login_id or not password:
        return jsonify({"ok": False, "message": "Enter your Mattermost username/email and password."}), 400

    endpoint = "/users/login/mfa" if mfa_code else "/users/login"
    body: dict = {"login_id": login_id, "password": password}
    if mfa_code:
        body["token"] = mfa_code
    try:
        resp = requests.post(MM_API + endpoint, json=body, timeout=20, verify=VERIFY_TLS)
    except requests.exceptions.SSLError:
        return jsonify({"ok": False, "message": f"TLS error talking to Mattermost at {MM_URL}. "
                                                "If the server uses a self-signed certificate, set "
                                                "DASH_INSECURE_TLS=1 in .env and restart the dashboard."}), 502
    except requests.exceptions.ConnectionError:
        return jsonify({"ok": False, "message": f"Cannot connect to Mattermost at {MM_URL}. "
                                                "Check that the Mattermost service is running and that "
                                                "MM_URL in .env is correct."}), 502
    except requests.RequestException:
        return jsonify({"ok": False, "message": f"Mattermost at {MM_URL} did not respond in time. "
                                                "Check the server and try again."}), 502

    payload: dict = {}
    try:
        payload = resp.json()
    except ValueError:
        pass

    if resp.status_code >= 400:
        if not mfa_code and _is_mfa_error(resp.status_code, payload):
            return jsonify({"ok": False, "mfa_required": True,
                            "message": "Enter the 6-digit code from your authenticator app."}), 401
        _note_attempt(ip, False)
        message = payload.get("message") or "The username or password is incorrect."
        if resp.status_code == 401:
            message = "The username or password is incorrect."
        return jsonify({"ok": False, "message": message}), resp.status_code

    token = resp.headers.get("Token") or resp.headers.get("token") or ""
    user = payload or {}
    roles = user.get("roles") or ""
    if "system_admin" not in roles.split():
        _note_attempt(ip, False)
        return jsonify({"ok": False, "message": "This account is not a Mattermost System Admin. "
                                                "Use an account with the System Admin role."}), 403
    if not token:
        return jsonify({"ok": False, "message": "Mattermost did not return a session token."}), 502

    session.clear()
    session.permanent = True
    session["token"] = token
    session["user_id"] = user.get("id")
    session["username"] = user.get("username")
    session["name"] = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) \
        or user.get("username")
    session["roles"] = roles
    session["csrf"] = secrets.token_urlsafe(32)
    set_service_token(token)
    _note_attempt(ip, True)
    invalidate_caches()
    try:
        log_admin("login", target=user.get("username", login_id), details="Dashboard sign-in")
    except Exception:
        pass

    # Track this admin's login location without slowing the login response
    def _track_login(uid=user.get("id"), uname=user.get("username"), login_ip=ip):
        try:
            record_location(uid, uname, ip=login_ip, source="dashboard-login")
        except Exception:
            pass
    threading.Thread(target=_track_login, daemon=True).start()

    return jsonify({
        "ok": True,
        "user": {"id": user.get("id"), "username": user.get("username"),
                 "name": session["name"], "roles": roles},
        "csrf": session["csrf"],
    })


@app.post("/api/logout")
@api_login_required
def api_logout():
    try:
        log_admin("logout", target=session.get("username", ""))
    except Exception:
        pass
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/session")
@handle_mm_errors
def api_session():
    if not session.get("token"):
        return jsonify({"ok": False, "login_required": True}), 401
    try:
        me = mm_request("GET", "/users/me").json()
    except MMError as exc:
        if exc.status == 401:
            session.clear()
            return jsonify({"ok": False, "login_required": True}), 401
        raise
    session["username"] = me.get("username", session.get("username"))
    session["roles"] = me.get("roles", session.get("roles"))
    return jsonify({
        "ok": True,
        "user": {"id": me.get("id"), "username": me.get("username"),
                 "name": " ".join(filter(None, [me.get("first_name"), me.get("last_name")]))
                         or me.get("username"),
                 "roles": me.get("roles")},
        "csrf": session.get("csrf"),
        "mm_url": MM_URL,
        "tz": APP_TZ,
        "version": APP_VERSION,
        "poll_seconds": STATUS_POLL_SECONDS,
        "chat_mode": "db" if DATABASE_URL else "api",
    })


# --------------------------------------------------------------------------- #
# Users + teams
# --------------------------------------------------------------------------- #

def _enrich_users(users: list[dict], teams_snap: dict, statuses: dict[str, dict]) -> list[dict]:
    states = status_state_map()
    pings = {p["user_id"]: p for p in latest_locations(limit=1000) if p.get("user_id")}
    teams_by_user = teams_snap.get("teams_by_user", {})
    now = now_ts()
    enriched = []
    for u in users:
        uid = u.get("id")
        st = statuses.get(uid) or {}
        state = states.get(uid) or {}
        if u.get("delete_at"):
            status = "offline"
        else:
            status = (st.get("status") or state.get("status") or "offline").lower()
        if state:
            if status in ("online", "away", "dnd"):
                last_seen = now
            else:
                last_seen = state.get("changed_at")
        else:
            last_seen = None
        ping = pings.get(uid)
        enriched.append({
            "id": uid,
            "username": u.get("username"),
            "email": u.get("email"),
            "first_name": u.get("first_name") or "",
            "last_name": u.get("last_name") or "",
            "nickname": u.get("nickname") or "",
            "roles": u.get("roles") or "",
            "is_admin": "system_admin" in (u.get("roles") or "").split(),
            "is_guest": "system_guest" in (u.get("roles") or "").split(),
            "is_bot": bool(u.get("is_bot")) or "system_bot" in (u.get("roles") or "").split(),
            "active": not bool(u.get("delete_at")),
            "delete_at": u.get("delete_at") or 0,
            "create_at": ms_to_s(u.get("create_at")),
            "last_activity_at": ms_to_s(st.get("last_activity_at")),
            "status": status,
            "status_manual": bool(st.get("manual")),
            "status_changed_at": state.get("changed_at"),
            "last_seen": last_seen,
            "team_ids": teams_by_user.get(uid, []),
            "location": {
                "ts": ping.get("ts"),
                "ip": ping.get("ip"),
                "city": ping.get("city"),
                "region": ping.get("region"),
                "country": ping.get("country"),
                "country_code": ping.get("country_code"),
                "lat": ping.get("lat"),
                "lon": ping.get("lon"),
                "source": ping.get("source"),
                "is_private": bool(ping.get("is_private")),
            } if ping else None,
        })
    enriched.sort(key=lambda x: (x["active"] is False, (x["username"] or "").lower()))
    return enriched


def _build_bundle(include_inactive: bool = True, refresh: bool = False) -> dict:
    cache_key = f"bundle_{int(include_inactive)}"
    if not refresh:
        cached = _cache.get(cache_key, ttl=8)
        if cached is not None:
            return cached
    users_raw = fetch_all_users(include_inactive=include_inactive)
    teams_snap = teams_snapshot(force=refresh)
    active_ids = [u["id"] for u in users_raw if not u.get("delete_at")]
    statuses = fetch_statuses(active_ids)
    users = _enrich_users(users_raw, teams_snap, statuses)
    visible = [u for u in users if not u["is_bot"]]
    counts = {
        "total_users": len(visible),
        "active_users": len([u for u in visible if u["active"]]),
        "inactive_users": len([u for u in visible if not u["active"]]),
        "admins": len([u for u in visible if u["is_admin"] and u["active"]]),
        "bots": len([u for u in users if u["is_bot"]]),
        "teams": len(teams_snap["teams"]),
        "online": len([u for u in visible if u["active"] and u["status"] != "offline"]),
    }
    bundle = {
        "users": visible,
        "teams": teams_snap["teams"],
        "counts": counts,
        "fetched_at": now_ts(),
        "tracking_since": TRACKING_SINCE,
        "chat_mode": "db" if DATABASE_URL else "api",
    }
    _cache.set(cache_key, bundle)
    return bundle


@app.get("/api/users")
@api_login_required
@handle_mm_errors
def api_users():
    include_inactive = request.args.get("include_inactive", "1") != "0"
    refresh = request.args.get("refresh") == "1"
    bundle = _build_bundle(include_inactive=include_inactive, refresh=refresh)
    return jsonify(bundle)


@app.get("/api/users/<user_id>/detail")
@api_login_required
@handle_mm_errors
def api_user_detail(user_id: str):
    user = mm_request("GET", f"/users/{user_id}").json()
    teams = []
    sessions = []
    try:
        teams = mm_request("GET", f"/users/{user_id}/teams").json()
    except MMError:
        pass
    try:
        sessions = mm_request("GET", f"/users/{user_id}/sessions").json()
        sessions = [{
            "id": s.get("id"),
            "create_at": ms_to_s(s.get("create_at")),
            "expires_at": ms_to_s(s.get("expires_at")),
            "last_activity_at": ms_to_s(s.get("last_activity_at")),
            "props": s.get("props") or {},
        } for s in sessions]
        sessions.sort(key=lambda s: s.get("last_activity_at") or 0, reverse=True)
    except MMError:
        pass
    last_activity = max([s.get("last_activity_at") or 0 for s in sessions] or [0])
    history = db_query(
        "SELECT ts, ip, is_private, city, region, country, lat, lon, source, username "
        "FROM location_pings WHERE user_id = ? OR (user_id IS NULL AND username = ?) "
        "ORDER BY ts DESC LIMIT 100",
        (user_id, user.get("username") or ""),
    )
    status_history = db_query(
        "SELECT status, ts FROM status_events WHERE user_id = ? ORDER BY ts DESC LIMIT 200",
        (user_id,),
    )
    status_history.reverse()
    return jsonify({
        "ok": True,
        "user": {
            "id": user.get("id"),
            "username": user.get("username"),
            "email": user.get("email"),
            "first_name": user.get("first_name") or "",
            "last_name": user.get("last_name") or "",
            "nickname": user.get("nickname") or "",
            "roles": user.get("roles") or "",
            "create_at": ms_to_s(user.get("create_at")),
            "delete_at": user.get("delete_at") or 0,
            "is_admin": "system_admin" in (user.get("roles") or "").split(),
        },
        "teams": [{"id": t.get("id"), "name": t.get("name"),
                   "display_name": t.get("display_name"), "type": t.get("type")} for t in teams],
        "sessions": sessions,
        "last_activity": last_activity,
        "locations": history,
        "status_history": status_history,
    })


def _team_error(team_query: str) -> Response:
    return jsonify({
        "ok": False,
        "code": "TEAM_NOT_FOUND",
        "team_query": team_query,
        "message": f'Team "{team_query}" does not exist. Create the team first, then add the user.',
    }), 404


def resolve_team(team_query: str, teams: list[dict]) -> dict | None:
    q = (team_query or "").strip().lower()
    if not q:
        return None
    for t in teams:
        if (t.get("id", "").lower() == q
                or (t.get("name") or "").lower() == q
                or (t.get("display_name") or "").lower() == q):
            return t
    return None


@app.post("/api/users")
@api_login_required
@handle_mm_errors
def api_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    team_query = (data.get("team") or "").strip()
    team_role = data.get("team_role") or "member"
    make_admin = bool(data.get("system_admin"))
    if not username or not email or not password:
        return jsonify({"ok": False, "message": "Username, email and password are required."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "message": "Password must be at least 8 characters."}), 400

    team = None
    if team_query:
        snap = teams_snapshot(force=True)
        team = resolve_team(team_query, snap["teams"])
        if not team:
            return _team_error(team_query)

    body = {
        "username": username,
        "email": email,
        "password": password,
        "first_name": (data.get("first_name") or "").strip(),
        "last_name": (data.get("last_name") or "").strip(),
    }
    user = mm_request("POST", "/users", json_body=body).json()

    warnings = []
    if make_admin:
        try:
            mm_request("PUT", f"/users/{user['id']}/roles",
                       json_body={"roles": "system_user system_admin"})
        except MMError as exc:
            warnings.append(f"User created, but could not grant System Admin: {exc.message}")
    if team:
        try:
            mm_request("POST", f"/teams/{team['id']}/members",
                       json_body={"team_id": team["id"], "user_id": user["id"]})
            if team_role == "team_admin":
                mm_request("PUT", f"/teams/{team['id']}/members/{user['id']}/roles",
                           json_body={"roles": "team_user team_admin"})
        except MMError as exc:
            warnings.append(f"User created, but could not add to team: {exc.message}")

    invalidate_caches()
    log_admin("user.create", target=username,
              details={"email": email, "team": team.get("name") if team else None,
                       "team_role": team_role, "system_admin": make_admin})
    return jsonify({"ok": True, "user": {"id": user.get("id"), "username": user.get("username"),
                                         "email": user.get("email")},
                    "team": {"id": team["id"], "name": team["name"],
                             "display_name": team.get("display_name")} if team else None,
                    "warnings": warnings}), 201


@app.put("/api/users/<user_id>/active")
@api_login_required
@handle_mm_errors
def api_user_active(user_id: str):
    data = request.get_json(silent=True) or {}
    active = bool(data.get("active"))
    if user_id == session.get("user_id") and not active:
        return jsonify({"ok": False, "message": "You cannot deactivate your own account."}), 400
    mm_request("PUT", f"/users/{user_id}/active", json_body={"active": active})
    invalidate_caches()
    log_admin("user.activate" if active else "user.deactivate", target=user_id)
    return jsonify({"ok": True})


@app.delete("/api/users/<user_id>")
@api_login_required
@handle_mm_errors
def api_user_delete(user_id: str):
    if user_id == session.get("user_id"):
        return jsonify({"ok": False, "message": "You cannot delete your own account."}), 400
    permanent = request.args.get("permanent") == "1"
    before = probe_user(user_id)
    api_error = ""
    mmctl_error = ""

    if permanent:
        # 1) Ask Mattermost to delete for good.
        try:
            mm_request("DELETE", f"/users/{user_id}", params={"permanent": "true"})
        except MMError as exc:
            if exc.status not in (400, 403, 404, 500, 501):
                raise
            api_error = exc.message

        after = probe_user(user_id)
        # Some builds answer 200 but only deactivate. Verify, then escalate.
        if after["exists"]:
            username = after.get("username") or (before or {}).get("username") or user_id
            ok, output = run_mmctl(["user", "delete", username, "--confirm"])
            mmctl_error = "" if ok else output
            after = probe_user(user_id)

        if not after["exists"]:
            invalidate_caches()
            log_admin("user.delete_permanent", target=user_id, details={"api_error": api_error})
            return jsonify({"ok": True, "result": "deleted", "username": username_of(before, user_id)})

        # Still there: report the truth instead of pretending it worked.
        if after.get("delete_at"):
            invalidate_caches()
            log_admin("user.deactivate", target=user_id,
                      details={"requested": "permanent", "api_error": api_error,
                               "mmctl_error": mmctl_error})
            return jsonify({
                "ok": True,
                "result": "deactivated",
                "warning": ("The account was deactivated, not permanently deleted. "
                            "Mattermost refuses permanent deletion while "
                            "ServiceSettings.EnableAPIUserDeletion is false, and the dashboard "
                            "could not run mmctl"
                            + (f" ({mmctl_error[:160]})" if mmctl_error else "") +
                            ". The user disappears from Mattermost and can no longer sign in, "
                            "but the account still exists. To really delete it: enable "
                            "EnableAPIUserDeletion in config.json, or install mmctl, then try again."),
                "api_error": api_error,
                "mmctl_error": mmctl_error,
            })
        return jsonify({
            "ok": False,
            "code": "DELETE_NOT_APPLIED",
            "message": ("Mattermost did not delete or deactivate this account."
                        + (f" API said: {api_error}" if api_error else "")
                        + (f" mmctl said: {mmctl_error[:200]}" if mmctl_error else "")),
        }), 400

    # Soft delete (deactivate)
    try:
        mm_request("PUT", f"/users/{user_id}/active", json_body={"active": False})
    except MMError as exc:
        api_error = exc.message
        if exc.status not in (400, 403, 500):
            raise
    after = probe_user(user_id)
    if after.get("exists") and after.get("delete_at"):
        invalidate_caches()
        log_admin("user.deactivate", target=user_id)
        return jsonify({"ok": True, "result": "deactivated"})
    if not after["exists"]:
        invalidate_caches()
        log_admin("user.delete_permanent", target=user_id)
        return jsonify({"ok": True, "result": "deleted"})
    return jsonify({
        "ok": False,
        "code": "DEACTIVATE_NOT_APPLIED",
        "message": "Mattermost did not deactivate this account." + (f" API said: {api_error}" if api_error else ""),
    }), 400


@app.put("/api/users/<user_id>/password")
@api_login_required
@handle_mm_errors
def api_user_password(user_id: str):
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    if len(password) < 8:
        return jsonify({"ok": False, "message": "Password must be at least 8 characters."}), 400
    mm_request("PUT", f"/users/{user_id}/password", json_body={"new_password": password})
    log_admin("user.reset_password", target=user_id)
    return jsonify({"ok": True})


@app.get("/api/files/<file_id>")
@api_login_required
def api_file(file_id: str):
    """Serve a chat attachment to a signed-in admin.

    Reads the file straight from the Mattermost data directory (the REST API
    refuses to hand over files from conversations the admin is not part of).
    """
    meta = None
    try:
        rows = db_rows(
            "SELECT id, name, mimetype, path, size FROM fileinfo WHERE id = %s",
            "SELECT Id AS id, Name AS name, MimeType AS mimetype, Path AS path, "
            "Size AS size FROM FileInfo WHERE Id = %s",
            (file_id,),
        )
        meta = rows[0] if rows else None
    except MMError as exc:
        app.logger.warning("file lookup failed: %s", exc.message)

    if meta and meta.get("path"):
        disk = safe_media_path(meta["path"])
        if disk:
            resp = send_file(disk, mimetype=meta.get("mimetype") or None,
                             as_attachment=False,
                             download_name=meta.get("name") or None,
                             conditional=True, max_age=0)
            resp.headers["Cache-Control"] = "private, max-age=300"
            return resp
        app.logger.info("attachment %s not on disk (%s)", file_id, meta.get("path"))

    # Fall back to the Mattermost API (works for the admin's own conversations).
    token = session.get("token")
    if token:
        try:
            upstream = requests.get(f"{MM_API}/files/{file_id}", headers={"Authorization": "Bearer " + token},
                                    timeout=30, verify=VERIFY_TLS, stream=True)
            if upstream.status_code == 200:
                resp = Response(upstream.iter_content(chunk_size=32768),
                                content_type=upstream.headers.get("Content-Type", "application/octet-stream"))
                name = meta.get("name") if meta else None
                if name:
                    resp.headers["Content-Disposition"] = f'inline; filename="{name}"'
                resp.headers["Cache-Control"] = "private, max-age=300"
                return resp
        except requests.RequestException:
            pass

    root = media_root()
    if not root:
        return jsonify({"ok": False, "code": "MEDIA_DIR_MISSING",
                        "message": "The Mattermost data directory is not readable by the dashboard. "
                                   "Set MM_DATA_DIR in .env (FileSettings.Directory) and add the "
                                   "mm-admin user to the mattermost group."}), 404
    return jsonify({"ok": False, "message": "Attachment file not found on disk."}), 404


@app.post("/api/users/<user_id>/revoke-sessions")
@api_login_required
@handle_mm_errors
def api_revoke_sessions(user_id: str):
    """Log the user out everywhere (all devices) without deactivating the account."""
    sessions = []
    try:
        sessions = mm_request("GET", f"/users/{user_id}/sessions").json()
    except MMError:
        sessions = []
    revoked = 0
    for sess in sessions:
        sid = sess.get("id")
        if not sid:
            continue
        try:
            mm_request("POST", f"/users/{user_id}/sessions/revoke",
                       json_body={"session_id": sid})
            revoked += 1
        except MMError:
            pass
    log_admin("user.revoke_sessions", target=user_id, details=revoked)
    return jsonify({"ok": True, "revoked": revoked})


@app.post("/api/users/<user_id>/roles")
@api_login_required
@handle_mm_errors
def api_set_user_roles(user_id: str):
    """Promote / demote a user between member and System Admin."""
    data = request.get_json(silent=True) or {}
    make_admin = bool(data.get("system_admin"))
    if user_id == session.get("user_id") and not make_admin:
        return jsonify({"ok": False, "message": "You cannot remove your own System Admin role."}), 400
    roles = "system_user system_admin" if make_admin else "system_user"
    mm_request("PUT", f"/users/{user_id}/roles", json_body={"roles": roles})
    invalidate_caches()
    log_admin("user.roles", target=user_id, details=roles)
    return jsonify({"ok": True, "roles": roles})


@app.get("/api/system/info")
@api_login_required
@handle_mm_errors
def api_system_info():
    """Lightweight server health panel for the overview page."""
    info: dict = {"mm_ping": None, "db": None, "mmctl": mmctl_available()}
    started = time.time()
    try:
        mm_request("GET", "/system/ping")
        info["mm_ping"] = int((time.time() - started) * 1000)
    except MMError:
        info["mm_ping"] = None
    if DATABASE_URL:
        started = time.time()
        try:
            db_rows("SELECT 1 AS ok", "SELECT 1 AS ok")
            info["db"] = int((time.time() - started) * 1000)
        except MMError:
            info["db"] = -1
    return jsonify({"ok": True, **info})


@app.get("/api/teams")
@api_login_required
@handle_mm_errors
def api_teams():
    snap = teams_snapshot(force=request.args.get("refresh") == "1")
    return jsonify({"ok": True, "teams": snap["teams"], "fetched_at": now_ts()})


@app.post("/api/teams")
@api_login_required
@handle_mm_errors
def api_create_team():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip().lower()
    display_name = (data.get("display_name") or "").strip()
    team_type = "I" if (data.get("type") or "O").upper() == "I" else "O"
    member_ids = data.get("member_ids") or []
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,63}$", name):
        return jsonify({"ok": False, "message": "Team handle must be 2-64 characters: lowercase "
                                                "letters, numbers and dashes only."}), 400
    if not display_name:
        display_name = name
    team = mm_request("POST", "/teams", json_body={
        "name": name, "display_name": display_name, "type": team_type,
    }).json()
    warnings = []
    added = 0
    if member_ids:
        req_token = session.get("token")

        def add(uid):
            mm_request("POST", f"/teams/{team['id']}/members", token=req_token,
                       json_body={"team_id": team["id"], "user_id": uid})
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(add, uid): uid for uid in member_ids}
            for fut, uid in futures.items():
                try:
                    fut.result()
                    added += 1
                except MMError as exc:
                    warnings.append(f"{uid}: {exc.message}")
    invalidate_caches()
    log_admin("team.create", target=name,
              details={"display_name": display_name, "type": team_type, "members_added": added})
    return jsonify({"ok": True, "team": {"id": team.get("id"), "name": team.get("name"),
                                         "display_name": team.get("display_name")},
                    "members_added": added, "warnings": warnings}), 201


@app.delete("/api/teams/<team_id>")
@api_login_required
@handle_mm_errors
def api_delete_team(team_id: str):
    permanent = request.args.get("permanent") == "1"
    params = {"permanent": "true"} if permanent else None
    before = probe_team(team_id)
    api_error = ""
    mmctl_error = ""

    try:
        mm_request("DELETE", f"/teams/{team_id}", params=params)
    except MMError as exc:
        if permanent and exc.status in (400, 403, 404, 500, 501):
            api_error = exc.message
        else:
            raise

    after = probe_team(team_id)
    if permanent and after["exists"]:
        name = after.get("name") or (before or {}).get("name") or team_id
        ok, output = run_mmctl(["team", "delete", name])
        mmctl_error = "" if ok else output
        after = probe_team(team_id)

    if not after["exists"]:
        invalidate_caches()
        log_admin("team.delete_permanent" if permanent else "team.archive", target=team_id)
        return jsonify({"ok": True, "result": "deleted"})

    if after.get("delete_at"):
        invalidate_caches()
        log_admin("team.archive", target=team_id,
                  details={"requested": "permanent" if permanent else "archive",
                           "api_error": api_error, "mmctl_error": mmctl_error})
        payload = {"ok": True, "result": "archived"}
        if permanent:
            payload["warning"] = ("The team was archived, not permanently deleted. Mattermost "
                                  "refuses permanent deletion while ServiceSettings."
                                  "EnableAPITeamDeletion is false, and mmctl could not be used"
                                  + (f" ({mmctl_error[:160]})" if mmctl_error else "") +
                                  ". Archived teams are hidden from users and can be restored.")
        return jsonify(payload)

    return jsonify({
        "ok": False,
        "code": "DELETE_NOT_APPLIED",
        "message": "Mattermost did not delete this team."
                   + (f" API said: {api_error}" if api_error else ""),
    }), 400


@app.post("/api/teams/<team_id>/members")
@api_login_required
@handle_mm_errors
def api_team_add_member(team_id: str):
    data = request.get_json(silent=True) or {}
    user_ids = data.get("user_ids") or ([data["user_id"]] if data.get("user_id") else [])
    role = data.get("role") or "member"
    if not user_ids:
        return jsonify({"ok": False, "message": "Select at least one user."}), 400
    added, errors = [], []
    for uid in user_ids:
        try:
            mm_request("POST", f"/teams/{team_id}/members",
                       json_body={"team_id": team_id, "user_id": uid})
            if role == "team_admin":
                mm_request("PUT", f"/teams/{team_id}/members/{uid}/roles",
                           json_body={"roles": "team_user team_admin"})
            added.append(uid)
        except MMError as exc:
            errors.append({"user_id": uid, "message": exc.message})
    invalidate_caches()
    log_admin("team.members_add", target=team_id,
              details={"added": added, "role": role, "errors": errors})
    return jsonify({"ok": True, "added": added, "errors": errors})


@app.delete("/api/teams/<team_id>/members/<user_id>")
@api_login_required
@handle_mm_errors
def api_team_remove_member(team_id: str, user_id: str):
    mm_request("DELETE", f"/teams/{team_id}/members/{user_id}")
    invalidate_caches()
    log_admin("team.members_remove", target=team_id, details={"user_id": user_id})
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
# Overview / presence / locations / audit / settings
# --------------------------------------------------------------------------- #

@app.get("/api/overview")
@api_login_required
@handle_mm_errors
def api_overview():
    bundle = _build_bundle(include_inactive=True)
    users = bundle["users"]
    users_by_id = {u["id"]: u for u in users}
    online = [u for u in users if u["active"] and u["status"] != "offline"]
    online.sort(key=lambda u: (u["status"] != "online", (u["username"] or "").lower()))
    latest = latest_locations(limit=8)
    for p in latest:
        u = users_by_id.get(p.get("user_id"))
        p["username"] = p.get("username") or (u or {}).get("username")
        p["status"] = (u or {}).get("status")
    pings_24h = db_scalar("SELECT COUNT(*) FROM location_pings WHERE ts >= ?",
                          (now_ts() - 86400,), 0)
    tracked_users = db_scalar("SELECT COUNT(DISTINCT COALESCE(user_id, username)) FROM location_pings",
                              (), 0)
    audit = db_query("SELECT * FROM audit_log ORDER BY id DESC LIMIT 8")
    return jsonify({
        "counts": bundle["counts"],
        "online_users": online[:12],
        "online_total": len(online),
        "teams": bundle["teams"],
        "latest_locations": latest,
        "pings_24h": pings_24h,
        "tracked_users": tracked_users,
        "audit": audit,
        "server": server_info(),
        "chat_mode": bundle["chat_mode"],
        "tracking_since": TRACKING_SINCE,
        "fetched_at": bundle["fetched_at"],
    })


@app.get("/api/presence")
@api_login_required
@handle_mm_errors
def api_presence():
    hours = max(1, min(24 * 30, int(request.args.get("hours", "24"))))
    bundle = _build_bundle(include_inactive=False)
    presence = compute_presence(hours=hours)
    out = []
    for u in bundle["users"]:
        if not u["active"] or u["is_bot"]:
            continue
        p = presence.get(u["id"]) or {}
        out.append({
            **u,
            "online_seconds": p.get("online_seconds", 0),
            "intervals": p.get("intervals", []),
            "last_status": p.get("last_status", u["status"]),
            "last_change": p.get("last_change"),
            "last_seen": p.get("last_seen") or u.get("last_seen"),
        })
    out.sort(key=lambda u: (u["status"] == "offline", -(u.get("online_seconds") or 0)))
    return jsonify({"ok": True, "hours": hours, "users": out,
                    "tracking_since": TRACKING_SINCE, "now": now_ts()})


@app.get("/api/status/history/<user_id>")
@api_login_required
@handle_mm_errors
def api_status_history(user_id: str):
    hours = max(1, min(24 * 30, int(request.args.get("hours", "24"))))
    now = now_ts()
    start = now - hours * 3600
    rows = db_query(
        "SELECT status, ts FROM status_events WHERE user_id = ? AND ts >= ? ORDER BY ts",
        (user_id, start),
    )
    base = db_one(
        "SELECT status, ts FROM status_events WHERE user_id = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
        (user_id, start),
    )
    events = ([base] if base else []) + rows
    intervals = []
    online_seconds = 0
    for idx, ev in enumerate(events):
        seg_start = max(ev["ts"], start)
        seg_end = events[idx + 1]["ts"] if idx + 1 < len(events) else now
        if seg_end <= seg_start:
            continue
        connected = ev["status"] in ("online", "away", "dnd")
        intervals.append({"status": ev["status"], "start": seg_start,
                          "end": min(seg_end, now), "seconds": min(seg_end, now) - seg_start})
        if connected:
            online_seconds += min(seg_end, now) - seg_start
    return jsonify({"ok": True, "user_id": user_id, "hours": hours,
                    "events": rows, "intervals": intervals,
                    "online_seconds": int(online_seconds),
                    "tracking_since": TRACKING_SINCE, "now": now})


@app.post("/api/presence/refresh")
@api_login_required
@handle_mm_errors
def api_presence_refresh():
    token = session.get("token")
    ids = [u["id"] for u in fetch_all_users(include_inactive=False, token=token)]
    statuses = fetch_statuses(ids, token=token)
    changes = record_statuses(statuses)
    invalidate_caches()
    return jsonify({"ok": True, "changes": changes, "users": len(statuses),
                    "polled_at": now_ts()})


@app.get("/api/locations/latest")
@api_login_required
@handle_mm_errors
def api_locations_latest():
    bundle = _build_bundle(include_inactive=True)
    users_by_id = {u["id"]: u for u in bundle["users"]}
    rows = latest_locations(limit=500)
    for r in rows:
        u = users_by_id.get(r.get("user_id"))
        r["username"] = r.get("username") or (u or {}).get("username")
        r["user_status"] = (u or {}).get("status")
        r["active"] = (u or {}).get("active")
        r["ts_local"] = local_str(r.get("ts"))
    return jsonify({"ok": True, "locations": rows, "now": now_ts(),
                    "tracking_since": TRACKING_SINCE})


@app.get("/api/locations")
@api_login_required
@handle_mm_errors
def api_locations():
    user_id = request.args.get("user_id") or ""
    username = request.args.get("username") or ""
    source = request.args.get("source") or ""
    limit = max(1, min(2000, int(request.args.get("limit", "200"))))
    offset = max(0, int(request.args.get("offset", "0")))
    where, args = [], []
    if user_id:
        where.append("(user_id = ? OR (user_id IS NULL AND username = ?))")
        args.extend([user_id, username])
    elif username:
        where.append("username = ?")
        args.append(username)
    if source:
        where.append("source = ?")
        args.append(source)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = db_scalar(f"SELECT COUNT(*) FROM location_pings {clause}", tuple(args), 0)
    rows = db_query(
        f"SELECT * FROM location_pings {clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
        tuple(args) + (limit, offset),
    )
    for r in rows:
        r["ts_local"] = local_str(r.get("ts"))
    return jsonify({"ok": True, "locations": rows, "total": total,
                    "limit": limit, "offset": offset})


@app.get("/api/locations/export.csv")
@api_login_required
@handle_mm_errors
def api_locations_export():
    user_id = request.args.get("user_id") or ""
    username = request.args.get("username") or ""
    where, args = [], []
    if user_id:
        where.append("(user_id = ? OR (user_id IS NULL AND username = ?))")
        args.extend([user_id, username])
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db_query(
        f"SELECT ts, user_id, username, ip, is_private, city, region, country, lat, lon, "
        f"isp, source, hostname FROM location_pings {clause} ORDER BY ts DESC LIMIT 50000",
        tuple(args),
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["time_local", "time_utc", "user_id", "username", "ip", "private_ip",
                     "city", "region", "country", "latitude", "longitude", "isp", "source", "hostname"])
    for r in rows:
        writer.writerow([
            local_str(r["ts"]), datetime.fromtimestamp(r["ts"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            r.get("user_id") or "", r.get("username") or "", r.get("ip") or "",
            "yes" if r.get("is_private") else "no", r.get("city") or "", r.get("region") or "",
            r.get("country") or "", r.get("lat") if r.get("lat") is not None else "",
            r.get("lon") if r.get("lon") is not None else "", r.get("isp") or "",
            r.get("source") or "", r.get("hostname") or "",
        ])
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=locations-{stamp}.csv"})


def _sync_audits() -> dict:
    """Best-effort import of login IPs from Mattermost's audit log (DB first, then API)."""
    users = {u["id"]: u for u in fetch_all_users(include_inactive=True)}
    id_to_name = {uid: u.get("username") for uid, u in users.items()}
    entries: list[dict] = []
    source = ""
    error = None
    if DATABASE_URL:
        try:
            entries = db_rows(
                "SELECT createat, userid, action, ipaddress FROM audits "
                "WHERE ipaddress <> '' AND action ILIKE '%login%' "
                "ORDER BY createat DESC LIMIT 1000",
                "SELECT CreateAt AS createat, UserId AS userid, Action AS action, "
                "IpAddress AS ipaddress FROM Audits WHERE IpAddress <> '' AND Action LIKE '%login%' "
                "ORDER BY CreateAt DESC LIMIT 1000",
            )
            source = "database"
        except Exception as exc:
            error = f"Could not read the Mattermost audits table: {exc}"
    if not entries and not source:
        try:
            resp = mm_request("GET", "/audits", params={"page": 0, "per_page": 200})
            data = resp.json()
            if isinstance(data, dict):
                data = data.get("audits") or []
            if isinstance(data, list):
                entries = data
                source = "api"
        except MMError as exc:
            error = error or f"Audit log not available via API ({exc.message})."
        except ValueError:
            pass
        except Exception as exc:
            error = error or f"Audit log import failed: {exc}"

    inserted = 0
    seen = 0
    for e in entries:
        action = (e.get("action") or "").lower()
        if "login" not in action or "fail" in action:
            continue
        ip = (e.get("ipaddress") or e.get("ip_address") or "").strip()
        uid = e.get("userid") or e.get("user_id")
        ts = ms_to_s(e.get("createat") or e.get("create_at"))
        if not ip or not uid:
            continue
        seen += 1
        existing = db_one(
            "SELECT id FROM location_pings WHERE user_id = ? AND ip = ? AND ts BETWEEN ? AND ?",
            (uid, ip, ts - 1800, ts + 1800),
        )
        if existing:
            continue
        # preserve the historical timestamp by inserting manually after geolocation
        private = is_private_ip(ip)
        geo = {} if private else geolocate(ip)
        db_exec(
            "INSERT INTO location_pings(user_id, username, ts, ip, is_private, lat, lon, "
            "city, region, country, country_code, isp, source, raw) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, id_to_name.get(uid), ts or now_ts(), ip, 1 if private else 0,
             geo.get("lat"), geo.get("lon"), geo.get("city") or ("Local network" if private else ""),
             geo.get("region") or "", geo.get("country") or "",
             geo.get("country_code") or "", geo.get("isp") or "", "audit-log",
             json.dumps(e)[:1500]),
        )
        inserted += 1
    return {"inserted": inserted, "scanned": seen, "source": source or None,
            "message": None if (source or seen) else (error or "No audit log entries available."),
            "error": error}


@app.post("/api/locations/sync-audits")
@api_login_required
@handle_mm_errors
def api_sync_audits():
    result = _sync_audits()
    try:
        log_admin("locations.sync_audits", details=result.get("inserted", 0))
    except Exception:
        pass
    return jsonify({"ok": True, **result})


@app.post("/api/track/location")
def api_track_location():
    key = request.headers.get("X-API-Key") or request.args.get("key") or ""
    if not LOCATION_API_KEY or not secrets.compare_digest(key, LOCATION_API_KEY):
        return jsonify({"ok": False, "message": "Invalid API key."}), 401
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    user_id = (data.get("user_id") or "").strip()
    token = get_service_token()
    user = None
    if token:
        try:
            if user_id:
                user = mm_request("GET", f"/users/{user_id}", token=token).json()
            elif username:
                user = mm_request("GET", f"/users/username/{username}", token=token).json()
        except MMError:
            user = None
    if user:
        user_id = user.get("id") or user_id
        username = user.get("username") or username
    if not (user_id or username):
        return jsonify({"ok": False, "message": "username or user_id is required."}), 400
    ip = (data.get("ip") or "").strip()
    if not ip:
        ip = client_ip()
    ping_id = record_location(
        user_id or None, username or None, ip=ip,
        lat=data.get("lat"), lon=data.get("lon"),
        accuracy=data.get("accuracy"), source=data.get("source") or "agent",
        hostname=data.get("hostname"), raw=data,
    )
    return jsonify({"ok": True, "id": ping_id, "resolved_user_id": user_id or None})


@app.get("/api/audit")
@api_login_required
@handle_mm_errors
def api_audit():
    limit = max(1, min(500, int(request.args.get("limit", "100"))))
    rows = db_query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["ts_local"] = local_str(r.get("ts"))
    return jsonify({"ok": True, "entries": rows})


@app.get("/api/settings")
@api_login_required
@handle_mm_errors
def api_settings():
    chat_info = chat_backend_info(test=True)
    settings = {
        "mm_url": MM_URL,
        "app_version": APP_VERSION,
        "server": server_info(),
        "timezone": APP_TZ,
        "poll_seconds": STATUS_POLL_SECONDS,
        "tracking_since": TRACKING_SINCE,
        "geoip_enabled": GEOIP_ENABLED,
        "location_api_key": LOCATION_API_KEY,
        "chat": chat_info,
        "database_url_masked": _mask_db_url(DATABASE_URL),
        "agent_hint_url": AGENT_URL_HINT or "",
        "mmctl_available": mmctl_available(),
        "media_dir": media_root() or "",
        "media_dir_configured": MM_DATA_DIR or "",
        "mmctl_path": find_mmctl() or "",
        "status_events": db_scalar("SELECT COUNT(*) FROM status_events", (), 0),
        "location_pings": db_scalar("SELECT COUNT(*) FROM location_pings", (), 0),
    }
    return jsonify({"ok": True, "settings": settings})


def _mask_db_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url)
        db = (p.path or "").lstrip("/")
        return f"{p.scheme}://{p.username or ''}:***@{p.hostname or ''}:{p.port or ''}/{db}"
    except Exception:
        return "configured"


@app.get("/api/chat/info")
@api_login_required
@handle_mm_errors
def api_chat_info():
    return jsonify({"ok": True, **chat_backend_info(test=True)})


@app.get("/api/chat/partners/<user_id>")
@api_login_required
@handle_mm_errors
def api_chat_partners(user_id: str):
    bundle = _build_bundle(include_inactive=True)
    users_by_id = {u["id"]: u for u in bundle["users"]}
    mode = "db" if DATABASE_URL else "api"
    warning = None
    try:
        if mode == "db":
            partners = db_chat_partners(user_id)
        else:
            partners, warning = chat_partners_via_api(user_id)
    except MMError as exc:
        if mode == "db" and exc.status in (500, 502):
            # DB configured but unreachable -> fall back to API and surface both notes
            partners, warning = chat_partners_via_api(user_id)
            warning = exc.message
            mode = "api"
        else:
            raise
    out = []
    for p in partners:
        other = users_by_id.get(p.get("partner_id")) or {}
        out.append({
            "channel_id": p.get("channel_id") or p.get("id"),
            "partner": {
                "id": p.get("partner_id"),
                "username": other.get("username") or p.get("partner_id"),
                "name": " ".join(filter(None, [other.get("first_name"), other.get("last_name")])).strip(),
                "status": other.get("status") or "offline",
                "active": other.get("active", True),
            },
            "last_post_at": p.get("last_post_at") or 0,
            "preview": p.get("preview") or "",
        })
    return jsonify({"ok": True, "mode": mode, "partners": out, "warning": warning,
                    "chat_configured": bool(DATABASE_URL)})


@app.get("/api/chat/<channel_id>/posts")
@api_login_required
@handle_mm_errors
def api_chat_posts(channel_id: str):
    page = max(0, int(request.args.get("page", "0")))
    per_page = max(20, min(200, int(request.args.get("per_page", "60"))))
    if DATABASE_URL:
        try:
            result = db_chat_posts(channel_id, page=page, per_page=per_page)
        except MMError as exc:
            if exc.status in (500, 502):
                result = chat_posts_via_api(channel_id, page=page, per_page=per_page)
                result["warning"] = exc.message
            else:
                raise
    else:
        result = chat_posts_via_api(channel_id, page=page, per_page=per_page)
    # participants
    user_ids = sorted({p["user_id"] for p in result.get("posts", []) if p.get("user_id")})
    participant_map = {}
    if user_ids:
        try:
            for chunk in chunks(user_ids, 100):
                resp = mm_request("POST", "/users/ids", json_body=chunk)
                for u in resp.json():
                    participant_map[u["id"]] = {
                        "id": u["id"],
                        "username": u.get("username"),
                        "name": " ".join(filter(None, [u.get("first_name"), u.get("last_name")])).strip(),
                    }
        except MMError:
            pass
    if not participant_map:
        bundle = _build_bundle(include_inactive=True)
        for u in bundle["users"]:
            participant_map[u["id"]] = {"id": u["id"], "username": u["username"],
                                        "name": " ".join(filter(None, [u.get("first_name"),
                                                                       u.get("last_name")])).strip()}
    result["participants"] = participant_map
    result["ok"] = True
    return jsonify(result)


@app.get("/download/agent.py")
def download_agent():
    if not session.get("token"):
        return redirect("/")
    script_path = os.path.join(BASE_DIR, "agent", "mm-location-agent.py")
    try:
        with open(script_path, "r", encoding="utf-8") as fh:
            script = fh.read()
    except OSError:
        return jsonify({"ok": False, "message": "Agent script not found."}), 404
    base = AGENT_URL_HINT or request.url_root.rstrip("/")
    username = request.args.get("username") or ""
    script = script.replace('DASH_URL_DEFAULT = ""', f'DASH_URL_DEFAULT = "{base}"')
    script = script.replace('API_KEY_DEFAULT = ""', f'API_KEY_DEFAULT = "{LOCATION_API_KEY}"')
    script = script.replace('USERNAME_DEFAULT = ""', f'USERNAME_DEFAULT = "{username}"')
    script = script.replace('APP_VERSION_PLACEHOLDER', APP_VERSION)
    log_admin("agent.download", target=username or "default")
    return Response(script, mimetype="text/x-python",
                    headers={"Content-Disposition": 'attachment; filename="mm-location-agent.py"'})


# --------------------------------------------------------------------------- #
# Error handling / startup
# --------------------------------------------------------------------------- #

@app.errorhandler(404)
def _not_found(_):
    if request.path.startswith(("/api/", "/download/")):
        return jsonify({"ok": False, "message": "Not found."}), 404
    return redirect("/")


@app.errorhandler(500)
def _server_error(exc):
    app.logger.exception("unhandled error: %s", exc)
    return jsonify({"ok": False, "message": "Internal error. Check the dashboard logs."}), 500


@app.after_request
def _headers(resp):
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


start_poller()


if __name__ == "__main__":
    try:
        from waitress import serve
    except ImportError:
        app.logger.warning("waitress not installed; using Flask development server")
        app.run(host=DASH_HOST, port=DASH_PORT, threaded=True)
    else:
        print(f"Mattermost Admin Dashboard v{APP_VERSION}")
        print(f"  Mattermost API : {MM_URL}")
        print(f"  Listening on   : http://{DASH_HOST}:{DASH_PORT}")
        print(f"  Chat data      : {'database (full visibility)' if DATABASE_URL else 'REST API'}")
        serve(app, host=DASH_HOST, port=DASH_PORT, threads=12)
