#!/usr/bin/env python3
"""
Tiny mock of the Mattermost REST API v4, used only to test the dashboard
locally without a real Mattermost server.

Run:  python3 tests/mock_mm.py          (listens on 127.0.0.1:8065)
Login: admin / admin123  (System Admin)
       john  / johnpass1 (regular user - dashboard must reject)
"""
from __future__ import annotations

import copy
import time
from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

NOW_MS = int(time.time() * 1000)


def ms(days_ago=0, minutes_ago=0):
    return NOW_MS - (days_ago * 86400 + minutes_ago * 60) * 1000


USERS = {
    "u-admin": {
        "id": "u-admin", "username": "admin", "email": "admin@example.com",
        "first_name": "Ada", "last_name": "Admin", "nickname": "",
        "roles": "system_user system_admin", "delete_at": 0,
        "create_at": ms(400), "password": "admin123",
    },
    "u-john": {
        "id": "u-john", "username": "john", "email": "john@example.com",
        "first_name": "John", "last_name": "Doe", "nickname": "JD",
        "roles": "system_user", "delete_at": 0,
        "create_at": ms(300), "password": "johnpass1",
    },
    "u-mary": {
        "id": "u-mary", "username": "mary", "email": "mary@example.com",
        "first_name": "Mary", "last_name": "Smith", "nickname": "",
        "roles": "system_user", "delete_at": 0,
        "create_at": ms(250), "password": "marypass1",
    },
    "u-ali": {
        "id": "u-ali", "username": "ali", "email": "ali@example.com",
        "first_name": "Ali", "last_name": "Hassan", "nickname": "",
        "roles": "system_user", "delete_at": 0,
        "create_at": ms(200), "password": "alipass1",
    },
    "u-sara": {
        "id": "u-sara", "username": "sara", "email": "sara@example.com",
        "first_name": "Sara", "last_name": "Khan", "nickname": "",
        "roles": "system_user", "delete_at": ms(10),
        "create_at": ms(150), "password": "sarapass1",
    },
}

TEAMS = {
    "t-core": {"id": "t-core", "name": "core", "display_name": "Core Team", "type": "O",
               "create_at": ms(200), "delete_at": 0},
    "t-design": {"id": "t-design", "name": "design", "display_name": "Design", "type": "I",
                 "create_at": ms(120), "delete_at": 0},
}

MEMBERS = {
    "t-core": [
        {"team_id": "t-core", "user_id": "u-admin", "roles": "team_user team_admin"},
        {"team_id": "t-core", "user_id": "u-john", "roles": "team_user"},
        {"team_id": "t-core", "user_id": "u-mary", "roles": "team_user"},
    ],
    "t-design": [
        {"team_id": "t-design", "user_id": "u-mary", "roles": "team_user"},
        {"team_id": "t-design", "user_id": "u-ali", "roles": "team_user team_admin"},
    ],
}

STATUSES = {"u-admin": "online", "u-john": "online", "u-mary": "away", "u-ali": "dnd"}

CHANNELS = {
    "dm-john-mary": {"id": "dm-john-mary", "name": "u-john__u-mary", "type": "D",
                     "last_post_at": ms(0, 25), "delete_at": 0},
    "dm-admin-john": {"id": "dm-admin-john", "name": "u-admin__u-john", "type": "D",
                      "last_post_at": ms(1, 0), "delete_at": 0},
    "dm-mary-ali": {"id": "dm-mary-ali", "name": "u-ali__u-mary", "type": "D",
                    "last_post_at": ms(0, 90), "delete_at": 0},
}

POSTS = {cid: [] for cid in CHANNELS}


def add_post(channel_id, user_id, message, minutes_ago, ptype=""):
    pid = "p-%s-%d" % (channel_id, len(POSTS[channel_id]) + 1)
    POSTS[channel_id].append({
        "id": pid, "channel_id": channel_id, "user_id": user_id,
        "message": message, "create_at": ms(0, minutes_ago),
        "delete_at": 0, "type": ptype, "root_id": "",
    })


