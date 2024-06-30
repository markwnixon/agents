#!/bin/bash
echo "Running FFF_task_ardata.py"
echo $USER
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_task_ardata.py "$1"

