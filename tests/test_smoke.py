#!/usr/bin/env python3
"""
End-to-end smoke test for the Mattermost Admin Dashboard.

Requirements:
  1. python3 tests/mock_mm.py            (fresh mock on 127.0.0.1:8065)
  2. MM_URL=http://127.0.0.1:8065 DASH_PORT=8090 \
     DB_PATH=/tmp/mm-test.db python3 app.py
  3. python3 tests/test_smoke.py

The test creates and deletes a team and a user in the mock, so restart the
mock between runs (or accept the duplicate-name failures).
"""
import sys
import time

import requests

BASE = "http://127.0.0.1:8090"
FAILS = []


def check(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label + (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAILS.append(label)


def main():
    s = requests.Session()

    r = s.get(BASE + "/")
    check("login page renders", r.status_code == 200 and "Administrator sign-in" in r.text)

    r = s.post(BASE + "/api/login", json={"login_id": "admin", "password": "wrong"})
    check("wrong password rejected (401)", r.status_code == 401, r.text[:120])

    r = s.post(BASE + "/api/login", json={"login_id": "john", "password": "johnpass1"})
    check("non-admin rejected (403)", r.status_code == 403, r.text[:120])

    r = s.post(BASE + "/api/login", json={"login_id": "admin", "password": "admin123"})
    check("admin login (200)", r.status_code == 200, r.text[:200])
    csrf = (r.json() or {}).get("csrf") or ""
    check("csrf token issued", len(csrf) > 10)
    H = {"X-CSRF-Token": csrf}

    check("session endpoint", s.get(BASE + "/api/session").status_code == 200)

    r = s.get(BASE + "/api/users")
    check("users list", r.status_code == 200)
    data = r.json() or {}
    users = {u["username"]: u for u in data.get("users", [])}
    check("users include admin/john/mary/ali/sara", set(users) >= {"admin", "john", "mary", "ali", "sara"})
    check("team membership loaded", any(len(t.get("member_ids", [])) > 0 for t in data.get("teams", [])))

    r = s.get(BASE + "/api/overview")
    check("overview", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        ov = r.json()
        check("overview counts", ov.get("counts", {}).get("active_users") == 4, ov.get("counts"))

    check("presence", s.get(BASE + "/api/presence").status_code == 200)
    check("latest locations", s.get(BASE + "/api/locations/latest").status_code == 200)
    check("audit log", s.get(BASE + "/api/audit").status_code == 200)
    r = s.get(BASE + "/api/settings")
    check("settings", r.status_code == 200)
    settings = (r.json() or {}).get("settings", {})

    r = s.post(BASE + "/api/teams", json={"name": "no-csrf", "display_name": "No"})
    check("CSRF enforced", r.status_code == 403)

    r = s.post(BASE + "/api/teams", headers=H,
               json={"name": "qa", "display_name": "QA Team", "type": "O",
                     "member_ids": [users["john"]["id"]]})
    check("create team", r.status_code == 201, r.text[:200])
    qa = (r.json() or {}).get("team") or {}
    check("team created with 1 member", (r.json() or {}).get("members_added") == 1)

    check("duplicate team rejected", s.post(BASE + "/api/teams", headers=H,
                                            json={"name": "qa", "display_name": "QA"}).status_code == 400)

    r = s.post(BASE + "/api/users", headers=H,
               json={"username": "bob", "email": "bob@example.com",
                     "password": "bobpass12", "team": "ghost-team"})
    check("missing team -> TEAM_NOT_FOUND", r.status_code == 404 and (r.json() or {}).get("code") == "TEAM_NOT_FOUND")

    r = s.post(BASE + "/api/users", headers=H,
               json={"username": "bob", "email": "bob@example.com", "password": "bobpass12",
                     "first_name": "Bob", "last_name": "Brown", "team": "core"})
    check("create user in existing team", r.status_code == 201, r.text[:200])
    bob = (r.json() or {}).get("user") or {}

    r = s.get(BASE + "/api/users?refresh=1")
    data = r.json()
    users = {u["username"]: u for u in data.get("users", [])}
    core = next(t for t in data["teams"] if t["name"] == "core")
    design = next(t for t in data["teams"] if t["name"] == "design")
    check("created user is in core", users["bob"]["team_ids"] == [core["id"]], users["bob"]["team_ids"])

    check("add user to another team",
          s.post(BASE + f"/api/teams/{design['id']}/members", headers=H,
                 json={"user_id": bob["id"]}).status_code == 200)
    check("remove user from team",
          s.delete(BASE + f"/api/teams/{core['id']}/members/{bob['id']}", headers=H).status_code == 200)

    r = s.get(BASE + f"/api/chat/partners/{users['john']['id']}")
    check("chat partners", r.status_code == 200, r.text[:200])
    partners = (r.json() or {}).get("partners", []) if r.status_code == 200 else []
    check("john has 2 conversation partners", len(partners) == 2, [(p.get("partner") or {}).get("username") for p in partners])
    if partners:
        channel = partners[0]["channel_id"]
        r = s.get(BASE + f"/api/chat/{channel}/posts?page=0&per_page=60")
        check("conversation messages", r.status_code == 200 and len((r.json() or {}).get("posts", [])) > 0)
        check("conversation participants resolved", bool((r.json() or {}).get("participants")))
        check("message pagination", s.get(BASE + f"/api/chat/{channel}/posts?page=1&per_page=5").status_code == 200)

    check("user detail", s.get(BASE + f"/api/users/{users['john']['id']}/detail").status_code == 200)

    key = settings.get("location_api_key")
    r = requests.post(BASE + "/api/track/location", headers={"X-API-Key": key},
                      json={"username": "john", "ip": "8.8.8.8", "hostname": "laptop", "source": "agent"})
    check("agent location ping", r.status_code == 200, r.text[:200])
    time.sleep(0.3)
    r = s.get(BASE + "/api/locations/latest")
    names = [l.get("username") for l in (r.json() or {}).get("locations", [])]
    check("location visible in latest", "john" in names, names)
    check("agent ping with bad key rejected", requests.post(
        BASE + "/api/track/location", headers={"X-API-Key": "bad"},
        json={"username": "john"}).status_code == 401)

    check("presence refresh", s.post(BASE + "/api/presence/refresh", headers=H).status_code == 200)
    time.sleep(1.2)  # let a measurable interval accumulate
    r = s.get(BASE + "/api/presence?hours=24")
    check("presence intervals recorded", any(u.get("intervals") for u in (r.json() or {}).get("users", [])))
    check("status history", s.get(BASE + f"/api/status/history/{users['john']['id']}").status_code == 200)

    r = s.post(BASE + "/api/locations/sync-audits", headers=H)
    check("audit import degrades gracefully", r.status_code == 200 and "message" in (r.json() or {}))

    r = s.get(BASE + "/download/agent.py")
    check("agent download personalised",
          r.status_code == 200 and "http://127.0.0.1:8090" in r.text and key in r.text
          and "APP_VERSION_PLACEHOLDER" not in r.text)

    check("password reset", s.put(BASE + f"/api/users/{bob['id']}/password", headers=H,
                                  json={"password": "newpass123"}).status_code == 200)
    r = s.delete(BASE + f"/api/users/{bob['id']}?permanent=1", headers=H)
    # Server has EnableAPIUserDeletion=false, so it only deactivates; the API must
    # say so instead of claiming a real deletion.
    body = r.json() if r.content else {}
    check("permanent delete reports the real outcome",
          r.status_code == 200 and body.get("result") == "deactivated" and body.get("warning"),
          str(body)[:160])
    check("deactivate user", s.delete(BASE + f"/api/users/{bob['id']}", headers=H).status_code == 200)
    check("delete team", s.delete(BASE + f"/api/teams/{qa['id']}", headers=H).status_code == 200)

    check("logout", s.post(BASE + "/api/logout", headers=H).status_code == 200)
    check("session cleared", s.get(BASE + "/api/session").status_code == 401)

    print()
    if FAILS:
        print("FAILED:", len(FAILS), "->", ", ".join(FAILS))
        return 1
    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
