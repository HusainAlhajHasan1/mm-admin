#!/usr/bin/env python3
"""
Show exactly what the dashboard reads from the Mattermost database for one DM.

Usage (on the Mattermost LXC, as root):

    /opt/mm-admin/venv/bin/python /opt/mm-admin/tools/debug_chat.py user1 user2

It prints, for every post in that conversation:
    create_at | delete_at | type | length(message) | message preview | props keys

If `len(message)` is 0 for a deleted post, the server no longer stores that
text and nothing can recover it. If it is > 0, the dashboard will show it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402


def ms_to_str(ms):
    if not ms:
        return "-"
    return app.local_str(ms // 1000)


def find_user(username):
    rows = app.db_rows(
        "SELECT id, username FROM users WHERE username = %s",
        "SELECT Id AS id, Username AS username FROM Users WHERE Username = %s",
        (username,),
    )
    return rows[0] if rows else None


def find_dm(user_a, user_b):
    name = "__".join(sorted([user_a, user_b]))
    rows = app.db_rows(
        "SELECT id, name FROM channels WHERE type = 'D' AND name = %s",
        "SELECT Id AS id, Name AS name FROM Channels WHERE Type = 'D' AND Name = %s",
        (name,),
    )
    return rows[0] if rows else None


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2

    info = app.chat_backend_info(test=True)
    print(f"chat mode    : {info['mode']}")
    print(f"database     : {info.get('dialect')}  ok={info.get('db_ok')}")
    if info.get("error"):
        print(f"db error     : {info['error']}")
        return 1
    if info["mode"] != "db" or not info.get("db_ok"):
        print("!! DATABASE_URL is not configured or unreachable - fix .env first.")
        return 1

    ua = find_user(argv[1])
    ub = find_user(argv[2])
    if not ua or not ub:
        print(f"!! user not found: {argv[1] if not ua else argv[2]}")
        return 1

    ch = find_dm(ua["id"], ub["id"])
    if not ch:
        print(f"!! no DM channel between {argv[1]} and {argv[2]}")
        return 1

    print(f"channel      : {ch['id']}  ({ch['name']})")
    print()

    data = app.db_chat_posts(ch["id"], page=0, per_page=500)
    print(f"posts found  : {data['total']}   deleted: {data['deleted_total']}")
    print()
    header = f"{'sent':<20} {'deleted':<20} {'type':<18} {'len':>4}  message"
    print(header)
    print("-" * len(header))
    empty_deleted = 0
    for p in data["posts"]:
        msg = p["message"] or ""
        if p["deleted"] and not msg:
            empty_deleted += 1
        preview = msg.replace("\n", " ")[:60]
        ptype = (p.get("type") or "")[:17]
        print(f"{ms_to_str((p['create_at'] or 0) * 1000):<20} "
              f"{ms_to_str((p['delete_at'] or 0) * 1000) if p['deleted'] else '-':<20} "
              f"{ptype:<18} {len(msg):>4}  {preview}")

    print()
    if empty_deleted:
        print(f"NOTE: {empty_deleted} deleted post(s) have an EMPTY message column.")
        print("      Mattermost has no text for them, so the dashboard can only say")
        print("      'This message was deleted.' Check the props column below:")
        for p in data["posts"]:
            if p["deleted"] and not p["message"] and p.get("props"):
                print(f"      - {p['id']}: props={p['props']}")
    else:
        print("OK: every deleted post still has text - the dashboard will show it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
