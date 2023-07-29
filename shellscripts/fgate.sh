#!/bin/bash
echo "Running FFF_task_gate_now.py"
echo $USER
echo $PATH
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_task_gate_now.py "$1" "$2" "$3"

