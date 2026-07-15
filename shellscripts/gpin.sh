#!/bin/bash
echo "gpin.sh which runs python code HHH_make_pins.py"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
export PLAYWRIGHT_BROWSERS_PATH="/home/$USER/flask/agents/.ms-playwright"
python3 HHH_make_pins.py "$1"
