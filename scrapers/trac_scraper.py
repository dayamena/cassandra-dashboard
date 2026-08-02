"""
trac_scraper.py -- Pull publicly published detention statistics from
TRAC Immigration (Transactional Records Access Clearinghouse, Syracuse
University). TRAC publishes detention population data derived from
FOIA'd ICE records, at a public JSON endpoint -- not gated behind auth,
just the raw data backing their interactive facilities table.

Endpoint: https://tracreports.org/immigration/detentionstats/facilities.json

Each record looks like:
  {
    "name": "ADAMS COUNTY CORRECTIONAL CENTER",
    "detention_facility_city": "NATCHEZ",
    "detention_facility_state": "MS",
    "detention_facility_zip": "39120",
    "type_detailed": "DIGSA",
    "count": "               1,878",   -- note: padded string, needs cleanup
    "guaranteed_min_num": 1436,
    "download_date": "07/09/2026",   -- MM/DD/YYYY
    "order": 1
  }

The feed includes multiple historical snapshots concatenated together
(distinguished by download_date), plus a "Total" pseudo-row per
snapshot (order=0) which we skip -- it's an aggregate, not a facility.

NOTE: Respect TRAC's terms of use and robots.txt. This scraper is
intended to run at most once every 24h (see the systemd timer in
scripts/), which is far below any reasonable rate limit.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

sys.path.append(str(Path(__file__).parent.parent))
from db import get_conn

TRAC_JSON_URL = "https://tracreports.org/immigration/detentionstats/facilities.json"
USER_AGENT = "cassandra-research-bot/0.1 (public data aggregation; contact: set-your-email-here)"


def fetch_json(url: str):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_count(raw_count) -> Optional[int]:
    """TRAC's 'count' field is a padded string like '               1,878'."""
    if raw_count is None:
        return None
    try:
        return int(str(raw_count).replace(",", "").strip())
    except ValueError:
        return None


def parse_download_date(raw_date: str) -> Optional[str]:
    """Convert MM/DD/YYYY -> YYYY-MM-DD. Returns None if unparseable."""
    if not raw_date:
        return None
    try:
        return datetime.strptime(raw_date, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_records(records):
    """
    Filter out the aggregate 'Total' rows and normalize the fields we
    care about. Returns a list of dicts ready for save_rows().
    """
    out = []
    for r in records:
        name = r.get("name")
        if not name or name.strip().lower() == "total":
            continue

        report_date = parse_download_date(r.get("download_date"))
        if report_date is None:
            # skip rows we can't date -- better to miss a row than
            # silently misfile it under today's date
            continue

        out.append({
            "facility_name": name.strip(),
            "state": (r.get("detention_facility_state") or "").strip() or None,
            "report_date": report_date,
            "population": parse_count(r.get("count")),
            "raw": r,
        })
    return out


def save_rows(rows):
    added = 0
    with get_conn() as conn:
        for r in rows:
            try:
                conn.execute(
                    """
                    INSERT INTO facility_stats
                        (facility_name, state, source, report_date, population, raw_json)
                    VALUES (?, ?, 'TRAC', ?, ?, ?)
                    ON CONFLICT(facility_name, source, report_date)
                    DO UPDATE SET population=excluded.population, raw_json=excluded.raw_json
                    """,
                    (r["facility_name"], r["state"], r["report_date"],
                     r["population"], json.dumps(r["raw"])),
                )
                added += 1
            except Exception as e:
                print(f"  [warn] could not save row for {r.get('facility_name')}: {e}")
    return added


def run():
    started = datetime.now(timezone.utc).isoformat()
    scraper_name = "trac_scraper"

    try:
        records = fetch_json(TRAC_JSON_URL)
        rows = parse_records(records)
        added = save_rows(rows)
        status, err = "ok", None
        distinct_dates = sorted({r["report_date"] for r in rows})
        print(f"[{scraper_name}] saved/updated {added} facility rows "
              f"across {len(distinct_dates)} snapshot date(s) "
              f"(latest: {distinct_dates[-1] if distinct_dates else 'n/a'})")
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
