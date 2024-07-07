#!/bin/bash
echo "Running FFF_emailread_daily.py"
echo "Path is: $PATH"
echo "Deployed for: $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_emailread_daily.py "$1"
