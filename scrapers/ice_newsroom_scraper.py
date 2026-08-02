"""
ice_newsroom_scraper.py -- Pull publicly published press releases from
ICE's own newsroom (ice.gov/newsroom). These are public communications
ICE itself chooses to publish -- no scraping of internal/authenticated
systems, no circumvention of any access control.

Useful for: tracking official statements, enforcement statistics ICE
chooses to disclose, policy announcements, etc. for reporting/research
purposes.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).parent.parent))
from db import get_conn

NEWSROOM_URL = "https://www.ice.gov/newsroom"
USER_AGENT = "cassandra-research-bot/0.1 (public data aggregation; contact: set-your-email-here)"


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_releases(html: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    out = []

    # ICE's newsroom listing typically uses article/list items with a
    # linked headline and a date. This selector is intentionally loose
    # and defensive -- adjust the CSS selector below if ICE changes markup.
    for item in soup.select("article, .views-row, li.release"):
        link = item.find("a")
        if not link or not link.get("href"):
            continue

        title = link.get_text(strip=True)
        href = link["href"]
        url = href if href.startswith("http") else f"https://www.ice.gov{href}"

        date_tag = item.find("time")
        published_date = date_tag.get("datetime") if date_tag else None

        summary_tag = item.find("p")
        summary = summary_tag.get_text(strip=True) if summary_tag else None

        if title and url:
            out.append({
                "title": title,
                "url": url,
                "published_date": published_date,
                "summary": summary,
            })

    return out


def save_releases(releases):
    added = 0
    with get_conn() as conn:
        for r in releases:
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO press_releases
                        (title, published_date, url, summary, source, raw_json)
                    VALUES (?, ?, ?, ?, 'ICE_newsroom', ?)
                    """,
                    (r["title"], r["published_date"], r["url"], r["summary"], json.dumps(r)),
                )
                if cur.rowcount:
                    added += 1
            except Exception as e:
                print(f"  [warn] could not save release '{r.get('title')}': {e}")
    return added


def run():
    started = datetime.now(timezone.utc).isoformat()
    scraper_name = "ice_newsroom_scraper"

    try:
        html = fetch_page(NEWSROOM_URL)
        releases = parse_releases(html, NEWSROOM_URL)
        added = save_releases(releases)
        status, err = "ok", None
        print(f"[{scraper_name}] found {len(releases)} releases, {added} new")
    except Exception as e:
        added, status, err = 0, "error", str(e)
        print(f"[{scraper_name}] ERROR: {e}")

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO scrape_runs
               (scraper_name, started_at, finished_at, status, rows_added, error_message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (scraper_name, started, datetime.now(timezone.utc).isoformat(), status, added, err),
        )

    return status == "ok"


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
