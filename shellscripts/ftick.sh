#!/bin/bash
echo "Running FFF_task_job_updater"
echo $PATH
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 FFF_task_job_updater.py "$1"
