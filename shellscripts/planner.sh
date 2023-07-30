#!/bin/bash
echo "Running Planner"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_planner.py "$1"

