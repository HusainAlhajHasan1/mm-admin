#!/usr/bin/env python3
"""
Tiny mock of the Mattermost REST API v4, used only to test the dashboard
locally without a real Mattermost server.

Run:  python3 tests/mock_mm.py          (listens on 127.0.0.1:8065)
Login: admin / admin123  (System Admin)
       john  / johnpass1 (regular user - dashboard must reject)
"""
from __future__ import annotations

import base64
import copy
import time
from flask import Flask, Response, jsonify, request

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

# post_id -> list of attached files (shape mirrors the Mattermost API metadata)
FILES_BY_POST = {}

# Mirrors config.json ServiceSettings flags on a real server.
SERVER_FLAGS = {
    "EnableAPIUserDeletion": False,   # false => permanent delete only deactivates
    "EnableAPITeamDeletion": False,   # false => permanent delete only archives
}


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
FILES_BY_POST["p-dm-john-mary-1"] = [{
    "id": "file-mock-png", "name": "release-screenshot.png", "extension": "png",
    "size": 24043, "mime_type": "image/png", "width": 360, "height": 200,
}]
FILES_BY_POST["p-dm-john-mary-3"] = [{
    "id": "file-mock-pdf", "name": "release-notes.pdf", "extension": "pdf",
    "size": 12, "mime_type": "application/pdf", "width": 0, "height": 0,
}]

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
        "flags": copy.deepcopy(SERVER_FLAGS),
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
        if SERVER_FLAGS["EnableAPIUserDeletion"]:
            USERS.pop(uid, None)
            return jsonify({"status": "OK"})
        # Real Mattermost: falls back to a soft delete and still answers 200,
        # which is why a dashboard must verify the result.
        user["delete_at"] = int(time.time() * 1000)
        return jsonify({"status": "OK"})
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
    if not team:
        return err(404, "Team not found", "app.team.get.app_error")
    # Real Mattermost returns archived teams (with delete_at set) to sysadmins,
    # which is how a client can tell "archived" apart from "deleted".
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
    if request.args.get("permanent") == "true" and SERVER_FLAGS["EnableAPITeamDeletion"]:
        del TEAMS[tid]
        MEMBERS.pop(tid, None)
    else:
        # Real Mattermost archives (soft-deletes) when permanent deletion is off.
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
    payload = {}
    for p in chunk:
        item = dict(p)
        if p["id"] in FILES_BY_POST:
            item["metadata"] = {"files": FILES_BY_POST[p["id"]]}
        payload[p["id"]] = item
    return jsonify({
        "order": [p["id"] for p in chunk],
        "posts": payload,
        "next_post_id": chunk[-1]["id"] if chunk else "",
        "prev_post_id": "",
    })


