# Put this project on GitHub, then download and run it

Two parts:

* **Part 1** — upload the project to your GitHub account.
* **Part 2** — download it on the Mattermost LXC and run it.

The project folder already has a `.gitignore` and a first commit, so secrets and
databases will **not** be uploaded.

---

## Part 1 — Upload to GitHub

### Step 1.1 — Create the empty repository

1. Open <https://github.com/new> in your browser.
2. Fill in:
   * **Repository name:** `mm-admin` (or any name you like)
   * **Visibility:** **Private** ← recommended, this is an admin tool
   * **Do NOT** tick "Add a README file", ".gitignore" or "license" — the project
     already has them.
3. Click **Create repository**.

GitHub now shows a page with commands. Ignore it for a moment and pick one of the
two methods below.

---

### Method A — Upload with the browser (easiest, no git needed)

1. On the new repository page click **uploading an existing file**
   (or go to `https://github.com/<your-user>/mm-admin/upload/main`).
2. Unzip `mm-admin-dashboard.zip` on your computer.
3. **Drag the contents of the `mm-admin` folder** (not the folder itself) into the
   browser window — `app.py`, `static/`, `templates/`, `install.sh`, etc.
4. In the message box write: `Mattermost Admin Dashboard v1.0.0`
5. Click **Commit changes**.

> The browser upload keeps folders such as `static/` and `templates/` correctly.

---

### Method B — Command line (recommended, keeps history)

On **your own computer** (not the LXC), in a folder where you unzipped the project:

```bash
cd mm-admin

git init -b main
git add .
git commit -m "Mattermost Admin Dashboard v1.0.0"

# replace YOUR-USER with your GitHub username
git remote add origin https://github.com/YOUR-USER/mm-admin.git
git push -u origin main
```

When git asks for a **password**, GitHub requires a **Personal Access Token**
instead of your normal password:

1. Go to <https://github.com/settings/tokens> → **Generate new token (classic)**
2. Note: `mm-admin upload` · Expiration: 30 days · Scope: tick **`repo`**
3. Click **Generate token** and copy it (`ghp_...`).
4. Paste it when git asks for the password. Username = your GitHub username.

*(Alternative: SSH key — <https://docs.github.com/authentication/connecting-to-github-with-ssh>)*

### Step 1.2 — Check the upload

Open your repository and confirm you can see:

```
app.py  install.sh  README.md  requirements.txt
static/  templates/  agent/  deploy/  docs/  tests/
```

**It must NOT contain** `.env`, `data/admin.db` or `data/secret_key`.
If you see those, delete them from the repo — they are meant to stay private.

---

## Part 2 — Download and run it on the Mattermost LXC

### Step 2.1 — Log into the LXC

From your Proxmox host:

```bash
pct list                       # find the Mattermost container ID
pct enter <ID>                 # or: ssh root@<LXC-IP>
```

### Step 2.2 — Get the code

**If the LXC has internet access:**

```bash
apt-get update && apt-get install -y git
git clone https://github.com/YOUR-USER/mm-admin.git /opt/src-mm-admin
cd /opt/src-mm-admin
```

For a **private** repository, git will ask for username + token (same token as
above). To avoid retyping, use:

```bash
git clone https://YOUR-USER:ghp_YOUR_TOKEN@github.com/YOUR-USER/mm-admin.git /opt/src-mm-admin
```

**If the LXC has no internet access** — download the ZIP on your computer and
copy it into the container:

```bash
# on your computer:
scp mm-admin-dashboard.zip root@<LXC-IP>:/root/

# inside the LXC:
apt-get update && apt-get install -y unzip python3 python3-venv python3-pip
cd /root && unzip -q mm-admin-dashboard.zip -d /opt/src-mm-admin-tmp
mv /opt/src-mm-admin-tmp/mm-admin /opt/src-mm-admin
```

### Step 2.3 — Run the installer

```bash
cd /opt/src-mm-admin
sudo bash install.sh
```

The installer asks for two things:

| Question | Answer |
|---|---|
| Mattermost server URL | `http://127.0.0.1:8065` (same container) |
| Dashboard port | `8090` (or any free port) |

It then creates a `mm-admin` service user, builds a virtual environment,
installs the Python packages, writes `/opt/mm-admin/.env`, registers the
`mm-admin` **systemd service**, opens the firewall port, and prints the URL.

### Step 2.4 — Open it

In your browser:

```
http://<MATTERMOST-LXC-IP>:8090
```

Sign in with a Mattermost **System Admin** account (the first user created in
Mattermost). A normal member gets "not a System Admin" and is sent back.

### Step 2.5 — Useful service commands

```bash
systemctl status mm-admin      # is it running?
systemctl restart mm-admin     # restart after changes
journalctl -u mm-admin -f      # live logs
```

The configuration lives in **`/opt/mm-admin/.env`** (permissions `600`).
Change the port, Mattermost URL, timezone or database there, then restart.

---

## Updating later

`install.sh` **copies** the program to `/opt/mm-admin` and runs it from there, so a
plain `git pull` is not enough — you must copy the new files again:

```bash
# inside the LXC
cd /opt/src-mm-admin
git pull
sudo bash install.sh        # safe to re-run: refreshes code, keeps .env and data
```

`install.sh` does not overwrite `/opt/mm-admin/.env` and never deletes
`/opt/mm-admin/data`, so your settings, presence history and audit log survive
the update. The service is restarted automatically at the end.

One-line version:

```bash
cd /opt/src-mm-admin && git pull && sudo bash install.sh
```

> If you edited files directly in `/opt/mm-admin` instead of the clone, back them
> up before updating — `install.sh` will replace them.

---

## Common problems

| Problem | Fix |
|---|---|
| `git: command not found` | `apt-get install -y git` |
| `install.sh: line 68: /opt/mm-admin/venv/bin/pip: No such file or directory` | The venv was built without pip (Debian/Ubuntu keeps `ensurepip` in a separate package). Run `apt-get install -y python3-venv python3$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')-venv python3-pip`, then `rm -rf /opt/mm-admin/venv`, then re-run `sudo bash install.sh`. |
| `Permission denied (publickey)` | Use the HTTPS URL + token, not SSH |
| `Authentication failed` on push | Use a Personal Access Token, not your password |
| `fatal: repository not found` | Check the username/repo spelling, and that you are logged into the right GitHub account |
| LXC cannot reach GitHub | Use the ZIP + `scp` method in Step 2.2 |
| Page does not open | `systemctl status mm-admin`; check firewall: `ufw allow 8090/tcp` |
| "Cannot connect to Mattermost" | Wrong `MM_URL` in `/opt/mm-admin/.env` → fix and `systemctl restart mm-admin` |
| Forgot the dashboard port | `grep DASH_PORT /opt/mm-admin/.env` |
| Permanent delete says "mmctl not installed" | mmctl lives at `/opt/mattermost/bin/mmctl`; make it executable and re-run `install.sh` so the sudoers rule is installed |
| After update the page still shows old code | `sudo systemctl restart mm-admin`, then hard-refresh the browser (`Ctrl+Shift+R`) |

---

## Security reminders

* Keep the repository **private** — the code alone is harmless, but it reveals
  your admin tooling.
* Never commit `.env` — it holds your Mattermost admin token and agent API key.
* Restrict port `8090` to your LAN/VPN: `ufw allow from 192.168.0.0/16 to any port 8090`.
* The dashboard never stores Mattermost passwords.
