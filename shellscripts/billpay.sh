#!/bin/bash
echo "billpay.sh which runs python code JJJ_BillPay_Import.py"
echo "deployed for $USER"
cd /home/$USER/flask
source flaskenv/bin/activate
cd /home/$USER/flask/agents
python3 JJJ_BillPay_Import.py "$1" "${2:-review}" "$3" "$4" "${5:-remote}"
