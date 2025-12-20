#!/usr/bin/env bash
set -e

# Arguments
SCAC="$1"
PINID="$2"
MODE="$3"
DOMAIN="$4"

# Basic validation
if [[ -z "$SCAC" || -z "$PINID" || -z "$MODE" || -z "$DOMAIN" ]]; then
    echo "Usage: getpin2.sh <scac> <pinid> <mode> <domain>"
    exit 1
fi

# Paths
FLASK_DIR="/home/mark/flask"
AGENTS_DIR="$FLASK_DIR/agents"
PYTHON="$FLASK_DIR/flaskenv/bin/python"

cd "$AGENTS_DIR"

echo "----------------------------------------"
echo "Starting PIN fetch"
echo "SCAC   : $SCAC"
echo "PINID  : $PINID"
echo "MODE   : $MODE"
echo "DOMAIN : $DOMAIN"
echo "Time   : $(date)"
echo "----------------------------------------"

# Run the actual headless PIN script
"$PYTHON" FFF_make_pins_headless.py \
    --scac "$SCAC" \
    --pinid "$PINID" \
    --mode "$MODE" \
    --domain "$DOMAIN"

EXIT_CODE=$?

echo "----------------------------------------"
echo "Finished PIN fetch"
echo "Exit code: $EXIT_CODE"
echo "Time     : $(date)"
echo "----------------------------------------"

exit $EXIT_CODE


