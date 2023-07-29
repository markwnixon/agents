#!/bin/bash
echo "Running FFF_task_gate_now.py"
echo $PATH
cd /home/mark/flask
source flaskenv/bin/activate
cd /home/mark/flask/agents
python3 FFF_task_gate_now.py "$1" "$2" "$3"

