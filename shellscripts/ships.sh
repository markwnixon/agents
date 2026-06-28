#!/bin/bash
echo "ships.sh which runs python code FFF_make_pins.py"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 GGG_Ship_Schedule_Api.py "$1"

