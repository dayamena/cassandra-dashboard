"""
digest.py -- Builds a "what's new since last digest" summary from the
SQLite DB and sends it to Slack (via incoming webhook) and/or email
(via SMTP). Intended to run daily/weekly via cron, after the scrapers.

Config is via environment variables so no secrets live in this file:
  SLACK_WEBHOOK_URL   -- Slack incoming webhook URL (optional)
  DIGEST_SMTP_HOST    -- e.g. smtp.gmail.com (optional, for email)
  DIGEST_SMTP_PORT    -- e.g. 587
  DIGEST_SMTP_USER    -- SMTP login
  DIGEST_SMTP_PASS    -- SMTP password / app password
  DIGEST_EMAIL_TO     -- comma-separated recipient list
  DIGEST_EMAIL_FROM   -- from address (defaults to DIGEST_SMTP_USER)

If a given set of variables isn't set, that channel is just skipped
(so you can run with only Slack, only email, or both).
"""

import os
import smtplib
import sys
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).parent.parent))
from db import get_conn

LOOKBACK_HOURS = int(os.environ.get("DIGEST_LOOKBACK_HOURS", "24"))


def since_cutoff():
    return (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).isoformat()


def gather_new_items():
    cutoff = since_cutoff()
    with get_conn() as conn:
        new_press = conn.execute(
            "SELECT title, url, source FROM press_releases WHERE first_seen >= ? ORDER BY first_seen DESC",
            (cutoff,),
        ).fetchall()

        new_dockets = conn.execute(
            "SELECT case_number, court, title, docket_url FROM court_dockets WHERE first_seen >= ? ORDER BY first_seen DESC",
            (cutoff,),
        ).fetchall()

        pop_changes = conn.execute(
            """
            SELECT facility_name, state, report_date, population
            FROM facility_stats
            WHERE scraped_at >= ?
            ORDER BY population DESC
            LIMIT 10
            """,
            (cutoff,),
        ).fetchall()

        run_log = conn.execute(
            "SELECT scraper_name, status, rows_added, error_message FROM scrape_runs WHERE started_at >= ? ORDER BY id DESC",
            (cutoff,),
        ).fetchall()

    return {
        "press": [dict(r) for r in new_press],
        "dockets": [dict(r) for r in new_dockets],
        "facilities": [dict(r) for r in pop_changes],
        "runs": [dict(r) for r in run_log],
    }


def build_text_summary(data):
    lines = [f"Cassandra digest — last {LOOKBACK_HOURS}h", "=" * 40, ""]

    lines.append(f"New press releases / disclosures: {len(data['press'])}")
    for p in data["press"][:10]:
        lines.append(f"  - [{p['source']}] {p['title']} -- {p['url']}")

    lines.append("")
    lines.append(f"New court dockets: {len(data['dockets'])}")
    for d in data["dockets"][:10]:
        lines.append(f"  - {d['case_number']} ({d['court']}): {d['title']} -- {d['docket_url']}")

    lines.append("")
    lines.append("Top facility populations (from this run's scrape):")
    for f in data["facilities"][:10]:
        lines.append(f"  - {f['facility_name']} ({f['state']}): {f['population']} as of {f['report_date']}")

    lines.append("")
    lines.append("Scraper run log:")
    for r in data["runs"]:
        status_note = f" -- {r['error_message']}" if r["error_message"] else ""
        lines.append(f"  - {r['scraper_name']}: {r['status']}, {r['rows_added']} rows{status_note}")

    if not data["press"] and not data["dockets"] and not data["facilities"]:
        lines.append("\n(No new items in this window.)")

    return "\n".join(lines)


def send_slack(text: str):
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("[digest] SLACK_WEBHOOK_URL not set, skipping Slack")
        return
    resp = requests.post(webhook, json={"text": f"```{text}```"}, timeout=15)
    resp.raise_for_status()
    print("[digest] posted to Slack")


def send_email(text: str):
    host = os.environ.get("DIGEST_SMTP_HOST")
    to_addrs = os.environ.get("DIGEST_EMAIL_TO")
    if not host or not to_addrs:
        print("[digest] SMTP not configured, skipping email")
        return

    port = int(os.environ.get("DIGEST_SMTP_PORT", "587"))
    user = os.environ.get("DIGEST_SMTP_USER")
    pw = os.environ.get("DIGEST_SMTP_PASS")
    from_addr = os.environ.get("DIGEST_EMAIL_FROM", user)

    msg = MIMEText(text)
    msg["Subject"] = f"Cassandra digest — {datetime.now().strftime('%Y-%m-%d')}"
    msg["From"] = from_addr
    msg["To"] = to_addrs

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if user and pw:
            server.login(user, pw)
        server.sendmail(from_addr, to_addrs.split(","), msg.as_string())

    print("[digest] sent email")


def run():
    data = gather_new_items()
    text = build_text_summary(data)
    print(text)
    send_slack(text)
    send_email(text)


if __name__ == "__main__":
    run()