PNG_DEMO = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAWgAAADICAIAAABK7OzYAABdsklEQVR42rzWV5dtaUG4+/oQtVLlHNeqnOuLgYKAoqAgICj8AQFBQUHgL0r3jpVXzjmHinvvxptzc67PmXPP2TO8833e0Re9eozfZ3jGMzL6uT8Sn+4DKb/uQ6mA7plU0PTcK/Te//P//n+fronPvZr43GvBpO1MMOVy7jTtcuE043LpNCu6ssyJri3zohvLgkTUsCgRMyxJxA3LcgnNilxSsyqX0qyh9DrKhFE2wjY+lyObn8uTrc8VyLauKLWjK0nt6spSe6aK176p6nVgqnkd2uqCI1tDcGxrCk5cWk6nLm2nEWU4PuBwfMjheKYMx3MOx4tPPRzv20HhOFOG45zDccHhuFSG44rDcc3huFGGI8rhiHE44spwJDgcSQ5HShmONIcjw+HIKsOR43DkORwFZTiKHI4Sh6OsDEeFw1HlcNSU4ahzOBocjqYyHC0OR/uTh+MDDseHHI5nynA853C8MHwG7aBqTHI1prga01yNGa7GLFdjjqsxz9VY4GoscjWWuBrLXI0VrsYqV2ONq7HO1eBw5DgceQ5HQRmOIoejxOEoK8NR4XBUORw1ZTjqHI4Gh6OpDEeLw9GWhePzf5T5QOOT+1Djl3umCaDnQfQi5DCUdnz+tWXy82dkSncuNa27kJrRXUrNmq685kzXXvOmG68FW1SwaIsJlmxxwbJLwmnFJem06pJyWhOlLeuijCUsyloiEjnDhkTesClRMGzJFTXbciXNjlxZs4sqe6i6j2oH7PDzdXL0+QY5/nyTnOhaUqe6ttQIVWOUq+HjanA4nnM4XgjhGHI7zpThOOdwXHA4LpXhuOJwXHM4bpThiHI4YhyOuDIcCQ5HksORUoYjzeHIcDiyynDkOBx5DkdBGY4ih6PE4Sgrw1HhcFQ5HDVlOOocjgaHo6kMR4vD0eZw/Nkf3T6w+EQfWvyiZ5aAxHNDUOKFIeQxlHb82ZlmEp1PoYtpdDnDZv/sisz92TWZ/7MbsqCLSi3qYlJLurjUsinhtWJKeq2aUl5rtrRg3ZYRhG1ZQcQl57ThknfadCk4bYmKlm1RybIjKlt2JSqGPYmqYV+iZjiQq2sO5RqaI7mm5hi1TlD7FHVGqBqjXA0fV8PP1QhwNWTheKkZUjuoGhyOCw7HpTIcVxyOaw7HjTIcUQ5HjMMRV4YjweFIcjhSynCkORwZDkdWGY4chyPP4Sgow1HkcJQ4HGVlOCocjiqHo6YMR53D0eBwNJXhaHE42hyOjhCODzgcH3I4ninD8ZzD8YLD8dIyjHZQNSa5GlNcDQ7HFYfjmsNxowxHlMMR43DEleFIcDiSHI6UMhxpDkeGw5FVhiPH4chzOArKcBQ5HCUOR1kZjgqHo8rhqCnDUedwNDgcTWU4WhyONoej83E4/vyP733g5TN96OU3PfMK2J4LgrYXgpDtpWAo7fjzM4dzy5TowjIturTMSFwZZiWuDXMSN4Z5uahmQS6mWZSLa5ZQYhklV1Bqla39eZqs/3mGhP88SyK6nNSGLi+1qStIbZmKXtumkteOqey1a6sI9mxVwb6tJjhwqTsdujScjlyaTseiluVE1LacijqWEarGKFfDx9XwczUCXI0gV0MzNtx2nHM4Ljgcl8pwXHE4rjkcN8pwRDkcMQ5HXBmOBIcjyeFIKcOR5nBkOBxZZThyHI48h6OgDEeRw1HicJSV4ahwOKocjpoyHHUOR4PD0VSGo8XhaHM4Ou5wfOED4vvCh8T/hWckoHsuFdS9kArpXkqNvffph+MLZ5NfOBdM2S4E07ZLwYzLldOsy7XTnMuN07woalkQxSyLorhlSSJhWJZIGlYkUoZVubRmTS6jWZfLasIoF0H5DVTYZFtfKJLtL5TIzhfKZFdXkdrTVaX2dTWpA1Pd69DU8DoyNb2ObS3Bia0tOLV1BIpwfMjheKYMx3MOxwsOx0tlOF4NZTowHBccjktlOK44HNccjhtlOKIcjhiHI64MR4LDkeRwpJThSHM4MhyOrDIcOQ5HnsNRUIajyOEocTjKynBUOBxVDkdNGY46h6PB4Wgqw9HicLQ5HJ1PHo4PORzPlOF4zuF4weF4qQzHK8Nn0A6qxhRXY5qrMcPVmOVqzHE15rkaC1yNRa7GEldjmauxwtVY5WqscTXWuRphrkaEq8HhKHI4ShyOsjIcFQ5HlcNRU4ajzuFocDiaynC0OBxtDkcHwvHFDzw+NPgknhn8cs81AbkXmqDcS00IvRpzGEo7vnhumfriBZn+4iWZ0V1JzequpeZ0N1LzpqjXginmtWiKey3ZEoJlW1KwYksJVl3STmsuGad1l6xTWJSzRER5y4aoYNmUKBq2JEqGbYmyYUeuotmVq2r25GqafVQ/QI1D1Dxix19skZMvtsnpFztkhKoxytXwcTX8XI0AV4PD8UoIx5DbccHhuFSG44rDcc3huFGGI8rhiHE44spwJDgcSQ5HShmONIcjw+HIKsOR43DkORwFZTiKHI4Sh6OsDEeFw1HlcNSU4ahzOBocjqYyHC0OR5vD0VGG4y8+cPjQyefyzMkvem4JiF5YgqKXlpDEK8OYx1Da8RcXmim5S800uppB17PoZo7N/0WULPxFjCz+RZws6RJSy7qk1IouJbVqSnutmTJe66asV9iWE0RsecGGrSDYdCk6bbmUnLZdyk47ooplV1S17Ilqln2JuuFAomE4lGgajuRammO5tuZErqM5Rd0RqsYoV8PH1fBzNQJcjSBXQxaO15ohtYOqweG44nBcczhulOGIcjhiHI64MhwJDkeSw5FShiPN4chwOLLKcOQ4HHkOR0EZjiKHo8ThKCvDUeFwVDkcNWU46hyOBoejqQxHi8PR5nB0lOHoOsPxIYfjmTIczzkcLzgcL5XheMXheG0ZRjuoGlNcjWmuxgxXg8MR5XDEOBxxZTgSHI4khyOlDEeaw5HhcGSV4chxOPIcjoIyHEUOR4nDUVaGo8LhqHI4aspw1DkcDQ5HUxmOFoejzeHoKMPR/TgcX/pg9EsfSvl0z6T8pudeAdMLr6DppVfI9kowZnstGEo7vnTxsUunadGVZUZ0bZkV3VjmJKKGeYmYYUEibliUS2iW5JKaZbmUZgWlV1FmDWXXWfhLORL5Up5sfKlANnVFqS1dSWpbV5baMVW8dk1Vrz1TzWvfVhcc2BqCQ1tTcOTScjp2aTuduHScTkVdywhVY5Sr4eNq+LkaAa5GkKsR4mpoxofYjktlOK44HNccjhtlOKIcjhiHI64MR4LDkeRwpJThSHM4MhyOrDIcOQ5HnsNRUIajyOEocTjKynBUOBxVDkdNGY46h6PB4Wgqw9HicLQ5HB1lOLrucHz5Q/DMx/xffk4CX35Bgl9+SUK6V1JjutdS47qzTz8cX770mrZdCWZs14JZ241gziXqNO8Sc1pwiTstihKWJVHSsixKWVYk0oZViYxhTSJrWJfLacJyeU1ErqDZQMVNVNpC5W228+UK2f1ylex9uUb2dXWpA11D6lDXlDoytbyOTW2vE1PH69TWFVA4ninD8ZzD8YLD8VIZjlccjtccjrNhhEPaDqrGNFdjhqsxy9WY42rMczUWuBqLXI0lrsYyV2OFq7HK1VjjaqxzNcJcDQ5HkcNR4nCUleGocDiqHI6aMhx1DkeDw9FUhqPF4WhzODrKcHQ/YTieKcPxnMPxgsPxUhmOVxyO1xyOs/GPfQbtoGpMczVmuBqzXI05rsY8V2OBq7HI1VjiaixzNVa4GqtcjTWuxjpXI8zViHA1Nrgam1wNDkeFw1HlcNSU4ahzOBocjqYyHC0OR5vD0VGGowvh+MqHbs8sPonnBr/EC0NA4qUhKPdKE5J7rRmTO9OMOwylHV+5tEx/5YrMfOWazH7lhszpolLzupjUgi4utWhKeC2Zkl7LppTXii0tWLVlBGu2rGDdJecUdsk7RVwKThuiomVTVLJsicqWbYmKYUeiatiVqBn25OqafbmG5kCuqTlErSPUPkadE3b6lS4ZoWqMcjV8XA0/VyPA1QhyNUJcDSEcQ27HFYfjmsNxowxHlMMR43DEleFIcDiSHI6UMhxpDkeGw5FVhiPH4chzOArKcBQ5HCUOR1kZjgqHo8rhqCnDUedwNDgcTWU4WhyONoejowxHl8PRGxn9yw8/9kzgc3nu5Hd54RRweekUFL2yhESvLWOiM8u4x1Da8ZdXmmm5a82M3I1mFkXnUGwexRfY4l8myNJfJsnyX6bIii4ttarLSK3pslLrppxX2JT3ipgKXhu2omDTVhJs2cqCbZeK045L1WnXpea0J6pb9kUNy4GoaTmUaBmOJNqGY4mO4USuqzmV62lGqBqjXA0fV8PP1QhwNYJcjRBXQxaOc82Q2kHVmOZqcDiiHI4YhyOuDEeCw5HkcKSU4UhzODIcjqwyHDkOR57DUVCGo8jhKHE4yspwVDgcVQ5HTRmOOoejweFoKsPR4nC0ORwdZTi6HI6eMxzPlOF4zuF4weF4qQzHKw7Haw7HmTIc55ZhtIOqMc3VmOFqzHI15rgaHI4EhyPJ4Ugpw5HmcGQ4HFllOHIcjjyHo6AMR5HDUeJwlJXhqHA4qhyOmjIcdQ5Hg8PRVIajxeFoczg6ynB0ORw9Rzj+6hnx6Z5L+XUvpAK6l1JB0yuvkOm115jpzGvcdi4YSjv+6upj104zLjdOs6KoZU4Us8yL4pYFiYRhUSJpWJJIGZbl0poVuYxmVS6rWUO5dZQPo0KEbfxVkWz+VYls/VWZbOsqUju6qtSuria1Z6p77ZsaXgemptehrSU4srUFx7aO4MSl63Tq0nNSh+M5h+MFh+OlMhyvOByvORxnynCce00MsR3XHI4bZTiiHI4YhyOuDEeCw5HkcKSU4UhzODIcjqwyHDkOR57DUVCGo8jhKHE4yspwVDgcVQ5HTRmOOoejweFoKsPR4nC0ORwdZTi6HI6eJxxffQae+9ALP3oZYMGvviKhr74mY189I+O6c6kJ3cWnH46vXnvNmG68Zm1RwZwtJpi3xQULLgmnRZek05JLymlZlLasiDKWVVHWsiaRM6xL5A1hiYIhIlfUbMiVNJtyZc0Wqmyj6g6q7bK9r9bJ/lcb5OCrTXKoa0kd6dpSx7qO1Imp63Vq6nlROJ5zOF5wOF4qw/GKw/Gaw3GmDMc5h+NiGOGQtoOqMcPVmOVqzHE15rkaC1yNRa7GEldjmauxwtVY5WqscTXWuRphrkaEq7HB1eBwVDgcVQ5HTRmOOoejweFoKsPR4nC0ORwdZTi6HI7eJw/Hcw7HCw7HS2U4XnE4XnM4zpThOOdwXEx87DNoB1Vjhqsxy9WY42rMczUWuBqLXI0lrsYyV2OFq7HK1VjjaqxzNcJcjQhXY4OrscnV2OJqbHM1OBx1DkeDw9FUhqPF4WhzODrKcHQ5HD0Ox18/c3tu8YleWPyil5aAxCtDUOK1ISRxZhiTO9eMy11oJhyG0o6/vv7YzQyb/esomfvrGJn/6zhZ0CWkFnVJqSVdSmrZlPZaMWW8Vk1ZrzVbTrBuywvCtoIg4lJ02nApOW26lJ22RBXLtqhq2RHVLLsSdcOeRMOwL9E0HMi1NIdybc2RXEdzjLonqHeK+iNUjVGuho+r4edqBLgaQa5GiKsxxtUQwjHMdtwowxHlcMQ4HHFlOBIcjiSHI6UMR5rDkeFwZJXhyHE48hyOgjIcRQ5HicNRVoajwuGocjhqynDUORwNDkdTGY4Wh6PN4egow9HlcPQ4HP334fibZx97LvDZXgj8tpeCgMsrp6DLa6eQy5nTmOjcMi66sEyILofSjr+50czIRTWzcjHNnFxcM48SCyi5iFJLbPlv0mTlbzJk9W+yZE2Xk1rX5aXCuoJUxFT02jCVvDZNZa8tW0WwbasKdmw1wa5L3WnPpeG079J0OhC1LIeituVI1LEcS3QNJxI9w6lE3zBC1Rjlavi4Gn6uRoCrEeRqhLgaY1wNTzguDUNqB1Vjhqsxy9XgcCQ4HEkOR0oZjjSHI8PhyCrDkeNw5DkcBWU4ihyOEoejrAxHhcNR5XDUlOGoczgaHI6mMhwtDkebw9FRhqPL4ehxOPpCOJ5zOF5wOF4qw/GKw/Gaw3GmDMc5h+OCw3HpNIx2UDVmuBqzXI05rsY8V2OBq8HhSHM4MhyOrDIcOQ5HnsNRUIajyOEocTjKynBUOBxVDkdNGY46h6PB4Wgqw9HicLQ5HB1lOLocjh6Ho+8Ox9eeE9/XXhD/116SgO6VVFD3WiqkO5MaM517jZsuvCZMl15DacfXbj4WdZp1iTnNucSd5kUJy4IoaVkUpSxLEmnDskTGsCKRNazK5TRrcnnNulxBE0bFCCptoPIm2/pahWx/rUp2vlYju7q61J6uIbWva0odmFpeh6a215Gp43Vs6wpObD3Bqa0vUITjBYfjpTIcrzgcrzkcZ8pwnHM4Ljgcl1KTQ2xHlMMR43DEleFIcDiSHI6UMhxpDkeGw5FVhiPH4chzOArKcBQ5HCUOR1kZjgqHo8rhqCnDUedwNDgcTWU4WhyONoejowxHl8PR43D0ZeH4+nOZFxqf3EuNH70KoNdBdBZiY18/J+NfvyATX78kk7qrTz8cX496zZpiXnOmuNe8LSFYsCUFi7aUYMkl7bTsknFacck6rYpyljVR3rIuKljCEkVDRKJk2JAoGzblKpotuapmW66m2UH1XdTYQ819dvD1Fjn8epscfb1DjnVdqRNdT+pU15caoWqMcjU4HK84HK85HGfKcJxzOC44HJfKcFwNIxzSdlA1Zrkac1yNea7GAldjkauxxNVY5mqscDVWuRprXI11rkaYqxHhamxwNTa5GltcDQ5HncPR4HA0leFocTjaHI6OMhxdDkePw9H/5OF4weF4qQzHKw7Haw7HmTIc5xyOCw7HpTIcV5Mf+wzaQdWY5WrMcTXmuRoLXI1FrsYSV2OZq7HC1VjlaqxxNda5GmGuRoSrscHV2ORqbHE1trkaO1yNXa4Gh6PF4WhzODrKcHQ5HD0OR18Zjr997vDCyefy0skvemUJiF5bgqIzS0ji3DAmcWEYl7g0TMhdaSYdhtKOv41+LDaL4nNs/m8TZOFvk2Txb1NkSZeWWtZlpFZ0WalVU85rzZT3WjcVvMK2oiBiKwk2bGXBpkvFacul6rTtUnPaEdUtu6KGZU/UtOxLtAwHEm3DoUTHcCTX1RzL9TQncn3NKRqMUDVGuRo+roafqxHgagS5GiGuxhhXY5yrIYRjmO2IcTjiynAkOBxJDkdKGY40hyPD4cgqw5HjcOQ5HAVlOIocjhKHo6wMR4XDUeVw1JThqHM4GhyOpjIcLQ5Hm8PRUYajy+HocTj6ynAM3ofj756/98LLZ3rp5be9EgRsrwVB25kg5HLuNOZy4TTucuk0IbqyTIquh9KOv4tpZiXihjm5hGZeLqlZkEtpFlF6CWWWUXaFrf5djqz9XZ6s/12BhHVFqYiuJLWhK0ttmipeW6aq17ap5rVjqwt2bQ3Bnq0p2HdpOR24tJ0OXTpOR6Ku5VjUs5yI+pZTiYFhhKoxytXwcTX8XI0AVyPI1QhxNca4GuNcDU84rg1DagdVY5arMcfVmOdqcDjSHI4MhyOrDEeOw5HncBSU4ShyOEocjrIyHBUOR5XDUVOGo87haHA4mspwtDgcbQ5HRxmOLoejx+HoK8MxcIbjBYfjpTIcrzgcrzkcZ8pwnHM4Ljgcl8pwXHE4rp2G0Q6qxixXY46rMc/VWOBqLHI1lrgaHI4chyPP4Sgow1HkcJQ4HGVlOCocjiqHo6YMR53D0eBwNJXhaHE42hyOjjIcXQ5Hj8PRV4Zj4A7HN16Alz7m/8YrEvjGaxL8xhkJ6c6lxnQXUuO6S6kJ05XXpOnaayjt+EbsvbhgziXhNO+SdFpwSTktitKWJVHGsizKWlYkcoZVibxhTaJgWJcrasJyJU1ErqzZQJVNVN1CtW2284062f1Gg+x9o0n2dS2pA11b6lDXkToydb2OTT2vE1Pf69Q2EFA4XirD8YrD8ZrDcaYMxzmH44LDcakMxxWH41pqaljtiCvDkeBwJDkcKWU40hyODIcjqwxHjsOR53AUlOEocjhKHI6yMhwVDkeVw1FThqPO4WhwOJrKcLQ4HG0OR0cZji6Ho8fh6CvDMZCF45svPF4afHKvNH6515qA3JkmiM5D6GIMXY6ziW9ekclvXpOpb95oPv1wfDPuNWdKeM2bkl4LppTXoi0tWLJlBMu2rGDFJee06pJ3WnMpOK2LipawqGSJiMqWDYmKYVOiatiSqBm25eqaHbmGZleuqdlDrX3UPkCdQ3b0zS45/maPnHyzT051A6kRqsYoV8PH1fBzNTgc5xyOCw7HpTIcVxyOaw7HzZDCIW0HVWOOqzHP1VjgaixyNZa4GstcjRWuxipXY42rsc7VCHM1IlyNDa7GJldji6uxzdXY4WpwOFocjjaHo6MMR5fD0eNw9JXhGHzCcLxUhuMVh+M1h+NMGY5zDscFh+NSGY4rDsc1h+PGCsdn0w6qxhxXY56rscDVWORqLHE1lrkaK1yNVa7GGldjnasR5mpEuBobXI1NrsYWV2Obq7HD1djlauxxNfa5GhyOLoejx+HoK8Mx4HDcjoz+/YuPvRT4XF45+V1eOwVczpyConNLSHRhGRNdWsYlrgwTEteGSYkbw5TDUNrx9/GPJeZQch6lFtji36fJ0t9nyPLfZ8mKLie1qstLrekKUuumolfYVPKKmMpeG7aKYNNWFWzZaoJtl7rTjkvDadel6bQnaln2RW3LgahjOZToGo4keoZjib7hRG6gOZW71YxQNUa5Gj6uhp+rEeBqBLkaIa7GGFdjnKsxwdUQwjHMdiQ4HEkOR0oZjjSHI8PhyCrDkeNw5DkcBWU4ihyOEoejrAxHhcNR5XDUlOGoczgaHI6mMhwtDkebw9FRhqPL4ehxOPrKcAw4HLcfh+NbL0a/9VLKZ3rl5Te99gqYzryCtnNByHYhGLNdCsZdrpwmXK6dJl1unKZE0aG041sJzZxE0jAvkTIsyKU1i3IZzZJcVrOMcisov4oKa2z9W0US/laJRL5VJhu6itSmriq1patJbZvqXjumhteuqem1Z2sJ9m1twYGtIzh06TodufScjl36TieigeVUdGsZoWqMcjV8XA0/VyPA1QhyNUJcjTGuxjhXY4Kr4QlH1DCkdlA15rga81yNBa7GIleDw5HjcOQ5HAVlOIocjhKHo6wMR4XDUeVw1JThqHM4GhyOpjIcLQ5Hm8PRUYajy+HocTj6ynAMOBy3nzwcrzgcrzkcZ8pwnHM4Ljgcl8pwXHE4rjkcN8pwRJ2G0Q6qxhxXY56rscDVWORqLHE1lrkaK1wNDkeRw1HicJSV4ahwOKocjpoyHHUOR4PD0VSGo8XhaHM4OspwdDkcPQ5HXxmOAYfj1hOOb78Er3zotR+dBVjw2+ck9O0LMvbtSzKuu5Ka0F1LTepupKZMUa+htOPbifeSgnlbSrDgknZadMk4LblknZZFOcuKKG9ZFRUsaxJFw7pEyRCWKBsichXNhlxVsylX02yh+jZq7KDmLtv7dovsf7tNDr7dIYe6rtSRrid1rOtLnZgGXqemWy8KxysOx2sOx5kyHOccjgsOx6UyHFccjmsOx40yHFGp6WG1I8nhSCnDkeZwZDgcWWU4chyOPIejoAxHkcNR4nCUleGocDiqHI6aMhx1DkeDw9FUhqPF4WhzODrKcHQ5HD0OR18ZjgGH4xbC8Z2XHq8MPonXBr/EmSEgd64Jyl1oQnKXmjF0NY6uJ9DNJJv6TpRMfyem+fTD8Z2k17wuJbVgSnstmjJeS6as17ItJ1ix5QWrtoJgzaXotO5Scgq7lJ0iooplQ1S1bIpqli2JumFbomHYkWgaduVamj25tmZfrqM5QN1D1DtC/WN28p0BOf3OLRmhaoxyNXxcDT9XI8DVCHI1OBxXHI5rDseNMhxRDkdsSOGQtoOqMc/VWOBqLHI1lrgay1yNFa7GKldjjauxztUIczUiXI0NrsYmV2OLq7HN1djhauxyNfa4GhyOLoejx+HoK8Mx4HDccjjuRqgao1wNH1fDz9UIcDWCXI0QV2OMqzHO1eBwRDkcMSscn0k7UspwpDkcGQ5HVhmOHIcjz+EoKMNR5HCUOBxlZTgqHI4qh6OmDEedw9HgcDSV4WhxONocjo4yHF0OR4/D0VeGY8DhuOVw3L0Pxz+8/Ngrgc/2WuC3nQkCLudOQZcLp5DLpdOY6MoyLrq2TIhuLJMSUcOURMww7TCUdvxD8r2UZh6lF1BmEWWX2PI/5MjKP+TJ6j8UyJquKLWuK0mFdWWpiKnitWGqem2aal5btrpg29YQ7Niagl2XltOeS9tp36XjdCDqWg5FPcuRqG85lhgYTiRuDacSd4YRqsYoV8PH1fBzNQJcjSBXI8TVGONqjHM1Jrgak1wNIRxDa0dKGY40hyPD4cgqw5HjcOQ5HAVlOIocjhKHo6wMR4XDUeVw1JThqHM4GhyOpjIcLQ5Hm8PRUYajy+HocTj6ynAMOBy3HI47Rzi++3L0u6+kfLrXUn7dmVTAdO4VNF14hUyXXmO2K8G47VowYbsRTLpEnaZcYk7TLnHNUNrx3ZRmXiJtWJDIGBYlsoYluZxmWS6vWZEraFZRcQ2V1lE5zCLfrZCN71bJ5ndrZEtXl9rWNaR2dE2pXVPLa8/U9to3dbwObF3Boa0nOLL1BccuA6cTl1unU5c7pxGqxihXw8fV8HM1AlyNIFcjxNUY42qMczUmuBqTXI0pTzWG2g6qxjxXY4GrscjVWOJqLHM1OBxFDkeJw1FWhqPC4ahyOGrKcNQ5HA0OR1MZjhaHo83h6CjD0eVw9DgcfWU4BhyOWw7H3ScPx2sOx5kyHOccjgsOx6UyHFccjmsOx40yHFEOR4zDERcMox1UjXmuxgJXY5GrscTVWOZqrHA1Vrkaa1wNDkeFw1HlcNSU4ahzOBocjqYyHC0OR5vD0VGGo8vh6HE4+spwDDgctxyOO1k4vvdK5rXGJ3em8aPzALoIossQG/veFRn/3jWZ+N4NmdRFpaZ0MalpXVxqKO34Xuq9tGDBlhEs2rKCJZec07JL3mnFpeC0Kipa1kQly7qobAlLVAwRiaphQ6Jm2JSra7bkGpptuaZmB7V2UXsPdfbZwfe65PB7PXL0vT451g2kTnS3Uqe6O6kRqsYoV4PDcc7huOBwXCrDccXhuOZw3CjDEeVwxDgccTIzrHakORwZDkdWGY4chyPP4Sgow1HkcJQ4HGVlOCocjiqHo6YMR53D0eBwNJXhaHE42hyOjjIcXQ5Hj8PRV4ZjwOG45XDccTj+8ZXba4tPdGbxS5wbAhIXhqDEpSEkd6UZk7vWjMvdaCZQdBLFplB8ms38Y0Lz6YfjH9NeC7qM1KIuK7Vkynktm/JeK6aC16qtKFizlQTrtrIg7FJxirhUnTZcak6borplS9SwbIualh2JlmFXom3Yk+gY9uW6mgO5nuZQrq85QoNjdHuC7k7ZCFVjlKvh42r4uRoBrkaQqxHiaoxxNTgcUQ5HjMMRV4YjMaRwSNtB1VjgaixyNZa4GstcjRWuxipXY42rsc7VCHM1IlyNDa7GJldji6uxzdXY4WrscjX2uBr7XI0DrgaHY8DhuOVw3CnDcT9C1Rjlavi4Gn6uRoCrEeRqhLgaY1yNca7GBFdjkqvB4UhY4fhM2pHhcGSV4chxOPIcjoIyHEUOR4nDUVaGo8LhqHI4aspw1DkcDQ5HUxmOFoejzeHoKMPR5XD0OBx9ZTgGHI5bDsedMhz378PxT6/ee+3lM515+W3ngoDtQhC0XQpCLldOYy7XTuMuN04ToqhlUhSzTInilmmJhGHGYSjt+Kf0exnNglxWs4hySyi/jAorbPWfimTtn0pk/Z/KJKyrSEV0VakNXU1q01T32jI1vLZNTa8dW0uwa2sL9mwdwb5L1+nAped06NJ3OhINLMeiW8uJ6M5yKnFvGKFqjHI1fFwNP1cjwNUIcjVCXI0xrsY4V2OCqzHJ1ZjiagjhGFo7MhyOrDIcOQ5HnsNRUIajyOEocTjKynBUOBxVDkdNGY46h6PB4Wgqw9HicLQ5HB1lOLocjh6Ho68Mx4DDccvhuFOG494Rju+/Jr7vnxG/7lwqoLuQCuoupUKmK68x07XXuOnGa8IWFUzaYoIpW1ww7ZJwmnFJaobSju9nNAuirGVRImdYksgbliUKhhW5omZVrqRZkytr1lEljKoRVNtgm9+vk63vN8j295tkR9eS2tW1pfZ0Hal9U9frwNTzOjT1vY5sA8Gx7VZwYrsTnLrcOynCcaYMxzmH44LDcakMxxWH45rDcaMMR5TDEeNwxJXhSHA4kpYhtYOqscDVWORqLHE1lrkaK1yNVa4Gh6PC4ahyOGrKcNQ5HA0OR1MZjhaHo83h6CjD0eVw9DgcfWU4BhyOWw7HnTIc958wHGfKcJxzOC44HJfKcFxxOK45HDfKcEQ5HDEOR1wZjgSHIykYRjuoGgtcjUWuxhJXY5mrscLVWOVqrHE11rkaYa4Gh6PO4WhwOJrKcLQ4HG0OR0cZji6Ho8fh6CvDMeBw3HI47pThuJeF4wevPc4MPrlzjV/uQhOQu9QE0VUIXY+hm3E28YMomfxBjEz9IE6mdQmpGV1Saijt+EFm4QdZr0VbTrBkywuWbQXBikvRadWl5LTmUnZaF1UsYVHVEhHVLBsSdcOmRMOwJdE0bMu1NDtybc2uXEezh7r7qHeA+ofs6AcDcvyDW3LygztyqruXGqFqjHI1fFwNP1eDw3HF4bjmcNwowxHlcMQ4HHFlOBIcjiSZ/UFqOO1QhCPH4chzOArKcBQ5HCUOR1kZjgqHo8rhqCnDUedwNDgcTWU4WhyONoejowxHl8PR43D0leEYcDhuORx3ynDcczj+z2uHMyef6NziF11YAqJLS1DiyhCSuDaMSdwYxuWimgm5mGZSLq6ZQolplJxBqdn3Pv1w/J+s16IuJ7Wky0st6wpSK6ai16qp5LVmKnut2yqCsK0qiNhqgg2XutOmS8Npy6XptC1qWXZEbcuuqGPZk+ga9iV6hgOJvuFQbqA5krvVHMvdaU7Q/Sl6GKFqjHI1fFwNP1cjwNUIcjVCXI0xrsY4V2OCq8HhSHA4khyO1PDCIW0HVWORq7HE1VjmaqxwNVa5GmtcjXWuRpirEeFqbHA1NrkaW1yNba7GDldjl6uxx9XY52occDUOuRpHXA0Oxz2H48EZjjNlOM45HBccjktlOK44HNccjhtlOKIcjhiHI64MR4LDkeRwpJzh+EzakeNw5DkcBWU4ihyOEoejrAxHhcNR5XDUlOGoczgaHI6mMhwtDkebw9FRhqPL4ehxOPrKcAw4HLccjjtlOO45HA8fh+OHr0d/eCblM517+U0XXgHTpVfQdiUI2a4FY7YbwbhL1GnCJeY06RJ3mhIlLNOipGVGlLLMOgylHT/MvpfTLMrlNUtyBc0yKq6g0ioqr7H1H1ZI+IdVEvlhjWzo6lKbuobUlq4ptW1qee2Y2l67po7Xnq0r2Lf1BAe2vuDQZeB05HLrdOxy53Qiurecih4sI1SNUa6Gj6vh52oEuBpBrkaIqzHG1RjnakxwNSa5GlNcjWmuhhCOobUjx+HIczgKynAUORwlDkdZGY4Kh6PK4agpw1HncDQ4HE1lOFocjjaHo6MMR5fD0eNw9JXhGHA4bjkcd8pw3HM4Htzh+NEZ8f3onPh/dEECP7okQd2VVEh3LTWmu5EaN0W9Jkwxr0lT3GvKlhBM25KCGVtKMOuS1gylHT/KaRZFecuSqGBZligaViRKhlWJsmFNrqJZl6tqwnI1TQTVN1BjEzW32PaPWmTnR22y+6MO2dN1pfZ1PakDXV/q0DTwOjLdeh2b7rxObPeCU9uDQBGOcw7HBYfjUhmOKw7HNYfjRhmOKIcjxuGIK8OR4HAkORwpZTjSliG1g6qxyNVY4mosczVWuBqrXI01rsY6V4PDUedwNDgcTWU4WhyONoejowxHl8PR43D0leEYcDhuORx3ynDcczgePnk4zjkcFxyOS2U4rjgc1xyOG2U4ohyOGIcjrgxHgsOR5HCklOFIC4bRDqrGIldjiauxzNVY4WqscjXWuBrrXI0wVyPC1djganA4WhyONoejowxHl8PR43D0leEYcDhuORx3ynDcczgeIBw/PvM4N/gkLgx+iUtDQO5KE5S71oTkbjRjKDqOYhMoPsmmfpwg0z9Okpkfp8isLi01lHb8OLf447zXkqngtWwrClZsJcGqrSxYc6k4rbtUncIuNaeIqG7ZEDUsm6KmZUuiZdiWaBt2JDqGXbmuZk+up9mX62sO0OAQ3R6hu2N28uN7cvrjBzJC1Rjlavi4Gn6uRoCrEeRqcDiiHI4YhyOuDEeCw5HkcKSU4UiTuR9nhtMOCkdBGY4ih6PE4Sgrw1HhcFQ5HDVlOOocjgaHo6kMR4vD0eZwdJTh6HI4ehyOvjIcAw7HLYfjThmOew7HA4fjcWT0n88czp18LhdOfpdLp4DoyhIUXVtCohvLmETUMC4RM0xIxA2TcgnNlFxSMy2X0syg9CzKzL336Yfjn/NeS/9cIMu6otSKriS1qitLrZkqXuumqlfYVPOK2OqCDVtDsGlrCrZcWk7bLm2nHZeO066oa9kT9Sz7or7lQGJgOJS4NRxJ3BmO5e41J3IPmlO5R80IVWOUq+Hjavi5GgGuRpCrEeJqjHE1xrkaE1yNSa7GFFeDw5HmcGSGFw5ZOwrKcBQ5HCUOR1kZjgqHo8rhqCnDUedwNDgcTWU4WhyONoejowxHl8PR43D0leEYcDhuORx3ynDcczgeOByPQjjOORwXHI5LZTiuOBzXHI4bZTiiHI4YhyOuDEeCw5HkcKSU4UhzODLOcAy/HQVlOIocjhKHo6wMR4XDUeVw1JThqHM4GhyOpjIcLQ5Hm8PRUYajy+HocTj6ynAMOBy3HI47ZTjuORwPHI5HRzh+cjb6k3Mpn+5Cyq+7lAqYrryCpmuvkOnGa8wWFYzbYoIJW1ww6ZJwmnJJOk27pJxmRGnLrChjmXMYSjt+kl/8ScGwJFfULMuVNCtyZc0qqqyh6jqqhVnkJ3Wy8ZMG2fxJk2zpWlLburbUjq4jtWvqeu2Zel77pr7XgW0gOLTdCo5sd4Jjl3unE5cHp1OXR6cRqsYoV8PH1fBzNQJcjSBXI8TVGONqjHM1Jrgak1yNKa7GNFdjhqshhGPuJ9nhtEMRjiKHo8ThKCvDUeFwVDkcNWU46hyOBoejqQxHi8PR5nB0lOHocjh6HI6+MhwDDscth+NOGY57DscDh+PRE46fnoMLH7r0s8BPr0jwp9ck9NMbMqaLSo3rYlITurjUpCnhNWVKek2bUl4ztrRg1pYRzNmyhqG046cFzZKoaFkWlSwrorJlVaJiWJOoGtYlaoawXF0TkWtoNuSamk3U2kLtbdTZYbs/7ZK9n/bI/k/75EA3kDrU3Uod6e6kjk33XiemB69T06MXheOCw3GpDMcVh+Oaw3GjDEeUwxHjcMSV4UhwOJIcjpQyHGkOR4bDkXUaUjuoGktcjWWuxgpXY5WrscbVWOdqhLkaEa4Gh6PF4WhzODrKcHQ5HD0OR18ZjgGH45bDcacMxz2H44HD8fjJw3HB4bhUhuOKw3HN4bhRhiPK4YhxOOLKcCQ4HEkOR0oZjjSHI8PhyHoNox1UjSWuxjJXY4WrscrVWONqrHM1wlyNCFdjg6uxydXY4mpwOLocjh6Ho68Mx4DDccvhuFOG457D8cDheORw/Ozc7cLiE11a/BJXhoDEtSEocWMIyUU1Y3IxzbhcXDOBEpMoOYVS02zmZ2ky+7MMmftZlgylHT8rLP2s6LVsKnmtmMpeq7aKYM1WFazbaoKwS90p4tJw2nBpOm2KWpYtUduyLepYdiS6hl2JnmFPom/YlxtoDuRuNYdyd5ojdH+MHk7Q4ykboWqMcjV8XA0/VyPA1QhyNUJcjTGuBocjweFIcjhSynCkORwZDkdWEY75n+WG0w4KR4nDUVaGo8LhqHI4aspw1DkcDQ5HUxmOFoejzeHoKMPR5XD0OBx9ZTgGHI5bDsedMhz3HI4HDsejMhxPI6P/cv6xC4HPdinwu1w5BVyunYIuN04hUdQyJopZxkVxy4REwjApkTRMSaQM03JpzYxcRjMrl9XModz8e59+OP6l6LX8LyWy8i9lsqqrSK3pqlLruppU2FT3ipgaXhumptemrSXYsrUF27aOYMel67Tr0nPac+k77YsGlgPRreVQdGc5krg3HEs8GE4kHg2nck+aEarGKFfDx9XwczUCXI0gVyPE1RjjaoxzNSa4GpNcjSmuxjRXY4arweHIDS8csnaUOBxlZTgqHI4qh6OmDEedw9HgcDSV4WhxONocjo4yHF0OR4/D0VeGY8DhuOVw3CnDcc/heOBwPCrD8eQMxwWH41IZjisOxzWH40YZjiiHI8bhiCvDkeBwJDkcKWU40hyODIcjqwxHzhmO4bejxOEoK8NR4XBUORw1ZTjqHI4Gh6OpDEeLw9HmcHSU4ehyOHocjr4yHAMOxy2H404ZjnsOxwOH41EZjidHOH5+QXw/vyR+3ZVUQHctFdTdSIVMUa8xU8xr3BT3mrAlBJO2pGDKlhJMu6SdZlwyTrMuWac5Uc4y7zCUdvy8uPTzkmFZomxYkatoVuWqmjW5mmYd1cOoEUHNDbb58xbZ+nmbbP+8Q3Z0XaldXU9qT9eX2jcNvA5Mt16HpjuvI9u94Nj2IDixPQpOXZ6cFOG4VIbjisNxzeG4UYYjyuGIcTjiynAkOBxJDkdKGY40hyPD4cgqw5GjcMz/PD+cdlA4yspwVDgcVQ5HTRmOOoejweFoKsPR4nC0ORwdZTi6HI4eh6OvDMeAw3HL4bhThuOew/HA4XhUhuPJE45fXMhcanzoyo+uA+gmyEK/iJKxX8TI+C/iZEKXkJrUJaWmdCmpaVPaa8aU8Zo1Zb3mbDnBvC1vGEo7flHSLLuUnVZEFcuqqGpZE9Us6xJ1Q1iiYYhINA0bci3NplxbsyXX0Wyj7g7q7aL+Htv/xYAc/OKWHP7ijhzp7qWOdQ9SJ7pHqVPTk9cIVYPDccXhuOZw3CjDEeVwxDgccWU4EhyOJIcjpQxHmsOR4XBkleHIcTjyTkNqB1VjmauxwtVY5WqscTXWuRphrkaEq7HB1djkanA4uhyOHoejrwzHgMNxy+G4U4bjnsPxwOF4VIbj6ROG41IZjisOxzWH40YZjiiHI8bhiCvDkeBwJDkcKWU40hyODIcjqwxHjsOR9xpGO6gay1yNFa7GKldjjauxztUIczUiXI0NrsYmV2OLq7HN1djhanA4BhyOWw7HnTIc9xyOBw7HozIcTxyOf71wuHTyia4sftG1JSC6sQQlooaQRMwwJhE3jMslNBNySc2kXEozhdLTKDODsrNs7l9zZP5f82Qo7fjXstSKqeK1aqp6rZlqXuu2uiBsawgitqZgw6XltOnSdtpy6Thti7qWHVHPsivqW/YkBoZ9iVvDgcSd4VDuXnMk96A5lnvUnKCnU/RmhKoxytXwcTX8XI0AVyPI1QhxNca4GuNcjQmuBocjzeHIcDiyynDkOBx5Dkdh4V8Ln1k7qBorXI1VrsYaV2OdqxHmakS4GhtcjU2uxhZXY5urscPV2OVq7HE19rkaB1yNQ67GEVeDw/HE4XjzPhz/dvHepZfPdiXw264FAduNIOgSdQq5xJzGXOJO46KEZUKUtEyKUpYpibRhWiJjmJHIGmblcpo5ubxmXq6gWXjv0w/Hv5W9Vv6tQlb/rUrW/q1G1nV1qbCuIRXRNaU2TC2vTVPba8vU8dq2dQU7tp5g19YX7LkMnPZdbp0OXO6cDkX3liPRg+VY9Gg5kXgynEq8MYxQNUa5Gj6uhp+rEeBqBLkaIa7GGFdjnKsxwdWY5GpMcTWmuRozXI1ZrsYcV2N44ZC1o8LhqHI4aspw1DkcDQ5HUxmOFoejzeHoKMPR5XD0OBx9ZTgGHI5bDsedMhz3HI4HDsejMhxPHI43znBcKsNxxeG45nDcKMMR5XDEOBxxZTgSHI4khyOlDEeaw5HhcGSV4chxOPIcjoIQjuG3o8LhqHI4aspw1DkcDQ5HUxmOFoejzeHoKMPR5XD0OBx9ZTgGHI5bDsedMhz3HI4HDsejMhxPHI437nD88pL4fnlF/L+8JoFf3pCgLioV0sWkxnRxqXFTwmvClPSaNKW8pmxpwbQtI5ixZQWzLjmnOZe807xLwWnBYSjt+GV5+ZcVw4pE1bAqUTOsydU163INTViuqYmg1gZqb6LOFtv+ZZfs/LJHdn/ZJ3u6gdS+7lbqQHcndWi69zoyPXgdmx69TmxPglPbG4EiHFccjmsOx40yHFEOR4zDEVeGI8HhSHI4UspwpDkcGQ5HVhmOHIcjz+EoKMKx8MvicNpB4ahyOGrKcNQ5HA0OR1MZjhaHo83h6CjD0eVw9DgcfWU4BhyOWw7HnTIc9xyOBw7HozIcTxyON7Jw/OpS5krjk7vW+OVuNAEUDaJYCMXH2PivEmTiV0ky+asUmdKlpaZ1GakZXVZq1pTzmjPlveZNBa8FW9EwlHb8qqJZcak6rbrUnNZEdcu6qGEJi5qWiETLsCHRNmxKdAxbcl3NtlxPsyPX1+yiwR663Ud3B+zwV/fk6FcP5PhXj+RE9yR1qnsjNULVGOVq+LgaHI4ohyPG4Ygrw5HgcCQ5HCllONIcjgyHI6sMR47DkedwFJThKDoNqR1UjRWuxipXY42rsc7VCHM1IlyNDa7GJldji6uxzdXgcAw4HLccjjtlOO45HA8cjkdlOJ44HG8+eTiuOBzXHI4bZTiiHI4YhyOuDEeCw5HkcKSU4UhzODIcjqwyHDkOR57DUVCGo+g1jHZQNVa4GqtcjTWuxjpXI8zViHA1Nrgam1yNLa7GNldjh6uxy9XY42pwOO45HA8cjkdlOJ44HG84HG9HRv/90uHKyedy7eR3uXEKiKKWoChmCYniljGJhGFcImmYkEgZJuXSmim5jGZaLquZQblZlJ9DhXm28O9FMpR2/HtValVXk1oz1b3WTQ2vsKnpFbG1BBu2tmDT1hFsuXSdtl16Tjsufadd0cCyJ7q17IvuLAcS94ZDiQfDkcSj4VjuSXMi90ZzKvdWM0LVGOVq+Lgafq5GgKsR5GqEuBpjXI1xrsYEV2OSqzHF1eBw5DgceQ5HQRmOIoejtPjvpc+sHVSNVa7GGldjnasR5mpEuBobXI1NrsYWV2Obq7HD1djlauxxNfa5GgdcjUOuxhFX45irccLVeB+O/7h878rLZ7r28ptuvAK2qCBoiwlCtrhgzCXhNO6SdJpwSTlNitKWKVHGMi3KWmYkcoZZibxhTqJgmJcrahbkSprF9z79cPxH1aO2ytb+o07W/6NBwv/RJBFdS2pD15ba1HWktkxdr21Tz2vH1PfatQ0Ee7Zbwb7tTnDgcu906PLgdOTy6HQserKciN5YTkVvLSNUjVGuho+r4edqBLgaQa5GiKsxxtUY52pMcDUmuRpTXI1prsYMV2OWqzHH1ZjnagwvHJ521JThqHM4GhyOpjIcLQ5Hm8PRUYajy+HocTj6ynAMOBy3HI47ZTjuORwPHI5HZTieOBxvOBxvhXBccTiuORw3ynBEORwxDkdcGY4EhyPJ4Ugpw5HmcGQ4HFllOHIcjjyHo6AMR5HDURLCMeR21JThqHM4GhyOpjIcLQ5Hm8PRUYajy+HocTj6ynAMOBy3HI47ZTjuORwPHI5HZTieOBxvOBxvPeH49RW49qEbPwv8OkqCv46R0K/jZEyXkBrXJaUmdCmpSVPaa8qU8Zo2Zb1mbDnBrC0vmLMVBPMuRacFl5LTosNQ2vHrmmVVom5Yk2gY1iWahrBcSxORa2s25DqaTdTdQr1t1N9hu78ekL1f35L9X9+RA9291KHuQepI9yh1bHryOjG98To1vfWicFxzOG6U4YhyOGIcjrgyHAkOR5LDkVKGI83hyHA4sspw5DgceQ5HQRmOIoejxOEoa4baDqrGKldjjauxztUIczUiXA0OR5fD0eNw9JXhGHA4bjkcd8pw3HM4Hjgcj8pwPHE43nA43kI4fnPlcW3wSdwY/HJRTUAupgnKxTUhlBhDyXGUmmCTv0mTqd9kyPRvsmRGl5Oa1eWl5nQFqXlT0WvBVPJaNJUtQ2nHb2qaVZe605pLw2ndpekUFrUsEVHbsiHqWDYluoYtiZ5hW6Jv2JEbaHblbjV7cneafXR/gB4O0eMRO/7NEzn5zRty+pu3ZISqMcrV8HE1/FyNAFeDw5HgcCQ5HCllONIcjgyHI6sMR47DkedwFJThKHI4ShyOsmBI7aBqrHI11rga61yNMFcjwtXY4GpscjW2uBrbXI0drsYuV4PDcc/heOBwPCrD8cTheMPhePvJw3HN4bhRhiPK4YhxOOLKcCQ4HEkOR0oZjjSHI8PhyCrDkeNw5DkcBWU4ihyOEoejLDWMdlA1Vrkaa1yNda5GmKsR4WpscDU2uRpbXI1trsYOV2OXq7HH1djnahxwNTgcTxyONxyOt8pwvBsZ/c+rj10LfLYbgd8l6hRwiTkFXeJOIVHCMiZKWsZFKcuERNowKZExTElkDdNyOc2MXF4zK1fQzKHiPCotoPIiG0o7/rMutaZrSK3rmlJhU8srYmp7bZg6Xpu2rmDL1hNs2/qCHZeB067LrdOey53TvujeciB6sByKHi1HEk+GY4k3hhOJt4ZTuXeaEarGKFfDx9XwczUCXI0gVyPE1RjjaoxzNSa4GpNcjSmuxjRXY4arweEocjhKHI6yMhyVpf+sfGbtoGqscTXWuRphrkaEq7HB1djkamxxNba5GjtcjV2uxh5XY5+rccDVOORqHHE1jrkaJ1yN9+H47dXob6+lfLobKb8p6hUwxbyCprhXyJYQjNmSgnFbSjDhknaadMk4TblknaZFOcuMKG+ZFRUscxJFw7xEybAgUTYsylU0S+99+uH4bd2jsYaa6yz82xaJ/LZNNn7bIZu6rtSWrie1retL7ZgGXrumW689053Xvu1ecGB7EBzaHgVHLk9Oxy5vnE5c3jqdit5ZRqgao1wNH1fDz9UIcDWCXI0QV2OMqzHO1ZjgakxyNaa4GtNcjRmuxixXY46rMc/VWOBqDC8cnnY0OBxNZThaHI42h6OjDEeXw9HjcPSV4RhwOG45HHfKcNxzOB44HI/KcDxxON5wON4qw/HuE4bjRhmOKIcjxuGIK8OR4HAkORwpZTjSHI4MhyOrDEeOw5HncBSU4ShyOEocjrIyHBUhHENuR4PD0VSGo8XhaHM4OspwdDkcPQ5HXxmOAYfjlsNxpwzHPYfjgcPxqAzHE4fjDYfjrTIc7zzh+N21zI3Gh6J+FAugeJCFfpcgY79LkvHfpciELi01qctITemyUtOmnNeMKe81ayp4zdmKgnlbSbBgKwsWXSpOSw5DacfvGpY1UdOyLtEyhCXahohEx7Ah19VsyvU0W3J9zTYa7KDbXXS3x/Z/d08OfvdADn/3SI50T1LHujdSJ7q3Uqemd14jVA0OR5TDEeNwxJXhSHA4khyOlDIcaQ5HhsORVYYjx+HIczgKynAUORwlDkdZGY4Kh6OqGWo7qBprXI11rkaYqxHhamxwNTa5GhyOAYfjlsNxpwzHPYfjgcPxqAzHE4fjDYfjrTIc7yAcv792u7H4JKIGv0TMEJCIG4JyCU1ILqkZk0tpxlF6AmUmUXaKTf8+R2Z+nyezvy+QOV1Ral5XklrQlaUWTRWvJVPVMpR2/L6hWbM1BesuLaewS9sp4tJx2hB1LZuinmVL1LdsSwwMOxK3hl2JO8Oe3L1mX+5BcyD3qDlET0fozTF6e8JOf/+OjFA1RrkaPq6Gn6sR4GoEuRohrgaHI83hyHA4sspw5DgceQ5HQRmOIoejxOEoK8NR4XBUBUNqB1VjjauxztUIczUiXI0NrsYmV2OLq7HN1djhauxyNfa4GvtcDQ7HE4fjDYfjrTIc7zgcH41QNUa5Gj6uhp+rEeBqBLkaIa7GGFdjnKsxwdXgcOQ4HHkOR0EZjiKHo8ThKCvDUeFwVKWG0Q6qxhpXY52rEeZqRLgaG1yNTa7GFldjm6uxw9XY5WrscTX2uRoHXI1DrsYRV4PD8Y7D8dH7cPzf6/duvHy2qMBviwkCtrgg6JJwCrkkncZcUk7jorRlQpSxTIqylimJnGFaIm+YkSgYZuWKmjm5kmZerqxZQJVFVF1CtaG04/82pdZ1Lamwri0V0XWkNkxdr01Tz2vL1Pfatg0EO7Zbwa7tTrDncu+07/LgdODy6HQoerIcid5YjkVvLScS7wynEh8ZRqgao1wNH1fDz9UIcDWCXI0QV2OMqzHO1ZjgakxyNaa4GtNcjRmuxixXY46rweGocDiqHI6aZvkzbAdVY52rEeZqRLgaG1yNTa7GFldjm6uxw9XY5WrscTX2uRoHXI1DrsYRV+OYq3HC1Xgfjv+6IT5dVMqvi0kFdHGpoCnhFTIlvcZMKa9xW1owYcsIJm1ZwZRLzmnaJe8041JwmhUVLXOikmVeVLYsSFQMixJVw5JEzbD83qcfjv9qerTWUTuMOhG28V9dsvlfPbL1X32yrRtI7ehupXZ1d1J7pnuvfdOD14Hp0evQ9iQ4sr0RHNveCk5c3jmdunzkpA5HlMMR43DEleFIcDiSHI6UMhxpDkeGw5FVhiPH4chzOArKcBQ5HCUOR1kZjgqHo8rhqA07HJ52tDgcbQ5HRxmOLoejx+HoK8Mx4HDccjjulOG453A8cDgeleF44nC84XC8VYbjHYfjo08ejiiHI8bhiCvDkeBwJDkcKWU40hyODIcjqwxHjsOR53AUlOEocjhKHI6yMhwVDkeVw1HzhmPI7WhxONocjo4yHF0OR4/D0VeGY8DhuOVw3CnDcc/heOBwPCrD8cTheMPheKsMxzsOx0eycPzhRiaq8cnFNH65uCaAEkGUDKHUGBv/Q5pM/CFDJv+QJVO6nNS0Li81oytIzZqKXnOmkte8qey1YKsIFm1VwZKtJlh2GEo7/tCyrIvalrCoY4lIdA0bEj3DpkTfsCU30GzL3Wp25O40u+h+Dz3so8cDdviHJ3L0hzfk+A9vyYnundSp7iOpEarGKFfDx9XgcCQ4HEkOR0oZjjSHI8PhyCrDkeNw5DkcBWU4ihyOEoejrAxHhcNR5XDUlOGoa4baDqrGOlcjzNWIcDU2uBqbXI0trsY2V4PDcc/heOBwPCrD8cTheMPheKsMxzsOx0ccjv++cYtafKKYxS+KWwISCUNQImkISaQMY3JpzbhcRjMhl9VMotwUyk+jwgyb/e8imfvvEpn/7zJZ0FWkFnVVqSVdTWrZVLcMpR3/3dKs29qCsK0jiLh0nTZcek6bLn2nLdHAsi26teyI7iy7EveGPYkHw77Eo+FA7klzKPdGcyT3VnOM3p2gj07Rn0aoGqNcDR9Xw8/VCHA1glyNEFdjjKsxztXgcOQ4HHkOR0EZjiKHo8ThKCvDUeFwVDkcNWU46oIhtYOqsc7VCHM1IlyNDa7GJldji6uxzdXY4WrscjX2uBr7XI0DrsYhV4PD8Y7D8RGH409COKIcjhiHI64MR4LDkeRwpJThSHM4MhyOrDIcOQ5HnsNRUIajyOEocTjKynBUOBxVDkdNGY661DDaQdVY52qEuRoRrsYGV2OTq7HF1djmauxwNXa5GntcjX2uxgFX45CrccTVOOZqnHA13ofjf27ei3r5TDEvvynuFbAlBEFbUhCypQRjLmmncZeM04RL1mlSlLNMifKWaVHBMiNRNMxKlAxzEmXDvFxFsyBX1SzK1TRLqL6MGkNpx/+0pcL/0yERXVdqQ9eT2tT1pbZMA69t063XjunOa9d2L9izPQj2bY+CA5cnp0OXN05HLm+djkXvLCeijyynoj9ZRqgao1wNH1fDz9UIcDWCXI0QV2OMqzHO1ZjgakxyNaa4GtNcjRmuxixXY46rMc/VWOBqcDjqHI6GZuWza0dHGY4uh6PH4egrwzHgcNxyOO6U4bjncDxwOB6V4XjicLzhcLxVhuMdh+MjDsef3OH4Y5T4/hgj/j/GSUCXkArqklIhXUpqzJT2GjdlvCZMWa9JW04wZcsLpm0FwYxL0WnWpeQ051J2mhdVLAuiqmVRVLMsSdQNyxINw8p7n344/th262jCqBtBvQ3U32RbfxyQ7T/ekp0/3pFd3b3Unu5Bal/3KHVgevI6NL3xOjK99Tq2vROc2D4SnNr+JFCEI8bhiCvDkeBwJDkcKWU40hyODIcjqwxHjsOR53AUlOEocjhKHI6yMhwVDkeVw1FThqPO4WgMOxzudnSU4ehyOHocjr4yHAMOxy2H404ZjnsOxwOH41EZjicOxxsOx1tlON5xOD7icPzpk4cjxuGIK8OR4HAkORwpZTjSHI4MhyOrDEeOw5HncBSU4ShyOEocjrIyHBUOR5XDUVOGo87haHjDMcx2dJTh6HI4ehyOvjIcAw7HLYfjThmOew7HA4fjURmOJw7HGw7HW2U43nE4PuJw/AnC8UHUI2bwScQNfrmEJiCX1ATlUpoQSo+hzDjKTrDJD3Jk6oM8mf6gQGZ0RalZXUlqTleWmjdVvBZMVa9FU81ryVYXLNsaghVbcyjt+KBjCYu6loioZ9kQ9S2bEgPDlsStYVvizrAjd6/ZlXvQ7Mk9avbR0wF6c4jeHrHjD96Rkw8+Iqcf/ImMUDVGuRo+roafqxHganA40hyODIcjqwxHjsOR53AUlOEocjhKHI6yMhwVDkeVw1FThqPO4WhwOJqGobaDqhHmakS4GhtcjU2uxhZXY5urscPV2OVqcDieOBxvOBxvleF4x+H4iMPxJ2U4Pow6xJx8LnEnvyhhCYiSlqAoZQlJpA1jEhnDuETWMCGX00zK5TVTcgXNNCrOoNIsKs+x+Q8rZOHDKln8sEaWdHWpZV1DakXXdBpKOz7saMK2riBi6wk2bH3BpsvAacvl1mnb5c5pR3Rv2RU9WPZEj5Z9iSfDgcQbw6HEW8OR3DvNsdxHmhO5P2lO0f+OUDVGuRo+roafqxHgagS5GiGuxhhXY5yrMcHVmORqcDiKHI4Sh6OsDEeFw1HlcNSU4ahzOBocjqbXkNpB1QhzNSJcjQ2uxiZXY4ursc3V2OFq7HI19rga+1yNA67GIVfjiKtxzNXgcPyvMxwxDkdcGY4EhyPJ4Ugpw5HmcGQ4HFllOHIcjjyHo6AMR5HDUeJwlJXhqHA4qhyOmjIcdQ5Hg8PRXAHDaAdVI8zViHA1Nrgam1yNLa7GNldjh6uxy9XY42rsczUOuBqHXI0jrsYxV+OEq/E+HM+io89iUj5dXMpvSngFTEmvoCnlFbKlBWO2jGDclhVMuOScJl3yTlMuBadpUdEyIypZZkVly5xExTAvUTUsSNQMi3J1zZJcQ7Ms19SsoNZQ2vGsKxV51iMbz/pkUzeQ2tLdSm3r7qR2TPdeu6YHrz3To9e+7UlwYHsjOLS9FRy5vHM6dvnI6cTlT06nov+1jFA1RrkaPq6Gn6sR4GoEuRohrsYYV2OcqzHB1ZjkakxxNaa5GjNcjVmuxhxXY56rscDVWORqLHE1OBwtzepn144eh6OvDMeAw3HL4bhThuOew/HA4XhUhuOJw/GGw/FWGY53HI6POBx/Uobjf93heB4DcR/zP0+QwPMkCT5PkZAuLTWmy0iN67JSE6ac16Qp7zVlKnhN24qCGVvp/++lPrPbthYFjGoQ6r032xJ7kSYeJ07sxLYo9t5JNfYieQoPMHBRDs53Xn6EXmuPYQsObCXBoUvZ6cil4nTsUnU6EdUsp6K65UzUsJxLNA0XP/33cfzWcetqPsg9aK7Q4zV68qFnPwv89kKCv/VI6Lc+CesGUhHdUCqqG0nFTGOvuGnidWOaet3aZgKK404ZR4LjuOc4kso4UhxHmuPIKOPIchw5jiOvjKPAcRQ5jpIyjjLHUeE4qso4ahxHneNoKONoLjoO9x1djuNBGccjx/HEcTwr43jhOHocR18Zx4DjGHIcI2UcY45jwnFMlXHM/mUcd8o4EhzHPceRVMaR4jjSHEdGGUeW48hxHHllHAWOo8hxlJRxlDmOCsdRVcZR4zjqHEdDGUfTG8ci7+hyHA/KOB45jieO41kZxwvH0eM4+so4BhzHkOMYKeMYcxwTjmOqjGMGcXz87nZnWZFIGFYl7g1rEknDulxKsyGX1mzKZTRbKLuNcjsov8v2PhbI/sciOfhYIoe6stSRriJ1rKtKnZhqXqemuteZqeF1bmsKLmythdzxsWv54PLgdCV6tFyLniw+0bPFL/FiCEj0DEGJviEkN9CE5YaaiNxIE0XjGJrE0fSG3X6ckSVaY5nXWOE1VnmNNV5jndfY4DU4jizHkeM48so4ChxHkeMoKeMocxwVjqOqjKPGcdQ5joYyjibH0TIs9A5a4wOvccVrXPMaPl7Dz2sEeI0grxHiNcK8Bscx5jgmHMdUGceM45gvLf/+/X/uBCsuCadVl3unNZek07ooZdkQpS2booxlSyJr2JbIGXYk8oZduYJmT66o2ZcraQ5Q+RBVjlD1mJ38XiOnv9fJ2e8Ncq5rSl3oWk4LueP3ruaD6cHryvYouLY9CXy2Z4Hf5cUp4NJzCrr0nUKigSUsGloiopElKjE2xCQmhrjE1HAjN9Pcys01S7TGMq+xwmus8hprvMY6r7HBa2zyGlu8xjavscNr7PIae7wGx1HmOCocR1UZR43jqHMcDWUcTY6j5bWgO2iND7zGFa9xzWv4eA0/rxHgNYK8RojXCPMaEV4jymvEeI04r3HDa1hx3CnjSHAc9xxHUhlHiuNIcxwZZRxZjiPHceSVcRQ4jiLHUVLGUeY4KhxHVRlHjeOocxwNZRxNjqN1ARZxB63xgde44jWueQ0fr+HnNQK8RpDXCPEaYV4jwmtEeY0YrxHnNW54jZ9x/HFHVnQJqVXdvdSaLim1bkp5bZjSXpumjNeWLSvYtuUEO7a8YNel4LTnUnTadyk5HYjKlkNRxXIkqlqOJWqGE4m64VSiYTiTa2rO5VqaC7m2ZiF3/PEgdfXHI7n+44n4/ngmft2LVEDXkwrq+lIh08ArbBp6RUwjr6htLIjZJoK4bSq4cZk53brMndRxJDiOe44jqYwjxXGkOY6MMo4sx5HjOPLKOAocR5HjKCnjKHMcFY6jqoyjxnHUOY6GMo4mx9HiONqGy193xyPH8cRxPCvjeOE4ehxHXxnHgOMYchwjZRxjjmPCcUyVccw4jrknjk93ILGC7ldRco2tf0qRjU9psvkpQ7Z0WaltXU5qR5eX2jUVvPZMRa99U8nrwFYWHNoqgiNbVXDsUnM6cak7nbo0nM5ETcu5qGW5ELUtlz/993F8enB71FzJPWmu5Z41PvTiR70A6gdZ6NOAhD8NSeTTiER1Y6mYbiIV102lbkwzr1vT3IviSHAc9xxHUhlHiuNIcxwZZRxZjiPHceSVcRQ4jiLHUVLGUeY4KhxHVRlHjeOocxwNZRxNjqPFcbR/QRzuOx45jieO41kZxwvH0eM4+so4BhzHkOMYKeMYcxwTjmOqjGPGccz/fRwJjuOe40gq40hxHGmOI6OMI8tx5DiOvDKOAsdR5DhKyjjKHEeF46gq46hxHHWOo6GMo8lxtDiOtjSORd7xyHE8cRzPyjheOI4ex9FXxjHgOIYcx0gZx5jjmHAcU2UcM45jznH8eeeWsKyI7i2roqRlTSJlWJdIGzYkMoZNuaxmSy6n2ZbLa3ZQYRcV91Bpnx38WSaHf1bI0Z9VcqyrSZ3o6lKnuobUmanpdW5qeV2Y2l6Xts5C7vjz0XLl8uR07fLs5BO9WPyiniUg6luCEgNDSGJoCEuMDBG5sSYqN9HE5KaaOJrdoPktel2iNZZ5jRVeY5XXWOM11nmNDV5jk9fY4jU4jgLHUeQ4Sso4yhxHheOoKuOocRx1jqOhjKPJcbQ4jrYyjo5hoXfQGle8xjWv4eM1/LxGgNcI8hohXiPMa0R4jSivwXHMOI45x/H6M46/7v4nIVix3QtWbUnBmkvKad0l7bThknHaFGUtW6KcZVuUt+xIFAy7EkXDnkTJsC9X1hzIVTSHclXNEaodo/oJapyys7+a5PyvFrn4q00udR2nhdzx16PmyvTkdW169vLZXgR+W08QsPUFQZeBU8hl6BR2GTlFRGNLVDSxxERTS1xiZriRmBtuJV4NS7TGMq+xwmus8hprvMY6r7HBa2zyGlu8xjavscNr7PIae7zGPq9xwGtwHDWOo85xNJRxNDmOFsfRVsbR8VrQHbTGFa9xzWv4eA0/rxHgNYK8RojXCPMaEV4jymvEeI04r3HDa1hxJDiOe44jqYwjxXGkOY6MMo4sx5HjOPLKOAocR5HjKCnjKHMcFY6jqoyjxnHUOY6GMo4mx9HiONrKODqXYBF30BpXvMY1r+HjNfy8RoDXCPIaIV4jzGtEeI0orxHjNeK8xg2v8TOOzwmy8vmerH5OkjVdSmpdl5ba0GWkNk1Zry1TzmvblPfasRUEu7aiYM9WEuy7lJ0OXCpOhy5VpyNRzXIsqltORA3LqUTTcCbRMpxLtA0Xch3NpVxXs5A7Pj/JPF8z3+cX4v/cI4HPfRLUDaRCuqFUWDeSipjGXlHTxCtmmnrFbTPBjW0uuLW9ChRx3HMcSWUcKY4jzXFklHFkOY4cx5FXxlHgOIocR0kZR5njqHAcVWUcNY6jznE0lHE0OY4Wx9FWxtHhOLqGd7/ojmdlHC8cR4/j6CvjGHAcQ45jpIxjzHFMOI6pMo4ZxzHnOF5lcXxJyNxrVuSSmlWUWkPpdZTZYJtfsmTrS45sf8mTHV1BaldXlNrTlaT2TWWvA1PF69BU9Tqy1QTHtrrgxNYQnLo0nc5cWk7nLm2nC1HHcinqWt799N/H8eXJ4dlwLfei8cn1NH65viaABkE0DKFRmEW+jEn0y4TEvkxJXDeTutHNpW51r1JLtMYyr8FxpDiONMeRUcaR5ThyHEdeGUeB4yhyHCVlHGWOo8JxVJVx1DiOOsfRUMbR5DhaHEdbGUeH4+j+gjgcdzwr43jhOHocR18Zx4DjGHIcI2UcY45jwnFMlXHMOI45x/H67+O45ziSyjhSHEea48go48hyHDmOI6+Mo8BxFDmOkjKOMsdR4TiqyjhqHEed42go42hyHC2Oo62Mo8NxdKVxLOyOZ2UcLxxHj+PoK+MYcBxDjmOkjGPMcUw4jqkyjhnHMec4XpVx/J1wuHdacUk6rYpSljVR2rIuylg2JLKGTYmcYUsib9iWK2h25IqaXbmSZg+V91HlAFUP2dHfNXL8d52c/N0gp7qm1JmuJXWua0tdmDpel6au1zvTg2Yhd/z9bLl2eXHyufSc/C59p4BoYAmKhpaQaGQJS4wNEYmJISoxNcTkZpq43FxzI/equUVvS7TGMq+xwmus8hprvMY6r7HBa2zyGlu8xjavscNrcBxljqPCcVSVcdQ4jjrH0VDG0eQ4WhxHWxlHh+PochwPloXeQWtc8xo+XsPPawR4jSCvEeI1wrxGhNeI8hoxXiPOa3Acbz/j+Cfx073XiinptWpLCdZsacG6LSPYcMk6bbrknLZc8k7booJlR1S07IpKlj2JsmFfomI4kKgaDuVqmiO5uuZYrqE5Qc1T1DpD7XN28U+HXP7TJe/+eRAs5I5/njXXphcvn6nn5Tf1vQK2gSBoGwpCtpEg7DJ2irhMnKIuU6eYaGaJi+aWG9Gr5VbizbBEayzzGiu8xiqvscZrrPMaG7zGJq+xxWts8xo7vMYur7HHa+zzGge8xiGvccRrcBxNjqPFcbSVcXQ4ji7H8fBOZkF30BrXvIaP1/DzGgFeI8hrhHiNMK8R4TWivEaM14jzGje8hhHHPceRVMaR4jjSHEdGGUeW48hxHHllHAWOo8hxlJRxlDmOCsdRVcZR4zjqHEdDGUeT42hxHG1lHB2Oo8txPFAcC7qD1rjmNXy8hp/XCPAaQV4jxGuEeY0IrxHlNWK8RpzXuOE1fsbx9R4kV9jq1xRZ+5om618zZEOXldrU5aS2dHmpbVPBa8dU9No1lbz2bGXBvq0iOLBVBYcuNacjl7rTsUvD6UTUtJyKWpYzUdtyLtExXEh0DZcSD4Z3co+ahdzx9UWm50N9Pwt8HZDg1yEJfR2RsG4sFdFNpKK6qVTMNPOKm+ZeN6ZXr1vbm4DiSCrjSHEcaY4jo4wjy3HkOI68Mo4Cx1HkOErKOMocR4XjqCrjqHEcdY6joYyjyXG0OI62Mo4Ox9HlOB6UcTwa3v+iO3ocR18Zx4DjGHIcI2UcY45jwnFMlXHMOI45x/GqjONNFse3e4+kYUUupVmVS2vW5DKadZTdQLlNlN9i298KZOdbkex+K5E9XVlqX1eROtBVpQ5NNa8jU93r2NTwOrE1Bae2luDM1hacu3ScLly6TpcuD07vRI+W9z/993F8e3HoGXwSfYNfbqAJyA01QbmRJoTGYTSJoGmUxb7NSPzbnNx8eyW3ujepJVpjmddY4TVWeQ2OI8tx5DiOvDKOAsdR5DhKyjjKHEeF46gq46hxHHWOo6GMo8lxtDiOtjKODsfR5TgelHE8/oI4HHf0OI6+Mo4BxzHkOEbKOMYcx4TjmCrjmHEcc47jVRnH27+MI6mMI8VxpDmOjDKOLMeR4zjyyjgKHEeR4ygp4yhzHBWOo6qMo8Zx1DmOhjKOJsfR4jjayjg6HEeX43hQxvEojWNhd/Q4jr4yjgHHMeQ4Rso4xhzHhOOYKuOYcRxzjuNVGccbx/Fjafn7/f8kBSsuKadVl7TTmkvGaV2UtWyIcpZNUd6yJVEwbEsUDTsSJcOuXFmzJ1fR7MtVNQeodojqR6hxzE6+N8np9xY5+94m57qO1IWuK3Wpe5B6Z3r0em960izkju89i8/WF/hdBk4Bl6FT0GXkFBKNLWHRxBIRTS1RiZkhJjE3xCVeDTdyb5pbuR+aJVpjmddY4TVWeY01XmOd19jgNTZ5jS1eY5vX2OE1dnmNPV6D46hxHHWOo6GMo8lxtDiOtjKODsfR5TgelHE8chxPloXeQWv4eA0/rxHgNYK8RojXCPMaEV4jymvEeI04r3HDa/yM4+5++S4ptWJKea2a0l5rpozXui0r2LDlBJu2vGDLpeC07VJ02nEpOe2KypY9UcWyL6paDiRqhkOJuuFIomE4lmtqTuRamlO5tuYMdc5R9wI9XLJ3d4/k/d2TYCF33PU0Pl1fym8aeAVMQ6+gaeQVso0FYdtEELFNBVGXmVPMZe4Ud3l1uhG9WW5FPyxLtMYyr7HCa6zyGmu8xjqvscFrbPIaW7zGNq+xw2vs8hp7vMY+r3HAaxzyGke8xjGvccJrcBwdjqPLcTwo43jkOJ7eyyzoDlrDx2v4eY0ArxHkNUK8RpjXiPAaUV4jxmvEeY0bXuP/jSPFcaQ5jowyjizHkeM48so4ChxHkeMoKeMocxwVjqOqjKPGcdQ5joYyjibH0eI42so4OhxHl+N4UMbxyHE8URzv754XcYcyjgHHMeQ4Rso4xhzHhOOYKuOYcRxzjuNVGccbx/HDE0ciCVIrKL2KMmtsPZElG4kc2UzkyZauILWtK0rt6EpSu6ay156p4rVvqnod2GqCQ1tdcGRrCI5dmk4nLi2nU5e205moYzkXdS0XogfLpcSj4Z3Ek+G9xLNhIXck+jIDPxoG0CjIQokxCScmJJKYkqhuJhXTzaXiulepG9Ob163phxfFkeI40hxHRhlHluPIcRx5ZRwFjqPIcZSUcZQ5jgrHUVXGUeM46hxHQxlHk+NocRxtZRwdjqPLcTwo43jkOJ44jmfLh190x4DjGHIcI2UcY45jwnFMlXHMOI45x/GqjOON4/gh9X9OZH1ohLPmBwAAAABJRU5ErkJggg=="
)


@app.get("/api/v4/files/<fid>")
def get_file(fid):
    if not auth_user():
        return err(401, "Not authenticated")
    if fid == "file-mock-png":
        return Response(PNG_DEMO, mimetype="image/png")
    if fid == "file-mock-pdf":
        return Response(b"%PDF-1.4 mock", mimetype="application/pdf")
    return err(404, "File not found")


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


@app.post("/mock/flags")
def mock_flags():
    """Test helper: set EnableAPIUserDeletion / EnableAPITeamDeletion."""
    data = request.get_json(silent=True) or {}
    for key in ("EnableAPIUserDeletion", "EnableAPITeamDeletion"):
        if key in data:
            SERVER_FLAGS[key] = bool(data[key])
    return jsonify({"ok": True, "flags": SERVER_FLAGS})


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
        SERVER_FLAGS.clear(); SERVER_FLAGS.update(copy.deepcopy(_INITIAL_STATE["flags"]))
    return jsonify({"ok": True})


_snapshot()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8065, debug=False, threaded=True)
