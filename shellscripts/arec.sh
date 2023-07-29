#!/bin/bash
echo "Running FFF_dray_ARcheck.py"
cd /home/mark/flask
source flaskenv/bin/activate
cd /home/mark/flask/agents
python3 FFF_dray_ARcheck.py "$1"

