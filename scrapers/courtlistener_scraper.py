"""
courtlistener_scraper.py -- Pull new immigration-related court filings
from CourtListener's free public API (courtlistener.com), which mirrors
public PACER filings via the RECAP project. This avoids per-page PACER
fees and any authentication -- CourtListener's REST API is open data.

Docs: https://www.courtlistener.com/help/api/rest/

Get a free API token at https://www.courtlistener.com/sign-in/ and set
it as the COURTLISTENER_TOKEN environment variable for higher rate
limits (the API works unauthenticated too, at a lower limit).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).parent.parent))
from db import get_conn

API_BASE = "https://www.courtlistener.com/api/rest/v4"
SEARCH_QUERY = "immigration detention ICE"  # adjust to narrow/broaden results
TOKEN = os.environ.get("COURTLISTENER_TOKEN", "")


def fetch_dockets(query: str, page_size: int = 20):
    headers = {"User-Agent": "cassandra-research-bot/0.1"}
    if TOKEN:
        headers["Authorization"] = f"Token {TOKEN}"

    params = {
        "q": query,
        "type": "r",          # 'r' = RECAP (docket) search
        "order_by": "dateFiled desc",
        "page_size": page_size,
    }
    resp = requests.get(f"{API_BASE}/search/", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def save_dockets(dockets):
    added = 0
    with get_conn() as conn:
        for d in dockets:
            case_number = d.get("docketNumber") or d.get("docket_id")
            if not case_number:
                continue
            try:
                cur = conn.execute(
                    """
                    INSERT INTO court_dockets
                        (case_number, court, filing_date, title, docket_url, source, raw_json, last_seen)
                    VALUES (?, ?, ?, ?, ?, 'CourtListener', ?, datetime('now'))
                    ON CONFLICT(case_number, source)
                    DO UPDATE SET last_seen=datetime('now')
                    """,
                    (
                        str(case_number),
                        d.get("court"),
                        d.get("dateFiled"),
                        d.get("caseName"),
                        f"https://www.courtlistener.com{d.get('absolute_url', '')}",
                        json.dumps(d),
                    ),
                )
                added += 1
            except Exception as e:
                print(f"  [warn] could not save docket {case_number}: {e}")
    return added


def run():
    started = datetime.now(timezone.utc).isoformat()
    scraper_name = "courtlistener_scraper"

    try:
        dockets = fetch_dockets(SEARCH_QUERY)
        added = save_dockets(dockets)
        status, err = "ok", None
        print(f"[{scraper_name}] fetched {len(dockets)} dockets, saved/updated {added}")
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
