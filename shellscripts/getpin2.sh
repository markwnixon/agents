#!/bin/bash
#echo "getpin2.sh started at $(date)" >> /home/mark/getpin_debug.log
#echo "Args: $@" >> /home/mark/getpin_debug.log

#echo "getpin.sh which runs python code FFF_make_pins_headless.py"
#echo "deployed for $USER"
#cd /home/mark/flask
#source flaskenv/bin/activate
#cd /home/mark/flask/agents
#python3 FFF_make_pins_headless.py "$1" "$2" "$3"

#SCAC="$1"
#PINID="$2"
#MODE="$3"
#TASK_ID="$4"
#CALLBACK_DOMAIN="$5"

#echo "Running Python now..." >> /home/mark/getpin_debug.log
# Run your python script and capture its output
#RESULT=$(python3 FFF_make_pins_headless.py "$SCAC" "$PINID" "$MODE" 2>&1)
#echo "Python exit code: $?" >> /home/mark/getpin_debug.log
#echo "Python output: $RESULT" >> /home/mark/getpin_debug.log

#EXITCODE=$?

# Format safely for JSON (escape double quotes)
#RESULT_ESCAPED=$(echo "$RESULT" | sed 's/"/\\"/g')

# Send callback to Flask API
#curl -s -X POST \
#  -H "Content-Type: application/json" \
#  -d "{\"task_id\": \"${TASK_ID}\", \"result\": \"${RESULT_ESCAPED}\", \"exit_code\": ${EXITCODE}}" \
#  "${CALLBACK_DOMAIN}/pin_callback"

#exit 0

######################################################################################################

#!/bin/bash

# --- SAFETY SETTINGS ---
set -u                      # Fail on undefined vars
set -o pipefail             # Fail if any piped command fails
export PYTHONUNBUFFERED=1   # Ensure python logs flush

# === ARGUMENTS ===
SCAC="$1"
PINID="$2"
MODE="$3"
TASK_ID="$4"
DOMAIN="$5"

# === PATHS ===
BASE="/home/mark/flask"
VENV="$BASE/flaskenv/bin/activate"
AGENTS="$BASE/agents"
SHELLSCRIPTS="$AGENTS/shellscripts"
SCRIPT="$AGENTS/getpin2.py"

LOGFILE="/home/mark/pinout_${TASK_ID}.log"

# === LOGGING FUNCTION ===
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"
    sync   # force flush
}

log "=== getpin2.sh START ==="
log "Args: SCAC=$SCAC PINID=$PINID MODE=$MODE TASK_ID=$TASK_ID DOMAIN=$DOMAIN"
log "LOGFILE: $LOGFILE"

# === VALIDATE ARGUMENTS ===
if [[ -z "$SCAC" || -z "$PINID" || -z "$MODE" || -z "$TASK_ID" || -z "$DOMAIN" ]]; then
    log "ERROR: Missing arguments!"
    exit 1
fi

# === MOVE TO FLASK DIRECTORY & ACTIVATE VENV ===
log "Changing directory to $BASE"
cd "$BASE" || { log "ERROR: Cannot cd to $BASE"; exit 1; }

if [[ ! -f "$VENV" ]]; then
    log "ERROR: Virtual environment not found at $VENV"
    exit 1
fi

log "Activating virtualenv: $VENV"
source "$VENV"

# === MOVE TO AGENTS DIRECTORY ===
log "Changing directory to $AGENTS"
cd "$AGENTS" || { log "ERROR: Cannot cd to $AGENTS"; exit 1; }

# === CHECK PYTHON SCRIPT ===
if [[ ! -f "$SCRIPT" ]]; then
    log "ERROR: Python script not found at $SCRIPT"
    exit 1
fi

# === RUN PYTHON SCRIPT ===
log "Running python script: $SCRIPT"

python3 "$SCRIPT" "$SCAC" "$PINID" "$MODE" "$TASK_ID" "$DOMAIN" 2>&1 | tee -a "$LOGFILE"
RET=$?

log "Python exit code: $RET"

if [[ $RET -ne 0 ]]; then
    log "ERROR: Python script failed"
    exit $RET
fi

log "=== getpin2.sh COMPLETE ==="
exit 0


