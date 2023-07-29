#!/bin/bash
echo "Running AR Report Maker for Global"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_dray_Global.py "$1"

