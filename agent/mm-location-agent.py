#!/usr/bin/env python3
"""
Mattermost Admin Dashboard — Location Agent
===========================================
A small, dependency-free agent that runs on a user's computer and reports its
public IP address to the admin dashboard (which turns it into an approximate,
city-level location).

It does NOT read messages, files, keystrokes or screenshots. It only sends:
    username, public IP, hostname, operating system and a timestamp.

Usage
-----
    python3 mm-location-agent.py --url http://192.168.1.50:8090 \
        --key YOUR_API_KEY --username jdoe --interval 300

Environment variables are also supported:
    DASH_URL, API_KEY, USERNAME, INTERVAL

Options:
    --once          send a single ping and exit (useful for cron)
    --lat/--lon     optional GPS coordinates to report instead of city lookup
    --insecure      allow self-signed HTTPS certificates
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# These defaults are filled in automatically when the script is downloaded
# from the dashboard (Settings -> Location agent).
DASH_URL_DEFAULT = ""
API_KEY_DEFAULT = ""
USERNAME_DEFAULT = ""
APP_VERSION = "APP_VERSION_PLACEHOLDER"
if "PLACEHOLDER" in APP_VERSION:  # running straight from the source tree
    APP_VERSION = "1.0.0"
INTERVAL_DEFAULT = 300


def log(message: str) -> None:
    print("[{}] {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message), flush=True)


def _ssl_context(insecure: bool):
    if not insecure:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def http_request(url: str, data=None, headers=None, timeout: int = 15, insecure: bool = False):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context(insecure)) as resp:
        return resp.read().decode("utf-8", "replace")


def detect_public_ip(timeout: int = 10) -> str:
    """Return the machine's public IPv4/IPv6 address, using a few fallbacks."""
    providers = [
        ("https://ipwho.is/", "json", "ip"),
        ("https://api.ipify.org?format=json", "json", "ip"),
        ("https://ifconfig.me/ip", "text", None),
        ("https://icanhazip.com", "text", None),
    ]
    for url, kind, key in providers:
        try:
            body = http_request(url, timeout=timeout).strip()
            if kind == "json":
                value = (json.loads(body) or {}).get(key) or ""
            else:
                value = body
            value = value.strip()
            if value and len(value) < 64:
                return value
        except Exception:
            continue
    return ""


def send_ping(args, public_ip: str) -> None:
    payload = {
        "username": args.username,
        "ip": public_ip,
        "source": "agent",
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
    }
    if args.lat is not None and args.lon is not None:
        payload["lat"] = args.lat
        payload["lon"] = args.lon
    body = json.dumps(payload).encode("utf-8")
    url = args.url.rstrip("/") + "/api/track/location"
    text = http_request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": args.key,
            "User-Agent": "mm-location-agent/" + APP_VERSION,
        },
        insecure=args.insecure,
    )
    try:
        data = json.loads(text)
    except ValueError:
        data = {}
    if data.get("ok"):
        uid = data.get("resolved_user_id")
        log("Ping sent for '{}' (public IP {}). Resolved user: {}.".format(
            args.username, public_ip or "unknown", uid or "not resolved"))
    else:
        log("Server response: " + text[:300])


def main() -> int:
    parser = argparse.ArgumentParser(description="Report this computer's public IP to the Mattermost Admin Dashboard.")
    parser.add_argument("--url", default=os.environ.get("DASH_URL", DASH_URL_DEFAULT),
                        help="Dashboard base URL, e.g. http://192.168.1.50:8090")
    parser.add_argument("--key", default=os.environ.get("API_KEY", API_KEY_DEFAULT),
                        help="Location API key from the dashboard settings")
    parser.add_argument("--username", default=os.environ.get("USERNAME", USERNAME_DEFAULT),
                        help="Mattermost username of the person using this computer")
    parser.add_argument("--interval", type=int, default=int(os.environ.get("INTERVAL", INTERVAL_DEFAULT)),
                        help="Seconds between pings (default 300)")
    parser.add_argument("--once", action="store_true", help="Send one ping and exit")
    parser.add_argument("--lat", type=float, default=None, help="Optional latitude (overrides IP geolocation)")
    parser.add_argument("--lon", type=float, default=None, help="Optional longitude (overrides IP geolocation)")
    parser.add_argument("--insecure", action="store_true", help="Do not verify HTTPS certificates")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args()

    if args.version:
        print("mm-location-agent " + APP_VERSION)
        return 0
    if not args.url:
        parser.error("--url is required (or set DASH_URL)")
    if not args.key:
        parser.error("--key is required (or set API_KEY)")
    if not args.username:
        parser.error("--username is required (or set USERNAME)")

    log("Mattermost location agent {} started for '{}' -> {}".format(APP_VERSION, args.username, args.url))
    log("Interval: {}s. Agent does not read any message content.".format(args.interval))

    while True:
        public_ip = detect_public_ip()
        if not public_ip:
            log("Warning: could not detect a public IP address. The dashboard will fall back to this machine's "
                "LAN address (local network).")
        try:
            send_ping(args, public_ip)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            log("HTTP error {} from dashboard: {}".format(exc.code, detail))
        except urllib.error.URLError as exc:
            log("Cannot reach dashboard at {}: {}".format(args.url, exc.reason))
        except Exception as exc:
            log("Unexpected error: {}".format(exc))

        if args.once:
            return 0
        try:
            time.sleep(max(30, args.interval))
        except KeyboardInterrupt:
            log("Stopped by user.")
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
