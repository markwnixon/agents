#!/bin/bash
#echo "getpin.sh which runs python code FFF_make_pins_headless.py"
#echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_make_pins_headless.py "$1" "$2"

