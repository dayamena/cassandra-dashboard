#!/usr/bin/env bash
# setup_pi.sh -- One-time setup for Cassandra on a Raspberry Pi 5
# running Raspberry Pi OS (Debian-based). Run this from inside the
# cassandra/ project directory after copying it onto the Pi, e.g.:
#
#   scp -r cassandra pi@raspberrypi.local:/home/pi/
#   ssh pi@raspberrypi.local
#   cd cassandra && bash scripts/setup_pi.sh
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "== Installing system packages =="
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip

echo "== Creating virtualenv =="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "== Initializing database =="
python3 db.py

echo "== Installing systemd units =="
sudo cp scripts/cassandra-dashboard.service /etc/systemd/system/
sudo cp scripts/cassandra-scrape.service /etc/systemd/system/
sudo cp scripts/cassandra-scrape.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now cassandra-dashboard.service
sudo systemctl enable --now cassandra-scrape.timer

echo ""
echo "== Done =="
echo "Dashboard: http://<pi-ip-address>:5000"
echo "Check scraper timer:  systemctl list-timers cassandra-scrape.timer"
echo "Check dashboard logs: journalctl -u cassandra-dashboard.service -f"
echo "Trigger a scrape now: sudo systemctl start cassandra-scrape.service"
echo ""
echo "Don't forget to create a .env file (see .env.example) with your"
echo "Slack webhook / SMTP settings for the digest, and edit the User=pi"
echo "lines in the .service files if your Pi username isn't 'pi'."
