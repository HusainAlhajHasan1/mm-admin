Developer test helpers
======================

These files are only for testing the dashboard without a real Mattermost
server. They are harmless in production but can be deleted.

  mock_mm.py      Minimal fake of the Mattermost REST API v4.
                  Login: admin / admin123  (System Admin)
                         john  / johnpass1  (regular member - dashboard rejects this)

  test_smoke.py   End-to-end API test (44 checks). Run against a running
                  mock + dashboard pair:
                     python3 tests/mock_mm.py
                     MM_URL=http://127.0.0.1:8065 DASH_PORT=8090 \
                        DB_PATH=/tmp/mm-test.db python3 app.py
                     python3 tests/test_smoke.py

  seed_demo.py    Fills the local SQLite with representative presence and
                  location history so the UI can be reviewed.

  test_delete_truth.py
                  Checks that "delete user/team" reports the real outcome when the
                  server has EnableAPIUserDeletion / EnableAPITeamDeletion off
                  (Mattermost then only deactivates but still answers 200).

  test_deleted_messages.py
                  Verifies that database-mode chat reading returns deleted
                  posts (text, deletion time, counts) by running the real
                  SQL from app.py against a Mattermost-shaped SQLite fixture.
                  Needs no server:  python3 tests/test_deleted_messages.py
