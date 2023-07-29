#!/bin/bash
echo "getpin.sh which runs python code DDD_make_pins.py"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_make_pins.py "$1"

