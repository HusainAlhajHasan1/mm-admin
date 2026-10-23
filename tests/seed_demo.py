#!/usr/bin/env python3
"""
Developer utility: fills the mock-backed dashboard with a few realistic teams,
users, presence intervals and location records so screenshots/UI review look
representative. Only for use with tests/mock_mm.py and a throwaway database.
"""
import os
import sqlite3
import time

import requests

BASE = "http://127.0.0.1:8090"
DB = os.environ.get("DB_PATH", "/home/user/mm-admin/data/test-admin.db")
NOW = int(time.time())

s = requests.Session()
r = s.post(BASE + "/api/login", json={"login_id": "admin", "password": "admin123"})
r.raise_for_status()
H = {"X-CSRF-Token": r.json()["csrf"]}

users = {u["username"]: u for u in s.get(BASE + "/api/users").json()["users"]}
teams = {t["name"]: t for t in s.get(BASE + "/api/users").json()["teams"]}

# --- extra team + user -------------------------------------------------------
if "ops" not in teams:
    r = s.post(BASE + "/api/teams", headers=H, json={
        "name": "ops", "display_name": "Operations", "type": "I",
        "member_ids": [users["ali"]["id"]],
    })
    print("created ops team:", r.status_code, r.text[:120])

if "lina" not in users:
    r = s.post(BASE + "/api/users", headers=H, json={
        "username": "lina", "email": "lina@example.com", "password": "linapass12",
        "first_name": "Lina", "last_name": "Weber", "team": "design",
    })
    print("created lina:", r.status_code, r.text[:120])

# --- location history -------------------------------------------------------
PINGS = [
    ("u-john", "john", "84.145.12.34", 52.520, 13.405, "Berlin", "Berlin", "Germany", "DE", "Deutsche Telekom", "agent", 4),
    ("u-john", "john", "84.145.12.34", 52.520, 13.405, "Berlin", "Berlin", "Germany", "DE", "Deutsche Telekom", "agent", 190),
    ("u-john", "john", "84.145.12.34", 52.520, 13.405, "Berlin", "Berlin", "Germany", "DE", "Deutsche Telekom", "agent", 380),
    ("u-mary", "mary", "91.64.23.11", 48.137, 11.575, "Munich", "Bavaria", "Germany", "DE", "Vodafone", "agent", 12),
    ("u-mary", "mary", "91.64.23.11", 48.137, 11.575, "Munich", "Bavaria", "Germany", "DE", "Vodafone", "agent", 300),
    ("u-ali", "ali", "79.173.2.5", 31.955, 35.945, "Amman", "Amman", "Jordan", "JO", "Orange Jordan", "agent", 25),
    ("u-ali", "ali", "79.173.2.5", 31.955, 35.945, "Amman", "Amman", "Jordan", "JO", "Orange Jordan", "audit-log", 1500),
    ("u-admin", "admin", "62.155.8.9", 49.452, 11.077, "Nuremberg", "Bavaria", "Germany", "DE", "Deutsche Telekom", "dashboard-login", 8),
    ("u-lina", "lina", "88.77.66.55", 53.551, 9.993, "Hamburg", "Hamburg", "Germany", "DE", "O2", "agent", 45),
    ("u-sara", "sara", "203.0.113.9", 40.712, -74.006, "New York", "New York", "United States", "US", "Example ISP", "audit-log", 2600),
]

con = sqlite3.connect(DB, timeout=15)
con.execute("PRAGMA journal_mode=WAL")
existing = con.execute("SELECT COUNT(*) FROM location_pings").fetchone()[0]
if existing < 5:
    for uid, uname, ip, lat, lon, city, region, country, cc, isp, source, mins_ago in PINGS:
        con.execute(
            "INSERT INTO location_pings(user_id, username, ts, ip, is_private, lat, lon, city, region, "
            "country, country_code, isp, source, hostname) VALUES(?,?,?,?,0,?,?,?,?,?,?,?,?,?)",
            (uid, uname, NOW - mins_ago * 60, ip, lat, lon, city, region, country, cc, isp, source,
             "workstation" if source == "agent" else ""),
        )
    print("inserted", len(PINGS), "location pings")

# --- presence history -------------------------------------------------------
# Current statuses in the mock: admin=online, john=online, mary=away, ali=dnd
CURRENT = {"u-admin": "online", "u-john": "online", "u-mary": "away", "u-ali": "dnd"}
existing_events = con.execute("SELECT COUNT(*) FROM status_events").fetchone()[0]
if existing_events < 5:
    patterns = {
        "u-john": [(36, "online"), (33, "offline"), (30, "online"), (24, "away"), (23, "online"), (18, "offline"),
                   (16, "online"), (12, "offline"), (10, "online"), (6, "dnd"), (4, "online"), (2, "online")],
        "u-mary": [(36, "offline"), (31, "online"), (26, "offline"), (22, "online"), (17, "away"), (13, "online"),
                   (8, "offline"), (5, "online"), (2, "away")],
        "u-ali": [(36, "online"), (28, "dnd"), (20, "online"), (14, "offline"), (9, "online"), (3, "dnd")],
        "u-admin": [(36, "offline"), (34, "online"), (20, "away"), (18, "online"), (7, "online"), (1, "online")],
    }
    for uid, events in patterns.items():
        for hours_ago, status in events:
            con.execute("INSERT INTO status_events(user_id, status, ts) VALUES(?,?,?)",
                        (uid, status, NOW - hours_ago * 3600))
        con.execute("INSERT INTO status_state(user_id, status, changed_at) VALUES(?,?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET status=excluded.status, changed_at=excluded.changed_at",
                    (uid, CURRENT[uid], NOW - 1800))
    print("inserted presence history")

con.commit()
con.close()
print("demo data ready")