for i in range(8):
    add_post("dm-john-mary", "u-john" if i % 2 == 0 else "u-mary",
             ["Hi Mary, did you see the release notes?", "Yes! Looks good.",
              "Can you review my PR when you get a chance?", "On it after lunch.",
              "Thanks!", "The deploy is scheduled for 5pm.", "Perfect.", "See you at standup."][i],
             300 - i * 30)
# Deleted post whose text is still stored (Mattermost keeps it in the posts table)
add_post("dm-john-mary", "u-john", "Delete this secret later, ok?", 30)
POSTS["dm-john-mary"][-1]["delete_at"] = ms(0, 5)
# Deleted post where the server also blanked the message
add_post("dm-john-mary", "u-john", "This message was removed by the user later", 20)
POSTS["dm-john-mary"][-1]["delete_at"] = ms(0, 5)
POSTS["dm-john-mary"][-1]["message"] = ""
add_post("dm-john-mary", "u-mary", "Are we still on for tomorrow?", 10)
# A conversation that exists only as deleted history
add_post("dm-mary-ali", "u-mary", "Old note that was removed", 400)
POSTS["dm-mary-ali"][-1]["delete_at"] = ms(0, 350)
add_post("dm-admin-john", "u-admin", "Hi John, welcome aboard!", 1500)
add_post("dm-admin-john", "u-john", "Thanks Ada!", 1400)
add_post("dm-admin-john", "u-admin", "Your laptop arrives Monday.", 1200)
add_post("dm-admin-john", "u-john", "Great, thank you.", 1180)
add_post("dm-mary-ali", "u-ali", "Salam Mary, the design review moved to Thursday.", 200)
add_post("dm-mary-ali", "u-mary", "Noted, shukran Ali.", 180)
add_post("dm-mary-ali", "u-ali", "The mockups are in the shared drive.", 95)

_INITIAL_STATE = None


def _snapshot():
    global _INITIAL_STATE
    _INITIAL_STATE = {
        "users": copy.deepcopy(USERS),
        "teams": copy.deepcopy(TEAMS),
        "members": copy.deepcopy(MEMBERS),
        "channels": copy.deepcopy(CHANNELS),
        "posts": copy.deepcopy(POSTS),
        "statuses": copy.deepcopy(STATUSES),
    }


SESSIONS = {
    "u-john": [
        {"id": "s1", "user_id": "u-john", "create_at": ms(2), "expires_at": ms(-28),
         "last_activity_at": ms(0, 3), "props": {"browser": "Chrome", "platform": "Linux", "os": "Linux"}},
        {"id": "s2", "user_id": "u-john", "create_at": ms(1), "expires_at": ms(-29),
         "last_activity_at": ms(0, 45), "props": {"browser": "Mattermost", "platform": "iPhone", "os": "iOS"}},
    ],
    "u-mary": [
        {"id": "s3", "user_id": "u-mary", "create_at": ms(1), "expires_at": ms(-29),
         "last_activity_at": ms(0, 12), "props": {"browser": "Firefox", "platform": "Linux", "os": "Linux"}},
    ],
}


def public_user(u):
    return {k: v for k, v in u.items() if k != "password"}


def err(code, message, mm_id="mock.error"):
    return jsonify({"id": mm_id, "message": message, "detailed_error": "", "status_code": code}), code


def auth_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer token-"):
        return None
    uid = header.split("Bearer token-", 1)[1]
    user = USERS.get(uid)
    if not user or user["delete_at"]:
        return None
    return user


@app.after_request
def headers(resp):
    resp.headers["X-Version-Id"] = "10.9.0-mock"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.post("/api/v4/users/login")
def login():
    data = request.get_json(silent=True) or {}
    login_id = (data.get("login_id") or "").strip().lower()
    password = data.get("password") or ""
    user = None
    for u in USERS.values():
        if u["username"].lower() == login_id or u["email"].lower() == login_id:
            user = u
            break
    if not user or user["password"] != password or user["delete_at"]:
        return err(401, "Enter a valid username or password.", "api.user.login.invalid_credentials_email_username")
    resp = jsonify(public_user(user))
    resp.headers["Token"] = "token-" + user["id"]
    return resp


