"""
app.py -- Flask dashboard for Cassandra. Reads from the SQLite DB that
the scrapers populate and renders charts/tables. Designed to run as a
lightweight systemd service on a Raspberry Pi 5 (Flask's built-in dev
server is fine for a small internal dashboard; put it behind Caddy or
nginx with basic auth if you're exposing it beyond localhost).
"""

import sys
from pathlib import Path

from flask import Flask, render_template, jsonify

sys.path.append(str(Path(__file__).parent.parent))
from db import get_conn

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/facility-stats")
def api_facility_stats():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT facility_name, state, report_date, population
            FROM facility_stats
            ORDER BY report_date DESC, population DESC
            LIMIT 200
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/facility-trend/<facility_name>")
def api_facility_trend(facility_name):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT report_date, population
            FROM facility_stats
            WHERE facility_name = ?
            ORDER BY report_date ASC
            """,
            (facility_name,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/recent-dockets")
def api_recent_dockets():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT case_number, court, filing_date, title, docket_url
            FROM court_dockets
            ORDER BY filing_date DESC
            LIMIT 50
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/recent-press")
def api_recent_press():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT title, published_date, url, summary, source
            FROM press_releases
            ORDER BY published_date DESC
            LIMIT 50
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/scrape-status")
def api_scrape_status():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT scraper_name, started_at, finished_at, status, rows_added, error_message
            FROM scrape_runs
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    # host='0.0.0.0' so it's reachable on your LAN from other devices;
    # remove/restrict if you don't want that.
    app.run(host="0.0.0.0", port=5000, debug=False)
