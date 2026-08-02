"""
run_all.py -- Runs every scraper in sequence. This is the entry point
that cron / the systemd timer calls once a day.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from scrapers import trac_scraper, ice_newsroom_scraper, courtlistener_scraper

SCRAPERS = [
    ("TRAC detention stats", trac_scraper.run),
    ("ICE newsroom", ice_newsroom_scraper.run),
    ("CourtListener dockets", courtlistener_scraper.run),
]


def main():
    results = {}
    for name, fn in SCRAPERS:
        print(f"\n=== Running: {name} ===")
        try:
            results[name] = fn()
        except Exception as e:
            print(f"[fatal] {name} crashed: {e}")
            results[name] = False

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'OK' if ok else 'FAILED'}  -- {name}")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