@app.get("/api/v4/users/me")
def me():
    user = auth_user()
    if not user:
        return err(401, "Invalid or expired session, please login again.", "api.context.session_expired.app_error")
    return jsonify(public_user(user))


@app.get("/api/v4/config")
def config():
    if not auth_user():
        return err(401, "Not authenticated")
    return jsonify({
        "TeamSettings": {"SiteName": "Mock Mattermost"},
        "ServiceSettings": {"SiteURL": "http://127.0.0.1:8065"},
        "PasswordSettings": {"MinimumLength": 8},
    })


@app.get("/api/v4/system/ping")
def ping():
    return jsonify({"status": "OK"})


@app.get("/api/v4/users")
def list_users():
    if not auth_user():
        return err(401, "Not authenticated")
    inactive = request.args.get("inactive") == "true"
    active_only = request.args.get("active") == "true"
    users = [u for u in USERS.values()
             if (u["delete_at"] > 0) == inactive and (not active_only or u["delete_at"] == 0)]
    users.sort(key=lambda u: u["username"])
    total = len(users)
    page = int(request.args.get("page", 0))
    per_page = min(int(request.args.get("per_page", 60)), 200)
    chunk = users[page * per_page:(page + 1) * per_page]
    resp = jsonify([public_user(u) for u in chunk])
    resp.headers["X-Total-Count"] = str(total)
    return resp


