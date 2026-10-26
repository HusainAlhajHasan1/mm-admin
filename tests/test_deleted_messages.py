#!/usr/bin/env python3
"""
Verifies that database-mode chat reading returns DELETED messages.

Mattermost keeps soft-deleted posts in the `posts` table with `deleteat > 0`
and (for most delete paths) still contains the original `message`. This test
builds a small SQLite database with the same table/column layout Mattermost
uses on PostgreSQL and runs the *real* SQL strings from app.py against it, so
the query logic that powers the dashboard's chat viewer is exercised for real.

Run:  python3 tests/test_deleted_messages.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402

PASS, FAIL = [], []


def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"PASS {name}")
    else:
        FAIL.append(f"{name} {detail}".strip())
        print(f"FAIL {name} {detail}")


# --------------------------------------------------------------------------- #
# Build a Mattermost-shaped database (PostgreSQL column naming is lowercase)
# --------------------------------------------------------------------------- #
def build_db():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT, email TEXT,
                            deleteat INTEGER DEFAULT 0);
        CREATE TABLE channels (id TEXT PRIMARY KEY, name TEXT, type TEXT,
                               deleteat INTEGER DEFAULT 0, lastpostat INTEGER DEFAULT 0);
        CREATE TABLE channelmembers (channelid TEXT, userid TEXT);
        CREATE TABLE posts (id TEXT PRIMARY KEY, createat INTEGER, updateat INTEGER,
                            deleteat INTEGER DEFAULT 0, userid TEXT, channelid TEXT,
                            message TEXT, type TEXT, rootid TEXT, props TEXT DEFAULT '');
        CREATE TABLE fileinfo (id TEXT PRIMARY KEY, postid TEXT, name TEXT, extension TEXT,
                               size INTEGER, mimetype TEXT, width INTEGER, height INTEGER,
                               deleteat INTEGER DEFAULT 0, path TEXT, createat INTEGER DEFAULT 0);
        """
    )
    cur.executemany("INSERT INTO users (id, username, email) VALUES (?,?,?)", [
        ("u1", "user1", "user1@example.com"),
        ("u2", "user2", "user2@example.com"),
    ])
    # DM channel name is "<id1>__<id2>" with the ids sorted, exactly like Mattermost
    dm_name = "__".join(sorted(["u1", "u2"]))
    cur.execute("INSERT INTO channels (id,name,type,lastpostat) VALUES (?,?,?,?)",
                ("c-dm", dm_name, "D", 3000))
    cur.execute("INSERT INTO channelmembers VALUES (?,?)", ("c-dm", "u1"))
    cur.execute("INSERT INTO channelmembers VALUES (?,?)", ("c-dm", "u2"))

    # (id, create_at, delete_at, user, message, type)
    posts = [
        ("p1", 1000, 0, "u2", "Hi, are you there?", ""),
        ("p2", 1100, 1900, "u2", "Hello", ""),                    # deleted, text kept
        ("p3", 1200, 1901, "u1", "Call canceled", ""),            # deleted, text kept
        ("p4", 1300, 1950, "u1", "Meet me at 5", ""),             # deleted, text kept
        ("p5", 1400, 0, "u1", "Sent a photo", "custom_attachment"),
        ("p6", 1500, 1960, "u2", "", ""),                         # deleted, text blanked
        ("p7", 1600, 0, "u2", "Still here", ""),
        # plugin post: no message, text lives in props
        ("p8", 1700, 1970, "u2", "", "custom_calls"),
    ]
    for pid, created, deleted, user, msg, ptype in posts:
        props = '{"call":"Call ended"}' if pid == "p8" else ""
        cur.execute(
            "INSERT INTO posts (id,createat,updateat,deleteat,userid,channelid,message,type,"
            "rootid,props) VALUES (?,?,?,?,?,?,?,?,'',?)",
            (pid, created, created + 10, deleted, user, "c-dm", msg, ptype, props),
        )
    # Attachments: one image on a live post, one PDF on a deleted post
    cur.executemany(
        "INSERT INTO fileinfo (id,postid,name,extension,size,mimetype,width,height,deleteat,path)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("f-img", "p1", "screenshot.png", "png", 2048, "image/png", 800, 600, 0,
             "20261026/files/abc/screenshot.png"),
            ("f-pdf", "p4", "contract.pdf", "pdf", 90000, "application/pdf", 0, 0, 0,
             "20261026/files/def/contract.pdf"),
        ],
    )
    con.commit()
    return con


