#!/bin/bash
echo "Running GGG_gate_portadds.py"
echo $USER
echo $PATH
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 GGG_gate_portadd.py "$1" "$2" "$3"

