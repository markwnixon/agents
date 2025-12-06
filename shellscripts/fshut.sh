#!/bin/bash
echo "Running FFF_Gate_Shuttle.py"
echo $USER
echo $PATH
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_Gate_Shuttle.py "$1" "$2" "$3"
python3 FFF_Gate_Shuttle_Update.py "$2" "$3"