def install_sqlite_shim(con):
    """Make app.db_rows() run its PostgreSQL SQL against our SQLite fixture."""
    original = app.db_rows

    def fake_db_rows(sql_pg, sql_mysql, params=()):
        try:
            cur = con.cursor()
            cur.execute(sql_pg.replace("%s", "?"), params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as exc:  # pragma: no cover - surfaces SQL errors
            raise app.MMError(502, f"sqlite shim failed: {exc}")

    app.db_rows = fake_db_rows
    app.DATABASE_URL = "postgresql://test/test"   # force DB mode
    return original


def main():
    con = build_db()
    original = install_sqlite_shim(con)

    try:
        info = app.chat_backend_info()
        check("chat backend reports database mode", info["mode"] == "db", str(info))

        # ---------------- conversation history ----------------
        data = app.db_chat_posts("c-dm", page=0, per_page=60)
        posts = data["posts"]
        check("all posts returned, deleted included", len(posts) == 8, f"got {len(posts)}")
        check("deleted_total counts soft-deleted posts", data["deleted_total"] == 5,
              f"got {data.get('deleted_total')}")

        by_id = {p["id"]: p for p in posts}
        check("deleted post keeps its text", by_id["p2"]["message"] == "Hello",
              by_id["p2"]["message"])
        check("deleted post flagged as deleted", by_id["p2"]["deleted"] is True)
        check("deleted post carries deletion timestamp",
              by_id["p2"]["delete_at"] and by_id["p2"]["delete_at"] > 0,
              str(by_id["p2"].get("delete_at")))
        check("text_available is True when text survived",
              by_id["p2"]["text_available"] is True)
        check("blanked deleted post has no text_available",
              by_id["p6"]["deleted"] is True and by_id["p6"]["text_available"] is False)
        check("live post is not marked deleted", by_id["p1"]["deleted"] is False)
        check("system/plugin posts are recognised",
              by_id["p5"]["type"] == "custom_attachment")

        # ordering: oldest first
        ordered = [p["id"] for p in posts]
        check("messages ordered oldest to newest",
              ordered == ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"], str(ordered))
        check("image attachment attached to its post",
              len(by_id["p1"]["files"]) == 1 and by_id["p1"]["files"][0]["is_image"] is True,
              str(by_id["p1"].get("files")))
        check("attachment filename preserved",
              by_id["p1"]["files"][0]["name"] == "screenshot.png")
        check("non-image attachment flagged as file",
              by_id["p4"]["files"][0]["is_image"] is False,
              str(by_id["p4"].get("files")))
        check("deleted post keeps its attachment",
              len(by_id["p4"]["files"]) == 1)
        check("post without attachments returns empty list",
              by_id["p2"]["files"] == [])
        check("plugin post text recovered from props",
              by_id["p8"]["message"] == "Call ended", repr(by_id["p8"]["message"]))
        check("props text flagged as from_props", by_id["p8"]["from_props"] is True)

        # ---------------- partner list ----------------
        partners = app.db_chat_partners("u1")
        check("conversation is listed", len(partners) == 1, f"got {len(partners)}")
        partner = partners[0]
        check("partner id resolved from channel name", partner["partner_id"] == "u2",
              partner.get("partner_id"))
        check("partner reports deleted message count",
              partner.get("deleted_count") == 5, str(partner.get("deleted_count")))
        check("preview uses the newest post even for deleted history",
              partner.get("preview") == "Call ended", repr(partner.get("preview")))

        # A conversation whose *only* message was deleted must still appear.
        con.execute("UPDATE posts SET deleteat = 2000 WHERE id = 'p7'")
        con.execute("UPDATE posts SET deleteat = 2001 WHERE id = 'p1'")
        con.commit()
        partners = app.db_chat_partners("u1")
        check("conversation with only deleted messages still listed",
              len(partners) == 1 and partners[0]["deleted_count"] == 7,
              str(partners and partners[0].get("deleted_count")))
        check("deleted-only preview is flagged", partners[0].get("preview_deleted") is True,
              str(partners[0].get("preview_deleted")))

        # ---------------- pagination keeps deleted posts ----------------
        page = app.db_chat_posts("c-dm", page=0, per_page=3)
        check("pagination returns a full page", len(page["posts"]) == 3, str(len(page["posts"])))
        check("pagination reports more pages", page["has_more"] is True)
        check("pagination total includes deleted", page["total"] == 8, str(page["total"]))
    finally:
        app.db_rows = original
        con.close()

    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED:")
        for f in FAIL:
            print("  -", f)
        return 1
    print(f"All {len(PASS)} deleted-message checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
