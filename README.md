# Cassandra — Public Records Monitor

A self-hosted monitor for **publicly available** immigration-detention
data and records: facility population statistics, court dockets, and
official press releases / disclosures. Built to run on a Raspberry Pi 5.

**What this deliberately does NOT do:** track the real-time location of
individual enforcement agents or operations, or crowdsource live
raid/incident reports. It only aggregates data that's already public —
published statistics, public court filings, and official communications
— for research and reporting purposes.

## What it does

1. **Scrapers** (`scrapers/`) pull data on a schedule:
   - `trac_scraper.py` — detention facility population stats from TRAC
     Immigration (tracreports.org), a Syracuse University research
     project that publishes FOIA-derived detention data.
   - `ice_newsroom_scraper.py` — press releases ICE itself publishes at
     ice.gov/newsroom.
   - `courtlistener_scraper.py` — immigration-related court dockets via
     CourtListener's free public API (mirrors public PACER filings via
     the RECAP project — no PACER fees, no auth needed for basic use).
2. **Database** (`db.py`) — a single SQLite file. No server process,
   easy to back up (just copy `data/cassandra.db`).
3. **Dashboard** (`dashboard/`) — a small Flask app with charts/tables
   over the scraped data.
4. **Digest** (`digest/digest.py`) — summarizes what's new since the
   last run and posts it to Slack (webhook) and/or email (SMTP).

## Quick start (development machine)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 db.py                      # initialize the database
python3 scrapers/run_all.py        # run all scrapers once
python3 dashboard/app.py           # start the dashboard at :5000
python3 digest/digest.py           # print/send a digest
```

## Deploying to a Raspberry Pi 5

1. Copy this folder onto the Pi:
   ```bash
   scp -r cassandra pi@raspberrypi.local:/home/pi/
   ```
2. SSH in and run the setup script:
   ```bash
   ssh pi@raspberrypi.local
   cd cassandra
   bash scripts/setup_pi.sh
   ```
   This installs Python deps into a venv, initializes the DB, and
   installs two systemd units:
   - `cassandra-dashboard.service` — runs the Flask dashboard, always on.
   - `cassandra-scrape.timer` — runs the scrapers + digest once a day
     (07:00 by default — edit `scripts/cassandra-scrape.timer` to change).

3. Copy `.env.example` to `.env` and fill in your Slack webhook / SMTP
   settings if you want the digest to actually send anywhere:
   ```bash
   cp .env.example .env
   nano .env
   ```

4. Visit `http://<pi-ip>:5000` for the dashboard.

Useful commands once installed:
```bash
systemctl list-timers cassandra-scrape.timer     # see next scheduled run
sudo systemctl start cassandra-scrape.service    # trigger a scrape now
journalctl -u cassandra-dashboard.service -f     # tail dashboard logs
journalctl -u cassandra-scrape.service -f        # tail scraper logs
```

## Notes on scraper maintenance

Scraped sites change their HTML periodically. Each scraper stores the
raw scraped record in a `raw_json` column alongside parsed fields, so if
parsing starts silently producing nulls, you can inspect `raw_json` in
the DB to see what changed and fix the parser without re-scraping.

Each scraper also logs its run (success/failure, rows added, error
message) to the `scrape_runs` table, visible in the dashboard's status
line and in the digest, so failures are visible rather than silent.

## Extending it

Some natural next additions, if useful:
- A FOIA reading-room scraper (`foia_releases` table already exists,
  just needs a scraper — DHS OIG and DOJ both have public FOIA logs).
- RSS/Atom feed support for sources that publish one, which is more
  stable than HTML scraping.
- A `state` filter or facility watchlist for the dashboard.
# cassandra-dashboard
