#!/usr/bin/env bash
set -e

SCAC="$1"
PINID="$2"

if [[ -z "$SCAC" || -z "$PINID" ]]; then
    echo "Usage: gpin2.sh <scac> <pinid>"
    exit 1
fi

FLASK_DIR="/home/$USER/flask"
AGENTS_DIR="$FLASK_DIR/agents"

echo "----------------------------------------"
echo "Starting Playwright headless PIN fetch"
echo "SCAC   : $SCAC"
echo "PINID  : $PINID"
echo "Time   : $(date)"
echo "----------------------------------------"

echo "gpin2.sh which runs python code HHH_make_pins.py in headless mode"
echo "deployed for $USER"
cd "$FLASK_DIR"
source flaskenv/bin/activate
cd "$AGENTS_DIR"
export PLAYWRIGHT_BROWSERS_PATH="$AGENTS_DIR/.ms-playwright"
export GPIN_HEADLESS=1
python3 HHH_make_pins.py "$SCAC" "$PINID"

EXIT_CODE=$?

echo "----------------------------------------"
echo "Finished Playwright headless PIN fetch"
echo "Exit code: $EXIT_CODE"
echo "Time     : $(date)"
echo "----------------------------------------"

exit $EXIT_CODE
