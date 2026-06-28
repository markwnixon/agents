#!/bin/bash
echo "ships.sh which runs python code GGG_Port_Details.py"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 GGG_Port_Details.py "$1"

