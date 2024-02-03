#!/bin/bash
echo "Running FFF_dray_ARhistory.py"
echo $USER
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_dray_ARhistory.py "$1" "$2"

