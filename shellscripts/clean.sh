#!/bin/bash
echo "Running FFF_Clean"
echo $PATH
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_Clean.py "$1" "$2"
