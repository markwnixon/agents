#!/bin/bash
echo "Running Chassis Checker"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_dray_Chassis.py "$1"
