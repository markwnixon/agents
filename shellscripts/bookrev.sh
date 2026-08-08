#!/bin/bash
echo "bookrev.sh which runs python code III_New_Order_Booking_Review.py"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
export PLAYWRIGHT_BROWSERS_PATH="/home/$USER/flask/agents/.ms-playwright"
export BOOKING_REVIEW_HEADLESS="${BOOKING_REVIEW_HEADLESS:-1}"
python3 III_New_Order_Booking_Review.py "$1"
