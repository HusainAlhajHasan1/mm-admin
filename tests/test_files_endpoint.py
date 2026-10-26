#!/usr/bin/env python3
"""
Verifies the attachment endpoint (/api/files/<id>).

Checks that a real image is served byte-for-byte, that path traversal out of
the Mattermost data directory is refused, that missing files 404, and that an
anonymous request is rejected.

Run:  python3 tests/test_files_endpoint.py
"""

import base64
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name} {detail}".strip())
    print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeDB:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(
            "CREATE TABLE fileinfo (id TEXT, name TEXT, mimetype TEXT, path TEXT, size INTEGER)"
        )
        self.con.executemany(
            "INSERT INTO fileinfo VALUES (?,?,?,?,?)",
            [
                ("f-img", "pic.png", "image/png", "20261026/files/abc/pic.png", len(PNG)),
                ("f-trav", "evil.png", "image/png", "../../../etc/passwd", 10),
                ("f-miss", "gone.png", "image/png", "20261026/files/abc/nope.png", 10),
            ],
        )
        self.con.commit()

    def rows(self, sql, params=()):
        cur = self.con.cursor()
        cur.execute(sql.replace("%s", "?"), params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    data_dir = tempfile.mkdtemp(prefix="mmdata-")
    os.makedirs(os.path.join(data_dir, "20261026/files/abc"), exist_ok=True)
    with open(os.path.join(data_dir, "20261026/files/abc/pic.png"), "wb") as fh:
        fh.write(PNG)

    db = FakeDB()
    app.db_rows = lambda pg, my, params=(): db.rows(pg, params)
    app.MM_DATA_DIR = data_dir
    app.DATABASE_URL = "postgresql://test/test"

    try:
        check("media root detected", app.media_root() == data_dir, str(app.media_root()))
        check("safe path resolves", app.safe_media_path("20261026/files/abc/pic.png") is not None)
        check("traversal refused by helper",
              app.safe_media_path("../../../etc/passwd") is None)

        with app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["token"] = "dummy"
                sess["user_id"] = "u-admin"
                sess["user"] = {"id": "u-admin", "username": "admin", "roles": "system_admin"}
                sess["csrf"] = "t"

            resp = client.get("/api/files/f-img")
            check("image served", resp.status_code == 200, str(resp.status_code))
            check("image content type", resp.headers.get("Content-Type") == "image/png",
                  str(resp.headers.get("Content-Type")))
            check("image bytes are intact", resp.data == PNG,
                  f"{len(resp.data)} vs {len(PNG)}")

            trav = client.get("/api/files/f-trav")
            check("traversal request refused", trav.status_code == 404, str(trav.status_code))
            check("traversal leaks no file content",
                  b"root:" not in trav.data and b"/bin/" not in trav.data)

            miss = client.get("/api/files/f-miss")
            check("missing attachment 404", miss.status_code == 404, str(miss.status_code))

        with app.app.test_client() as anon:
            check("anonymous request rejected", anon.get("/api/files/f-img").status_code == 401)

        # attachments reach the chat payload
        post_files = app.shape_file({"id": "f-img", "name": "pic.png", "extension": "png",
                                     "mimetype": "image/png", "size": len(PNG)})
        check("image detected as image", post_files["is_image"] is True)
        check("size formatted source", post_files["size"] == len(PNG))
        pdf = app.shape_file({"id": "f-pdf", "name": "a.pdf", "extension": "pdf",
                              "mimetype": "application/pdf", "size": 5})
        check("pdf not treated as image", pdf["is_image"] is False)
        unknown = app.shape_file({"id": "f-x", "name": "b", "extension": "",
                                  "mimetype": "", "size": 0})
        check("unknown type falls back to file", unknown["is_image"] is False)
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)

    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED:")
        for f in FAIL:
            print("  -", f)
        return 1
    print(f"All {len(PASS)} attachment checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
