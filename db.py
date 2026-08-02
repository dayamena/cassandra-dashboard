"""
db.py -- SQLite schema + connection helper for the Cassandra project.

Design notes:
- SQLite is used because this runs on a Raspberry Pi 5: no separate DB
  server to manage, single file, trivial to back up (just copy the file).
- Every table has a `first_seen` / `last_seen` pair so the digest job can
  answer "what's new since last time" without a separate change-log table.
- Raw scraped payloads are stored alongside parsed fields so you can
  re-parse later if a source changes format without re-scraping.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "data" / "cassandra.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS facility_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_name TEXT NOT NULL,
    state TEXT,
    source TEXT NOT NULL,          -- e.g. 'TRAC', 'ICE_public_report'
    report_date TEXT NOT NULL,     -- the date the stat applies to (YYYY-MM-DD)
    population INTEGER,
    avg_length_of_stay_days REAL,
    raw_json TEXT,                 -- original scraped record, for re-parsing
    scraped_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(facility_name, source, report_date)
);

CREATE TABLE IF NOT EXISTS court_dockets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT NOT NULL,
    court TEXT,
    filing_date TEXT,
    title TEXT,
    docket_url TEXT,
    source TEXT NOT NULL,          -- e.g. 'PACER', 'CourtListener'
    raw_json TEXT,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(case_number, source)
);

CREATE TABLE IF NOT EXISTS foia_releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    agency TEXT,
    release_date TEXT,
    url TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    raw_json TEXT,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(url)
);

CREATE TABLE IF NOT EXISTS press_releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    published_date TEXT,
    url TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,          -- e.g. 'ICE_newsroom', 'DHS_OIG'
    raw_json TEXT,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(url)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scraper_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,                   -- 'ok', 'error'
    rows_added INTEGER DEFAULT 0,
    error_message TEXT
);
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()
