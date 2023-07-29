#!/bin/bash
echo "Running FFF_dray_ARcheck.py"
echo $USER
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_dray_ARcheck.py "$1"

