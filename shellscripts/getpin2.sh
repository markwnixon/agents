#!/bin/bash
echo "getpin2.sh started at $(date)" >> /home/mark/getpin_debug.log
echo "Args: $@" >> /home/mark/getpin_debug.log

#echo "getpin.sh which runs python code FFF_make_pins_headless.py"
#echo "deployed for $USER"
cd /home/mark/flask
source flaskenv/bin/activate
cd /home/mark/flask/agents
#python3 FFF_make_pins_headless.py "$1" "$2" "$3"

SCAC="$1"
PINID="$2"
MODE="$3"
TASK_ID="$4"
CALLBACK_DOMAIN="$5"

echo "Running Python now..." >> /home/mark/getpin_debug.log
# Run your python script and capture its output
RESULT=$(python3 FFF_make_pins_headless.py "$SCAC" "$PINID" "$MODE" 2>&1)
echo "Python exit code: $?" >> /home/mark/getpin_debug.log
echo "Python output: $RESULT" >> /home/mark/getpin_debug.log

EXITCODE=$?

# Format safely for JSON (escape double quotes)
RESULT_ESCAPED=$(echo "$RESULT" | sed 's/"/\\"/g')

# Send callback to Flask API
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d "{\"task_id\": \"${TASK_ID}\", \"result\": \"${RESULT_ESCAPED}\", \"exit_code\": ${EXITCODE}}" \
  "${CALLBACK_DOMAIN}/pin_callback"

exit 0
