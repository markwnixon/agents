#!/usr/bin/env bash
set -e

# Arguments
SCAC="$1"
PINID="$2"

# Basic validation
if [[ -z "$SCAC" || -z "$PINID" ]]; then
    echo "Usage: getpin2.sh <scac> <pinid>"
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
echo "Time   : $(date)"
echo "----------------------------------------"

# Run the actual headless PIN script
#"$PYTHON" FFF_make_pins_headless.py \
#    --scac "$SCAC" \
#    --pinid "$PINID"
echo "getpin2.sh which runs python code FFF_make_pins_headless.py"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_make_pins.py "$1" "$2"

EXIT_CODE=$?

echo "----------------------------------------"
echo "Finished PIN fetch"
echo "Exit code: $EXIT_CODE"
echo "Time     : $(date)"
echo "----------------------------------------"

exit $EXIT_CODE