@app.get("/api/v4/users/<uid>")
def get_user(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    user = USERS.get(uid)
    if not user:
        return err(404, "User not found", "app.user.get.app_error")
    return jsonify(public_user(user))


@app.get("/api/v4/users/username/<username>")
def get_user_by_username(username):
    if not auth_user():
        return err(401, "Not authenticated")
    for u in USERS.values():
        if u["username"].lower() == username.lower():
            return jsonify(public_user(u))
    return err(404, "User not found", "app.user.get.app_error")


@app.post("/api/v4/users/ids")
def users_by_ids():
    if not auth_user():
        return err(401, "Not authenticated")
    ids = request.get_json(silent=True) or []
    return jsonify([public_user(USERS[i]) for i in ids if i in USERS])


@app.post("/api/v4/users")
def create_user():
    if not auth_user():
        return err(401, "Not authenticated")
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    if not username or not email or not data.get("password"):
        return err(400, "Invalid or missing user in request body.", "api.user.create_user.missing_field.app_error")
    for u in USERS.values():
        if u["username"].lower() == username.lower():
            return err(400, "An account with that username already exists.", "api.user.create_user.username_exists.app_error")
        if u["email"].lower() == email.lower():
            return err(400, "An account with that email already exists.", "api.user.create_user.email_exists.app_error")
    uid = "u-" + username.lower()
    USERS[uid] = {
        "id": uid, "username": username, "email": email,
        "first_name": data.get("first_name") or "", "last_name": data.get("last_name") or "",
        "nickname": "", "roles": "system_user", "delete_at": 0,
        "create_at": int(time.time() * 1000), "password": data.get("password"),
    }
    STATUSES[uid] = "offline"
    return jsonify(public_user(USERS[uid])), 201


@app.put("/api/v4/users/<uid>/active")
def set_active(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    user = USERS.get(uid)
    if not user:
        return err(404, "User not found")
    active = bool((request.get_json(silent=True) or {}).get("active"))
    user["delete_at"] = 0 if active else int(time.time() * 1000)
    return jsonify({"status": "OK"})


@app.delete("/api/v4/users/<uid>")
def delete_user(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    user = USERS.get(uid)
    if not user:
        return err(404, "User not found")
    if request.args.get("permanent") == "true":
        return err(501, "User deletion is disabled on this server.", "app.user.delete.app_error")
    user["delete_at"] = int(time.time() * 1000)
    return jsonify({"status": "OK"})


@app.put("/api/v4/users/<uid>/password")
def set_password(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    user = USERS.get(uid)
    if not user:
        return err(404, "User not found")
    user["password"] = (request.get_json(silent=True) or {}).get("new_password") or user["password"]
    return jsonify({"status": "OK"})


@app.put("/api/v4/users/<uid>/roles")
def set_roles(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    user = USERS.get(uid)
    if not user:
        return err(404, "User not found")
    user["roles"] = (request.get_json(silent=True) or {}).get("roles", user["roles"])
    return jsonify({"status": "OK"})


@app.get("/api/v4/users/<uid>/teams")
def user_teams(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    teams = [TEAMS[tid] for tid, members in MEMBERS.items()
             if any(m["user_id"] == uid for m in members) and tid in TEAMS]
    return jsonify(teams)


@app.get("/api/v4/users/<uid>/sessions")
def user_sessions(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    return jsonify(SESSIONS.get(uid, []))


@app.get("/api/v4/users/<uid>/channels")
def user_channels(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    channels = [c for c in CHANNELS.values() if uid in (c["name"] or "").split("__")]
    return jsonify(channels)


@app.post("/api/v4/users/status/ids")
def statuses_by_ids():
    if not auth_user():
        return err(401, "Not authenticated")
    ids = request.get_json(silent=True) or []
    out = []
    for uid in ids:
        if uid in USERS and not USERS[uid]["delete_at"]:
            st = STATUSES.get(uid, "offline")
            out.append({"user_id": uid, "status": st, "manual": False,
                        "last_activity_at": int(time.time() * 1000)})
    return jsonify(out)


@app.get("/api/v4/users/<uid>/status")
def user_status(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    return jsonify({"user_id": uid, "status": STATUSES.get(uid, "offline"), "manual": False})


@app.get("/api/v4/teams")
def list_teams():
    if not auth_user():
        return err(401, "Not authenticated")
    teams = sorted([t for t in TEAMS.values() if not t["delete_at"]], key=lambda t: t["name"])
    page = int(request.args.get("page", 0))
    per_page = min(int(request.args.get("per_page", 60)), 100)
    chunk = teams[page * per_page:(page + 1) * per_page]
    resp = jsonify(chunk)
    resp.headers["X-Total-Count"] = str(len(teams))
    return resp


@app.get("/api/v4/teams/<tid>")
def get_team(tid):
    if not auth_user():
        return err(401, "Not authenticated")
    team = TEAMS.get(tid)
    if not team or team["delete_at"]:
        return err(404, "Team not found", "app.team.get.app_error")
    return jsonify(team)


@app.post("/api/v4/teams")
def create_team():
    if not auth_user():
        return err(401, "Not authenticated")
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip().lower()
    if any(t["name"] == name for t in TEAMS.values()):
        return err(400, "A team with that handle already exists.", "store.sql_team.save.domain_exists.app_error")
    tid = "t-" + name
    TEAMS[tid] = {"id": tid, "name": name,
                  "display_name": data.get("display_name") or name,
                  "type": data.get("type") or "O",
                  "create_at": int(time.time() * 1000), "delete_at": 0}
    MEMBERS[tid] = []
    return jsonify(TEAMS[tid]), 201


@app.delete("/api/v4/teams/<tid>")
def delete_team(tid):
    if not auth_user():
        return err(401, "Not authenticated")
    team = TEAMS.get(tid)
    if not team:
        return err(404, "Team not found")
    if request.args.get("permanent") == "true":
        del TEAMS[tid]
        MEMBERS.pop(tid, None)
    else:
        team["delete_at"] = int(time.time() * 1000)
    return jsonify({"status": "OK"})


@app.get("/api/v4/teams/<tid>/members")
def team_members(tid):
    if not auth_user():
        return err(401, "Not authenticated")
    members = list(MEMBERS.get(tid, []))
    page = int(request.args.get("page", 0))
    per_page = min(int(request.args.get("per_page", 60)), 200)
    return jsonify(members[page * per_page:(page + 1) * per_page])


@app.post("/api/v4/teams/<tid>/members")
def add_team_member(tid):
    if not auth_user():
        return err(401, "Not authenticated")
    if tid not in TEAMS:
        return err(404, "Team not found")
    data = request.get_json(silent=True) or {}
    uid = data.get("user_id")
    if uid not in USERS:
        return err(404, "User not found")
    if any(m["user_id"] == uid for m in MEMBERS.get(tid, [])):
        return err(400, "This user is already a member of the team.",
                   "store.sql_team.save_member.exists.app_error")
    member = {"team_id": tid, "user_id": uid, "roles": "team_user"}
    MEMBERS.setdefault(tid, []).append(member)
    return jsonify(member), 201


@app.put("/api/v4/teams/<tid>/members/<uid>/roles")
def set_member_roles(tid, uid):
    if not auth_user():
        return err(401, "Not authenticated")
    roles = (request.get_json(silent=True) or {}).get("roles", "team_user")
    for m in MEMBERS.get(tid, []):
        if m["user_id"] == uid:
            m["roles"] = roles
    return jsonify({"status": "OK"})


@app.delete("/api/v4/teams/<tid>/members/<uid>")
def remove_team_member(tid, uid):
    if not auth_user():
        return err(401, "Not authenticated")
    MEMBERS[tid] = [m for m in MEMBERS.get(tid, []) if m["user_id"] != uid]
    return jsonify({"status": "OK"})


@app.get("/api/v4/channels/<cid>/posts")
def channel_posts(cid):
    if not auth_user():
        return err(401, "Not authenticated")
    channel = CHANNELS.get(cid)
    if not channel:
        return err(404, "Channel not found")
    posts = sorted(POSTS.get(cid, []), key=lambda p: p["create_at"], reverse=True)
    page = int(request.args.get("page", 0))
    per_page = min(int(request.args.get("per_page", 60)), 200)
    chunk = posts[page * per_page:(page + 1) * per_page]
    return jsonify({
        "order": [p["id"] for p in chunk],
        "posts": {p["id"]: p for p in chunk},
        "next_post_id": chunk[-1]["id"] if chunk else "",
        "prev_post_id": "",
    })


@app.post("/api/v4/users/<uid>/sessions/revoke")
def revoke_session(uid):
    if not auth_user():
        return err(401, "Not authenticated")
    sid = (request.get_json(silent=True) or {}).get("session_id")
    SESSIONS[uid] = [s for s in SESSIONS.get(uid, []) if s["id"] != sid]
    return jsonify({"status": "OK"})


@app.get("/api/v4/system/ping")
def system_ping():
    return jsonify({"status": "OK", "version": "10.9.0-mock"})


@app.get("/api/v4/audits")
def audits():
    if not auth_user():
        return err(401, "Not authenticated")
    return err(403, "Audit log access is not enabled in this mock.", "api.context.permissions.app_error")


@app.post("/mock/reset")
def mock_reset():
    """Restore the mock to its initial state (test helper)."""
    if _INITIAL_STATE:
        USERS.clear(); USERS.update(copy.deepcopy(_INITIAL_STATE["users"]))
        TEAMS.clear(); TEAMS.update(copy.deepcopy(_INITIAL_STATE["teams"]))
        MEMBERS.clear(); MEMBERS.update(copy.deepcopy(_INITIAL_STATE["members"]))
        CHANNELS.clear(); CHANNELS.update(copy.deepcopy(_INITIAL_STATE["channels"]))
        POSTS.clear(); POSTS.update(copy.deepcopy(_INITIAL_STATE["posts"]))
        STATUSES.clear(); STATUSES.update(copy.deepcopy(_INITIAL_STATE["statuses"]))
    return jsonify({"ok": True})


_snapshot()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8065, debug=False, threaded=True)
