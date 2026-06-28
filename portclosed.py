import os
import sys
import socket
from utils import getpaths, hasinput, d2s, stripper

scac = 'OSLM'
SCAC = scac.upper()
nt = 'remote'

print(f'Running Base Port Closed Database {scac}')
host_name = socket.gethostname()
print("Host Name:", host_name)
dropbox_path = getpaths(host_name, 'dropbox')
ar_path = f'{dropbox_path}/Dray/{scac}_AR_Report.xlsx'
sys_path = getpaths(host_name, 'system')
sys.path.append(sys_path)  # So we can import CCC_system_setup from full path

os.environ['SCAC'] = scac
os.environ['PURPOSE'] = 'script'
os.environ['MACHINE'] = host_name
os.environ['TUNNEL'] = nt


from remote_db_connect import tunnel, db
from models8 import PortClosed

import datetime
from datetime import timedelta
year, ytd_month, ytd_day = 2024, 1, 1
today = datetime.date(year, ytd_month, ytd_day)
todayyear = today.year
nextyear = year+1

while todayyear == year or todayyear == nextyear:
    todayyear = today.year
    day_of_week = today.weekday()
    print(f'The year is {year} and the date is {today}')
    if day_of_week == 5 or day_of_week == 6:
        #Check if already in database:
        cdat = PortClosed.query.filter(PortClosed.Date == today).first()
        if cdat is None:
            #Add to port closed database...for now...
            input = PortClosed(Date=today,Reason='Weekend')
            db.session.add(input)
            db.session.commit()
    today = today + timedelta(days=1)
