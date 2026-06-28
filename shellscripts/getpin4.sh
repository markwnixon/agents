#!/bin/bash
echo "getpin.sh which runs python code FFF_make_pins.py"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_make_pins4.py "$1"

