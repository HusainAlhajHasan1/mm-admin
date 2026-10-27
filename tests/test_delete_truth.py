#!/usr/bin/env python3
"""
Verifies that user/team deletion reports the REAL outcome.

A Mattermost server with ServiceSettings.EnableAPIUserDeletion disabled answers
200 to `DELETE /users/{id}?permanent=true` but only *deactivates* the account.
The dashboard must notice that and say "deactivated", not "deleted".

Runs against the mock API which reproduces both server configurations.
Prerequisites: mock on :8065 and the dashboard on :8090.

Run:  python3 tests/test_delete_truth.py
"""

import requests

BASE = "http://127.0.0.1:8090"
MOCK = "http://127.0.0.1:8065"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name} {detail}".strip())
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


def main():
    s = requests.Session()
    r = s.post(BASE + "/api/login", json={"login_id": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    csrf = r.json()["csrf"]
    H = {"X-CSRF-Token": csrf}

    # ---------------------------------------------------------------- flags OFF
    requests.post(MOCK + "/mock/reset")
    requests.post(MOCK + "/mock/flags", json={"EnableAPIUserDeletion": False,
                                              "EnableAPITeamDeletion": False})
    users = {u["username"]: u for u in s.get(BASE + "/api/users").json()["users"]}
    uid = users["john"]["id"]

    r = s.delete(BASE + f"/api/users/{uid}", params={"permanent": "1"}, headers=H)
    body = r.json() if r.content else {}
    check("permanent delete returns 200 (deactivated)", r.status_code == 200, str(r.status_code))
    check("result is 'deactivated', not 'deleted'", body.get("result") == "deactivated",
          str(body.get("result")))
    check("warning explains why", bool(body.get("warning")), str(body)[:200])

    fresh = {u["username"]: u for u in s.get(BASE + "/api/users").json()["users"]}
    check("user still exists on the server", "john" in fresh)
    check("user is marked deactivated", fresh.get("john", {}).get("active") is False,
          str(fresh.get("john", {}).get("active")))

    # team, same story
    teams = {t["name"]: t for t in s.get(BASE + "/api/teams").json()["teams"]}
    tid = teams["design"]["id"]
    r = s.delete(BASE + f"/api/teams/{tid}", params={"permanent": "1"}, headers=H)
    tb = r.json() if r.content else {}
    check("team permanent delete reports 'archived'", tb.get("result") == "archived",
          str(tb.get("result")))
    check("team warning present", bool(tb.get("warning")))

    # ---------------------------------------------------------------- flags ON
    requests.post(MOCK + "/mock/reset")
    requests.post(MOCK + "/mock/flags", json={"EnableAPIUserDeletion": True,
                                              "EnableAPITeamDeletion": True})
    users = {u["username"]: u for u in s.get(BASE + "/api/users").json()["users"]}
    uid = users["mary"]["id"]

    r = s.delete(BASE + f"/api/users/{uid}", params={"permanent": "1"}, headers=H)
    body = r.json() if r.content else {}
    check("real delete returns 200", r.status_code == 200, str(r.status_code))
    check("result is 'deleted'", body.get("result") == "deleted", str(body.get("result")))
    check("no warning on real delete", not body.get("warning"), str(body.get("warning")))

    fresh = {u["username"]: u for u in s.get(BASE + "/api/users").json()["users"]}
    check("user is gone from the server", "mary" not in fresh, str(list(fresh)))

    teams = {t["name"]: t for t in s.get(BASE + "/api/teams").json()["teams"]}
    tid = teams["core"]["id"]
    r = s.delete(BASE + f"/api/teams/{tid}", params={"permanent": "1"}, headers=H)
    tb = r.json() if r.content else {}
    check("team really deleted", tb.get("result") == "deleted", str(tb.get("result")))

    # ---------------------------------------------------------------- soft delete
    requests.post(MOCK + "/mock/reset")
    users = {u["username"]: u for u in s.get(BASE + "/api/users").json()["users"]}
    uid = users["ali"]["id"]
    r = s.delete(BASE + f"/api/users/{uid}", headers=H)
    body = r.json() if r.content else {}
    check("deactivate reports 'deactivated'", body.get("result") == "deactivated",
          str(body.get("result")))
    fresh = {u["username"]: u for u in s.get(BASE + "/api/users").json()["users"]}
    check("deactivated user still listed", "ali" in fresh)
    check("deactivated user inactive", fresh.get("ali", {}).get("active") is False)

    requests.post(MOCK + "/mock/reset")

    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED:")
        for f in FAIL:
            print("  -", f)
        return 1
    print(f"All {len(PASS)} delete-truth checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
