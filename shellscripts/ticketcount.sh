#!/bin/bash
echo "Running ticketcount"
echo $PATH
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 ticketcount.py "$@"
